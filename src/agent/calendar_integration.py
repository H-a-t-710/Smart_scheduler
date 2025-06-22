import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import pytz
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import dateparser
from config.environment import config

logger = logging.getLogger(__name__)

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/calendar']

class CalendarEvent:
    """Represents a calendar event"""
    
    def __init__(self, event_id: str, summary: str, start_time: datetime, 
                 end_time: datetime, description: str = "", attendees: List[str] = None):
        self.event_id = event_id
        self.summary = summary
        self.start_time = start_time
        self.end_time = end_time
        self.description = description
        self.attendees = attendees or []
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API calls"""
        return {
            'summary': self.summary,
            'description': self.description,
            'start': {
                'dateTime': self.start_time.isoformat(),
                'timeZone': str(self.start_time.tzinfo)
            },
            'end': {
                'dateTime': self.end_time.isoformat(),
                'timeZone': str(self.end_time.tzinfo)
            },
            'attendees': [{'email': email} for email in self.attendees]
        }

class TimeSlot:
    """Represents an available time slot"""
    
    def __init__(self, start_time: datetime, end_time: datetime, user_timezone=None):
        self.start_time = start_time
        self.end_time = end_time
        self.duration_minutes = int((end_time - start_time).total_seconds() / 60)
        self.user_timezone = user_timezone
    
    def can_fit_meeting(self, duration_minutes: int) -> bool:
        """Check if this slot can fit a meeting of given duration"""
        return self.duration_minutes >= duration_minutes
    
    def __str__(self):
        # Format for user-friendly display in user's local timezone
        display_start = self.start_time
        display_end = self.end_time
        
        # Convert to user's timezone if available and times are timezone-aware
        if self.user_timezone and self.start_time.tzinfo:
            display_start = self.start_time.astimezone(self.user_timezone)
            display_end = self.end_time.astimezone(self.user_timezone)
        elif self.user_timezone and not self.start_time.tzinfo:
            # If no timezone info, assume it's already in user's timezone
            display_start = self.start_time.replace(tzinfo=self.user_timezone)
            display_end = self.end_time.replace(tzinfo=self.user_timezone)
        
        day_name = display_start.strftime('%A')  # Monday, Tuesday, etc.
        date = display_start.strftime('%B %d')   # December 16
        start_time = display_start.strftime('%I:%M %p').lstrip('0')  # 2:00 PM (remove leading zero)
        end_time = display_end.strftime('%I:%M %p').lstrip('0')      # 3:00 PM
        
        return f"{day_name}, {date} at {start_time} - {end_time}"

class GoogleCalendarService:
    """Service for interacting with Google Calendar API"""
    
    def __init__(self):
        self.service = None
        # Use local timezone for better day/date alignment
        import tzlocal
        try:
            self.timezone = tzlocal.get_localzone()
        except:
            # Fallback to a common timezone if local detection fails
            self.timezone = pytz.timezone('America/New_York')
        self.calendar_id = 'primary'  # Use primary calendar
    
    async def authenticate(self) -> bool:
        """Authenticate with Google Calendar API"""
        try:
            creds = None
            
            # The file token.json stores the user's access and refresh tokens
            if os.path.exists(config.GOOGLE_CALENDAR_TOKEN):
                creds = Credentials.from_authorized_user_file(config.GOOGLE_CALENDAR_TOKEN, SCOPES)
            
            # If there are no (valid) credentials available, let the user log in
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        config.GOOGLE_CALENDAR_CREDENTIALS, SCOPES)
                    creds = flow.run_local_server(port=0)
                
                # Save the credentials for the next run
                with open(config.GOOGLE_CALENDAR_TOKEN, 'w') as token:
                    token.write(creds.to_json())
            
            self.service = build('calendar', 'v3', credentials=creds)
            logger.info("Successfully authenticated with Google Calendar")
            return True
            
        except Exception as e:
            logger.error(f"Error authenticating with Google Calendar: {e}")
            return False
    
    async def get_busy_times(self, start_datetime: datetime, end_datetime: datetime) -> List[Tuple[datetime, datetime]]:
        """Get busy time periods within the specified range"""
        try:
            if not self.service:
                # Try to authenticate first
                auth_success = await self.authenticate()
                if not auth_success:
                    # Log error and return empty list - don't use mock data for real scheduling
                    logger.error("Google Calendar authentication failed - cannot retrieve real calendar data")
                    logger.error("Please ensure Google Calendar API is properly configured")
                    return []  # Return empty list instead of mock data
            
            # Format times for API
            time_min = start_datetime.isoformat()
            time_max = end_datetime.isoformat()
            
            # Get events from calendar
            events_result = self.service.events().list(
                calendarId=self.calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            busy_times = []
            
            for event in events:
                start = event['start'].get('dateTime', event['start'].get('date'))
                end = event['end'].get('dateTime', event['end'].get('date'))
                
                # Parse datetime strings
                start_dt = dateparser.parse(start)
                end_dt = dateparser.parse(end)
                
                if start_dt and end_dt:
                    busy_times.append((start_dt, end_dt))
            
            return busy_times
            
        except HttpError as error:
            logger.error(f"Google Calendar API error: {error}")
            logger.error("Please check your Google Calendar API configuration and permissions")
            return []  # Return empty list instead of mock data
        except Exception as e:
            logger.error(f"Unexpected error in get_busy_times: {e}")
            return []  # Return empty list instead of mock data
    

    
    async def find_available_slots(self, 
                                 duration_minutes: int, 
                                 start_date: datetime, 
                                 end_date: datetime,
                                 work_hours_start: int = 9,  # 9 AM
                                 work_hours_end: int = 17,   # 5 PM
                                 buffer_minutes: int = 15) -> List[TimeSlot]:
        """Find available time slots for a meeting"""
        try:
            # Get busy times
            busy_times = await self.get_busy_times(start_date, end_date)
            
            available_slots = []
            current_time = start_date.replace(hour=work_hours_start, minute=0, second=0, microsecond=0)
            
            while current_time.date() <= end_date.date():
                # Skip weekends (can be made configurable)
                if current_time.weekday() >= 5:  # Saturday = 5, Sunday = 6
                    current_time += timedelta(days=1)
                    current_time = current_time.replace(hour=work_hours_start, minute=0, second=0, microsecond=0)
                    continue
                
                day_end = current_time.replace(hour=work_hours_end, minute=0, second=0, microsecond=0)
                
                # Find available slots for this day
                day_slots = self._find_slots_for_day(
                    current_time, day_end, busy_times, duration_minutes, buffer_minutes
                )
                available_slots.extend(day_slots)
                
                # Move to next day
                current_time += timedelta(days=1)
                current_time = current_time.replace(hour=work_hours_start, minute=0, second=0, microsecond=0)
            
            return available_slots
            
        except Exception as e:
            logger.error(f"Error finding available slots: {e}")
            return []
    
    def _find_slots_for_day(self, day_start: datetime, day_end: datetime, 
                           busy_times: List[Tuple[datetime, datetime]], 
                           duration_minutes: int, buffer_minutes: int) -> List[TimeSlot]:
        """Find available slots within a single day"""
        available_slots = []
        
        # Filter busy times for this day
        day_busy_times = []
        for busy_start, busy_end in busy_times:
            if (busy_start.date() == day_start.date() or 
                busy_end.date() == day_start.date() or
                (busy_start.date() < day_start.date() < busy_end.date())):
                
                # Clip to day boundaries
                clipped_start = max(busy_start, day_start)
                clipped_end = min(busy_end, day_end)
                day_busy_times.append((clipped_start, clipped_end))
        
        # Sort busy times
        day_busy_times.sort(key=lambda x: x[0])
        
        # Find gaps between busy times
        current_time = day_start
        
        for busy_start, busy_end in day_busy_times:
            # Check if there's a gap before this busy time
            if current_time < busy_start:
                gap_duration = int((busy_start - current_time).total_seconds() / 60)
                if gap_duration >= duration_minutes + buffer_minutes:
                    # Create a slot exactly for the meeting duration
                    slot_end = current_time + timedelta(minutes=duration_minutes)
                    slot = TimeSlot(current_time, slot_end, user_timezone=self.timezone)
                    available_slots.append(slot)
            
            # Move past this busy time
            current_time = max(current_time, busy_end + timedelta(minutes=buffer_minutes))
        
        # Check if there's time left at the end of the day
        if current_time < day_end:
            gap_duration = int((day_end - current_time).total_seconds() / 60)
            if gap_duration >= duration_minutes:
                # Create a slot exactly for the meeting duration
                slot_end = current_time + timedelta(minutes=duration_minutes)
                slot = TimeSlot(current_time, slot_end, user_timezone=self.timezone)
                available_slots.append(slot)
        
        return available_slots
    
    async def create_event(self, event: CalendarEvent) -> Optional[str]:
        """Create a new calendar event"""
        try:
            if not self.service:
                # Try to authenticate first
                auth_success = await self.authenticate()
                if not auth_success:
                    logger.error("Cannot create calendar event - Google Calendar authentication failed")
                    return None
            
            event_dict = event.to_dict()
            created_event = self.service.events().insert(
                calendarId=self.calendar_id, 
                body=event_dict
            ).execute()
            
            event_id = created_event.get('id')
            logger.info(f"Event created successfully with ID: {event_id}")
            return event_id
            
        except HttpError as error:
            logger.error(f"An error occurred creating event: {error}")
            return None
    
    async def get_event_by_name(self, event_name: str, 
                               start_date: datetime, 
                               end_date: datetime) -> Optional[CalendarEvent]:
        """Find an event by name within a date range"""
        try:
            if not self.service:
                await self.authenticate()
            
            events_result = self.service.events().list(
                calendarId=self.calendar_id,
                timeMin=start_date.isoformat(),
                timeMax=end_date.isoformat(),
                q=event_name,  # Search query
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            
            if events:
                event = events[0]  # Return first match
                start = event['start'].get('dateTime', event['start'].get('date'))
                end = event['end'].get('dateTime', event['end'].get('date'))
                
                start_dt = dateparser.parse(start)
                end_dt = dateparser.parse(end)
                
                return CalendarEvent(
                    event_id=event.get('id'),
                    summary=event.get('summary', ''),
                    start_time=start_dt,
                    end_time=end_dt,
                    description=event.get('description', '')
                )
            
            return None
            
        except HttpError as error:
            logger.error(f"An error occurred searching for event: {error}")
            return None

class CalendarManager:
    """High-level manager for calendar operations"""
    
    def __init__(self):
        # Use local timezone for better day/date alignment
        import tzlocal
        try:
            self.user_timezone = tzlocal.get_localzone()
        except:
            # Fallback to a common timezone if local detection fails
            self.user_timezone = pytz.timezone('America/New_York')
        
        self.calendar_service = GoogleCalendarService()
        # Ensure calendar service uses the same timezone
        self.calendar_service.timezone = self.user_timezone
    
    async def initialize(self):
        """Initialize the calendar manager"""
        success = await self.calendar_service.authenticate()
        if success:
            logger.info("Calendar manager initialized successfully")
        return success
    
    async def find_meeting_slots(self, 
                               duration_minutes: int,
                               preferred_date: Optional[str] = None,
                               preferred_time: Optional[str] = None,
                               date_range_days: int = 7,
                               time_preference: Optional[str] = None) -> List[TimeSlot]:
        """Find available meeting slots based on user preferences"""
        try:
            # Parse time preference if provided (e.g., "Tuesday morning", "Wednesday afternoon")
            if time_preference:
                # Use dateparser to handle natural language with timezone settings
                parsed_time = dateparser.parse(
                    time_preference, 
                    settings={
                        'PREFER_DATES_FROM': 'future',
                        'TIMEZONE': str(self.user_timezone),
                        'RETURN_AS_TIMEZONE_AWARE': True
                    }
                )
                
                if parsed_time:
                    # Ensure parsed time is in user's timezone
                    if parsed_time.tzinfo is None:
                        parsed_time = parsed_time.replace(tzinfo=self.user_timezone)
                    else:
                        parsed_time = parsed_time.astimezone(self.user_timezone)
                    
                    # If it's a specific day, search only that day in user's timezone
                    start_datetime = parsed_time.replace(hour=9, minute=0, second=0, microsecond=0)
                    end_datetime = parsed_time.replace(hour=17, minute=0, second=0, microsecond=0)
                    
                    # Adjust for morning/afternoon preferences in user's local timezone
                    if 'morning' in time_preference.lower():
                        start_datetime = parsed_time.replace(hour=9, minute=0, second=0, microsecond=0)
                        end_datetime = parsed_time.replace(hour=12, minute=0, second=0, microsecond=0)
                    elif 'afternoon' in time_preference.lower():
                        start_datetime = parsed_time.replace(hour=12, minute=0, second=0, microsecond=0)
                        end_datetime = parsed_time.replace(hour=17, minute=0, second=0, microsecond=0)
                    elif 'evening' in time_preference.lower():
                        start_datetime = parsed_time.replace(hour=17, minute=0, second=0, microsecond=0)
                        end_datetime = parsed_time.replace(hour=20, minute=0, second=0, microsecond=0)
                    
                    logger.info(f"Parsed '{time_preference}' to {start_datetime} - {end_datetime} in timezone {self.user_timezone}")
                else:
                    # Fallback to default range if parsing fails
                    now = datetime.now(self.user_timezone)
                    start_datetime = now + timedelta(hours=1)
                    end_datetime = start_datetime + timedelta(days=date_range_days)
            
            # Parse preferred date/time or use defaults
            elif preferred_date and preferred_time:
                start_datetime = dateparser.parse(f"{preferred_date} {preferred_time}")
                end_datetime = start_datetime + timedelta(days=1)
            elif preferred_date:
                start_datetime = dateparser.parse(preferred_date)
                start_datetime = start_datetime.replace(hour=9, minute=0)
                end_datetime = start_datetime.replace(hour=17, minute=0)
            else:
                # Default to next 7 days
                now = datetime.now(self.user_timezone)
                start_datetime = now + timedelta(hours=1)  # Start from next hour
                end_datetime = start_datetime + timedelta(days=date_range_days)
            
            # Make timezone aware if needed
            if start_datetime.tzinfo is None:
                start_datetime = start_datetime.replace(tzinfo=self.user_timezone)
            if end_datetime.tzinfo is None:
                end_datetime = end_datetime.replace(tzinfo=self.user_timezone)
            
            logger.info(f"Searching for slots between {start_datetime} and {end_datetime}")
            
            slots = await self.calendar_service.find_available_slots(
                duration_minutes=duration_minutes,
                start_date=start_datetime,
                end_date=end_datetime
            )
            
            logger.info(f"Found {len(slots)} available slots")
            
            # If user specified a particular day, filter to only show slots from that day
            if time_preference:
                # Check if user specified a specific day
                specified_day = None
                specified_time_of_day = None
                days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
                
                for day in days:
                    if day in time_preference.lower():
                        specified_day = day
                        break
                
                # Check for time of day preferences
                if 'morning' in time_preference.lower():
                    specified_time_of_day = 'morning'
                elif 'afternoon' in time_preference.lower():
                    specified_time_of_day = 'afternoon'
                elif 'evening' in time_preference.lower():
                    specified_time_of_day = 'evening'
                
                if specified_day:
                    # Filter slots to only include the specified day and time of day
                    filtered_slots = []
                    for slot in slots:
                        # Convert slot time to user's timezone for comparison
                        slot_time_local = slot.start_time.astimezone(self.user_timezone) if slot.start_time.tzinfo else slot.start_time.replace(tzinfo=self.user_timezone)
                        slot_day = slot_time_local.strftime('%A').lower()
                        slot_hour = slot_time_local.hour
                        
                        # Check if it matches the requested day
                        if slot_day == specified_day:
                            # If time of day is specified, also check that
                            if specified_time_of_day:
                                if (specified_time_of_day == 'morning' and 9 <= slot_hour < 12) or \
                                   (specified_time_of_day == 'afternoon' and 12 <= slot_hour < 17) or \
                                   (specified_time_of_day == 'evening' and 17 <= slot_hour < 20):
                                    filtered_slots.append(slot)
                                    logger.debug(f"Included slot: {slot} (hour {slot_hour} matches {specified_time_of_day})")
                                else:
                                    logger.debug(f"Excluded slot: {slot} (hour {slot_hour} doesn't match {specified_time_of_day})")
                            else:
                                # No time preference, include all slots from the day
                                filtered_slots.append(slot)
                    
                    logger.info(f"Filtered to {len(filtered_slots)} slots for {specified_day} {specified_time_of_day or ''}")
                    return filtered_slots[:10]  # Return top 10 slots from the specified day/time
            
            return slots[:10]  # Return top 10 slots
            
        except Exception as e:
            logger.error(f"Error finding meeting slots: {e}")
            return []
    
    async def schedule_meeting(self, 
                             title: str,
                             start_time: datetime, 
                             duration_minutes: int,
                             description: str = "",
                             attendees: List[str] = None) -> Optional[str]:
        """Schedule a meeting"""
        try:
            end_time = start_time + timedelta(minutes=duration_minutes)
            
            event = CalendarEvent(
                event_id="",  # Will be generated
                summary=title,
                start_time=start_time,
                end_time=end_time,
                description=description,
                attendees=attendees or []
            )
            
            event_id = await self.calendar_service.create_event(event)
            return event_id
            
        except Exception as e:
            logger.error(f"Error scheduling meeting: {e}")
            return None
    
    async def find_existing_event(self, event_name: str, days_to_search: int = 30) -> Optional[CalendarEvent]:
        """Find an existing event by name"""
        try:
            start_date = datetime.now() - timedelta(days=days_to_search)
            end_date = datetime.now() + timedelta(days=days_to_search)
            
            # Make timezone aware
            if start_date.tzinfo is None:
                start_date = start_date.replace(tzinfo=self.user_timezone)
            if end_date.tzinfo is None:
                end_date = end_date.replace(tzinfo=self.user_timezone)
            
            event = await self.calendar_service.get_event_by_name(
                event_name, start_date, end_date
            )
            
            return event
            
        except Exception as e:
            logger.error(f"Error finding existing event: {e}")
            return None 