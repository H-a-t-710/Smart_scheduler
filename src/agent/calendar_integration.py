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
    
    def __init__(self, start_time: datetime, end_time: datetime):
        self.start_time = start_time
        self.end_time = end_time
        self.duration_minutes = int((end_time - start_time).total_seconds() / 60)
    
    def can_fit_meeting(self, duration_minutes: int) -> bool:
        """Check if this slot can fit a meeting of given duration"""
        return self.duration_minutes >= duration_minutes
    
    def __str__(self):
        # Format for user-friendly display
        day_name = self.start_time.strftime('%A')  # Monday, Tuesday, etc.
        date = self.start_time.strftime('%B %d')   # December 16
        start_time = self.start_time.strftime('%I:%M %p').lstrip('0')  # 2:00 PM (remove leading zero)
        end_time = self.end_time.strftime('%I:%M %p').lstrip('0')      # 3:00 PM
        
        return f"{day_name}, {date} at {start_time} - {end_time}"

class GoogleCalendarService:
    """Service for interacting with Google Calendar API"""
    
    def __init__(self):
        self.service = None
        self.timezone = pytz.timezone('UTC')  # Default timezone
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
                    # Fall back to mock mode if authentication fails
                    logger.info("Using mock calendar data - Google Calendar not available")
                    return self._get_mock_busy_times(start_datetime, end_datetime)
            
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
            logger.error(f"An error occurred: {error}")
            # Fall back to mock mode on API errors
            return self._get_mock_busy_times(start_datetime, end_datetime)
        except Exception as e:
            logger.error(f"Unexpected error in get_busy_times: {e}")
            # Fall back to mock mode on any other errors
            return self._get_mock_busy_times(start_datetime, end_datetime)
    
    def _get_mock_busy_times(self, start_datetime: datetime, end_datetime: datetime) -> List[Tuple[datetime, datetime]]:
        """Generate mock busy times for demo purposes"""
        busy_times = []
        current_date = start_datetime.date()
        end_date = end_datetime.date()
        
        while current_date <= end_date:
            # Skip weekends
            if current_date.weekday() < 5:  # Monday = 0, Friday = 4
                # Add some sample meetings
                if current_date.weekday() == 4:  # Friday
                    # Add a 6 PM flight (mentioned in the conversation)
                    flight_start = datetime.combine(current_date, datetime.min.time().replace(hour=18, minute=0))
                    flight_end = datetime.combine(current_date, datetime.min.time().replace(hour=20, minute=0))
                    # Make timezone aware if start_datetime is timezone aware
                    if start_datetime.tzinfo:
                        flight_start = self.timezone.localize(flight_start)
                        flight_end = self.timezone.localize(flight_end)
                    busy_times.append((flight_start, flight_end))
                
                # Add some regular meetings
                meeting1_start = datetime.combine(current_date, datetime.min.time().replace(hour=10, minute=0))
                meeting1_end = datetime.combine(current_date, datetime.min.time().replace(hour=11, minute=0))
                if start_datetime.tzinfo:
                    meeting1_start = self.timezone.localize(meeting1_start)
                    meeting1_end = self.timezone.localize(meeting1_end)
                busy_times.append((meeting1_start, meeting1_end))
                
                meeting2_start = datetime.combine(current_date, datetime.min.time().replace(hour=14, minute=0))
                meeting2_end = datetime.combine(current_date, datetime.min.time().replace(hour=15, minute=30))
                if start_datetime.tzinfo:
                    meeting2_start = self.timezone.localize(meeting2_start)
                    meeting2_end = self.timezone.localize(meeting2_end)
                busy_times.append((meeting2_start, meeting2_end))
            
            current_date += timedelta(days=1)
        
        return busy_times
    
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
                    slot = TimeSlot(current_time, slot_end)
                    available_slots.append(slot)
            
            # Move past this busy time
            current_time = max(current_time, busy_end + timedelta(minutes=buffer_minutes))
        
        # Check if there's time left at the end of the day
        if current_time < day_end:
            gap_duration = int((day_end - current_time).total_seconds() / 60)
            if gap_duration >= duration_minutes:
                # Create a slot exactly for the meeting duration
                slot_end = current_time + timedelta(minutes=duration_minutes)
                slot = TimeSlot(current_time, slot_end)
                available_slots.append(slot)
        
        return available_slots
    
    async def create_event(self, event: CalendarEvent) -> Optional[str]:
        """Create a new calendar event"""
        try:
            if not self.service:
                # Mock mode - simulate event creation
                import uuid
                event_id = f"mock_event_{uuid.uuid4().hex[:8]}"
                logger.info(f"Mock event created: {event.summary} at {event.start_time} (ID: {event_id})")
                return event_id
            
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
        self.calendar_service = GoogleCalendarService()
        self.user_timezone = pytz.timezone('UTC')  # Will be set based on user preference
    
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
                               date_range_days: int = 7) -> List[TimeSlot]:
        """Find available meeting slots based on user preferences"""
        try:
            # Parse preferred date/time or use defaults
            if preferred_date and preferred_time:
                start_datetime = dateparser.parse(f"{preferred_date} {preferred_time}")
                end_datetime = start_datetime + timedelta(days=1)
            elif preferred_date:
                start_datetime = dateparser.parse(preferred_date)
                start_datetime = start_datetime.replace(hour=9, minute=0)
                end_datetime = start_datetime.replace(hour=17, minute=0)
            else:
                # Default to next 7 days
                start_datetime = datetime.now() + timedelta(hours=1)  # Start from next hour
                end_datetime = start_datetime + timedelta(days=date_range_days)
            
            # Make timezone aware if needed
            if start_datetime.tzinfo is None:
                start_datetime = self.user_timezone.localize(start_datetime)
            if end_datetime.tzinfo is None:
                end_datetime = self.user_timezone.localize(end_datetime)
            
            slots = await self.calendar_service.find_available_slots(
                duration_minutes=duration_minutes,
                start_date=start_datetime,
                end_date=end_datetime
            )
            
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
                start_date = self.user_timezone.localize(start_date)
            if end_date.tzinfo is None:
                end_date = self.user_timezone.localize(end_date)
            
            event = await self.calendar_service.get_event_by_name(
                event_name, start_date, end_date
            )
            
            return event
            
        except Exception as e:
            logger.error(f"Error finding existing event: {e}")
            return None 