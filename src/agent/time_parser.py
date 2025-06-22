import re
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
import dateparser
import pytz
from dateutil.relativedelta import relativedelta
from src.agent.calendar_integration import CalendarManager, CalendarEvent

logger = logging.getLogger(__name__)

class TimeParseResult:
    """Result of time parsing operation"""
    
    def __init__(self, 
                 start_datetime: Optional[datetime] = None,
                 end_datetime: Optional[datetime] = None,
                 duration_minutes: Optional[int] = None,
                 constraints: Optional[Dict] = None,
                 confidence: float = 0.0,
                 needs_clarification: bool = False,
                 clarification_needed: str = ""):
        self.start_datetime = start_datetime
        self.end_datetime = end_datetime
        self.duration_minutes = duration_minutes
        self.constraints = constraints or {}
        self.confidence = confidence
        self.needs_clarification = needs_clarification
        self.clarification_needed = clarification_needed

class AdvancedTimeParser:
    """Advanced time parser for natural language time expressions"""
    
    def __init__(self, calendar_manager: CalendarManager):
        self.calendar_manager = calendar_manager
        # Use local timezone for better day/date alignment
        import tzlocal
        try:
            self.timezone = tzlocal.get_localzone()
        except:
            # Fallback to a common timezone if local detection fails
            self.timezone = pytz.timezone('America/New_York')
        
        # Time pattern regex
        self.patterns = {
            'relative_time': [
                r'next\s+(?P<unit>week|month|tuesday|wednesday|thursday|friday|monday|saturday|sunday)',
                r'this\s+(?P<unit>week|month|tuesday|wednesday|thursday|friday|monday|saturday|sunday)',
                r'(?P<num>\d+)\s+(?P<unit>days?|weeks?|months?)\s+(?P<direction>from now|later|after)',
                r'(?P<direction>before|after)\s+(?P<num>\d+)\s+(?P<unit>days?|weeks?|months?)',
            ],
            'contextual_time': [
                r'(?P<duration>\d+)\s+(?P<unit>minutes?|hours?)\s+(?P<context>before|after)\s+(?P<event>.*)',
                r'(?P<context>before|after)\s+(?P<event>.*)',
                r'(?P<num>\d+)\s+(?P<unit>days?|hours?)\s+(?P<context>before|after)\s+(?P<event>.*)',
            ],
            'constraint_time': [
                r'not\s+(?P<constraint>too early|too late|on\s+\w+)',
                r'(?P<constraint>morning|afternoon|evening|night)',
                r'(?P<constraint>after\s+\d+|before\s+\d+)',
                r'(?P<constraint>weekday|weekend)',
            ],
            'specific_time': [
                r'(?P<date>\w+\s+\d+(?:st|nd|rd|th)?)',
                r'(?P<time>\d+:\d+\s*(?:AM|PM|am|pm)?)',
                r'(?P<relative>today|tomorrow|yesterday)',
            ]
        }
    
    async def parse_time_expression(self, text: str) -> TimeParseResult:
        """Parse a natural language time expression"""
        text = text.lower().strip()
        
        # Try different parsing strategies
        result = await self._parse_relative_time(text)
        if result.confidence > 0.7:
            return result
        
        result = await self._parse_contextual_time(text)
        if result.confidence > 0.7:
            return result
        
        result = await self._parse_constraint_time(text)
        if result.confidence > 0.5:
            return result
        
        result = await self._parse_specific_time(text)
        if result.confidence > 0.5:
            return result
        
        # Fallback to dateparser
        result = await self._fallback_parse(text)
        return result
    
    async def _parse_relative_time(self, text: str) -> TimeParseResult:
        """Parse relative time expressions like 'next week', 'in 3 days'"""
        for pattern in self.patterns['relative_time']:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    groups = match.groupdict()
                    now = datetime.now(self.timezone)
                    
                    if 'unit' in groups:
                        unit = groups['unit']
                        if unit in ['week', 'weeks']:
                            if 'next' in text:
                                start_time = now + timedelta(weeks=1)
                                end_time = start_time + timedelta(days=7)
                            elif 'this' in text:
                                start_time = now
                                end_time = now + timedelta(days=7)
                            else:
                                start_time = now
                                end_time = now + timedelta(weeks=1)
                        
                        elif unit in ['month', 'months']:
                            if 'next' in text:
                                start_time = now + relativedelta(months=1)
                                end_time = start_time + relativedelta(months=1)
                            else:
                                start_time = now
                                end_time = now + relativedelta(months=1)
                        
                        elif unit.lower() in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']:
                            weekday = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'].index(unit.lower())
                            days_ahead = weekday - now.weekday()
                            
                            # Handle "this" vs "next" context
                            if 'this' in text:
                                if days_ahead <= 0:  # Day already happened this week
                                    days_ahead += 7
                            elif 'next' in text:
                                if days_ahead <= 0:  # Always go to next week
                                    days_ahead += 7
                                else:  # Even if day hasn't happened this week, go to next week
                                    days_ahead += 7
                            else:
                                # Default behavior - if day already passed, go to next week
                                if days_ahead <= 0:
                                    days_ahead += 7
                            
                            start_time = now + timedelta(days=days_ahead)
                            end_time = start_time + timedelta(hours=8)  # 8-hour window
                        
                        return TimeParseResult(
                            start_datetime=start_time,
                            end_datetime=end_time,
                            constraints={},
                            confidence=0.8
                        )
                    
                    if 'num' in groups and 'unit' in groups:
                        num = int(groups['num'])
                        unit = groups['unit'].rstrip('s')  # Remove plural
                        direction = groups.get('direction', 'from now')
                        
                        if unit == 'day':
                            delta = timedelta(days=num)
                        elif unit == 'week':
                            delta = timedelta(weeks=num)
                        elif unit == 'month':
                            delta = relativedelta(months=num)
                        else:
                            continue
                        
                        if 'before' in direction:
                            start_time = now - delta
                        else:
                            start_time = now + delta
                        
                        end_time = start_time + timedelta(hours=8)
                        
                        return TimeParseResult(
                            start_datetime=start_time,
                            end_datetime=end_time,
                            constraints={},
                            confidence=0.8
                        )
                        
                except Exception as e:
                    logger.error(f"Error parsing relative time: {e}")
                    continue
        
        return TimeParseResult(confidence=0.0)
    
    async def _parse_contextual_time(self, text: str) -> TimeParseResult:
        """Parse contextual time expressions like 'before my 5 PM meeting'"""
        for pattern in self.patterns['contextual_time']:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    groups = match.groupdict()
                    
                    if 'event' in groups:
                        event_description = groups['event'].strip()
                        
                        # Find the referenced event
                        reference_event = await self.calendar_manager.find_existing_event(event_description)
                        
                        if reference_event:
                            context = groups.get('context', '').lower()
                            duration = groups.get('duration')
                            unit = groups.get('unit', 'minutes')
                            
                            if context == 'before':
                                if duration:
                                    # "45 minutes before my flight"
                                    minutes = int(duration) if unit.startswith('minute') else int(duration) * 60
                                    end_time = reference_event.start_time - timedelta(minutes=15)  # Buffer
                                    start_time = end_time - timedelta(minutes=minutes)
                                else:
                                    # "before my flight" - default window
                                    end_time = reference_event.start_time - timedelta(minutes=30)
                                    start_time = end_time - timedelta(hours=4)  # 4-hour window
                            
                            elif context == 'after':
                                if duration:
                                    # "a day or two after the event"
                                    if 'day' in text:
                                        days = 1
                                        if 'two' in text or '2' in text:
                                            days = 2
                                        start_time = reference_event.end_time + timedelta(days=days)
                                        end_time = start_time + timedelta(hours=8)
                                    else:
                                        minutes = int(duration) if unit.startswith('minute') else int(duration) * 60
                                        start_time = reference_event.end_time + timedelta(minutes=15)  # Buffer
                                        end_time = start_time + timedelta(minutes=minutes)
                                else:
                                    # "after my event" - default window
                                    start_time = reference_event.end_time + timedelta(minutes=30)
                                    end_time = start_time + timedelta(hours=4)
                            
                            return TimeParseResult(
                                start_datetime=start_time,
                                end_datetime=end_time,
                                constraints={'reference_event': reference_event.summary},
                                confidence=0.9
                            )
                        else:
                            # Event not found, needs clarification
                            return TimeParseResult(
                                needs_clarification=True,
                                clarification_needed=f"I couldn't find an event matching '{event_description}' in your calendar. Could you provide more details or check the event name?",
                                confidence=0.3
                            )
                        

                    
                except Exception as e:
                    logger.error(f"Error parsing contextual time: {e}")
                    continue
        
        return TimeParseResult(confidence=0.0)
    
    async def _parse_constraint_time(self, text: str) -> TimeParseResult:
        """Parse time constraints like 'not too early', 'afternoon'"""
        constraints = {}
        confidence = 0.0
        
        for pattern in self.patterns['constraint_time']:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                constraint = match.group('constraint').lower()
                
                if constraint == 'morning':
                    constraints['time_range'] = (6, 12)
                    confidence = 0.6
                elif constraint == 'afternoon':
                    constraints['time_range'] = (12, 18)
                    confidence = 0.6
                elif constraint == 'evening':
                    constraints['time_range'] = (18, 22)
                    confidence = 0.6
                elif constraint == 'night':
                    constraints['time_range'] = (22, 6)
                    confidence = 0.6
                elif 'too early' in constraint:
                    constraints['not_before'] = 9  # Not before 9 AM
                    confidence = 0.5
                elif 'too late' in constraint:
                    constraints['not_after'] = 18  # Not after 6 PM
                    confidence = 0.5
                elif constraint == 'weekday':
                    constraints['weekdays_only'] = True
                    confidence = 0.5
                elif constraint == 'weekend':
                    constraints['weekends_only'] = True
                    confidence = 0.5
        
        # Check for day exclusions
        if 'not on' in text or 'not' in text:
            for day in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']:
                if day in text.lower():
                    if 'excluded_days' not in constraints:
                        constraints['excluded_days'] = []
                    constraints['excluded_days'].append(day)
                    confidence = max(confidence, 0.6)
        
        if constraints:
            # Create a default time range if we have constraints
            now = datetime.now(self.timezone)
            start_time = now + timedelta(hours=1)
            end_time = start_time + timedelta(days=7)
            
            return TimeParseResult(
                start_datetime=start_time,
                end_datetime=end_time,
                constraints=constraints,
                confidence=confidence
            )
        
        return TimeParseResult(confidence=0.0)
    
    async def _parse_specific_time(self, text: str) -> TimeParseResult:
        """Parse specific time expressions"""
        text_lower = text.lower()
        now = datetime.now(self.timezone) if self.timezone else datetime.now()
        
        # Handle specific relative terms
        if 'today' in text_lower:
            start_time = now.replace(hour=9, minute=0, second=0, microsecond=0)
            end_time = now.replace(hour=17, minute=0, second=0, microsecond=0)
            return TimeParseResult(
                start_datetime=start_time,
                end_datetime=end_time,
                confidence=0.9
            )
        
        if 'tomorrow' in text_lower:
            tomorrow = now + timedelta(days=1)
            start_time = tomorrow.replace(hour=9, minute=0, second=0, microsecond=0)
            end_time = tomorrow.replace(hour=17, minute=0, second=0, microsecond=0)
            return TimeParseResult(
                start_datetime=start_time,
                end_datetime=end_time,
                confidence=0.9
            )
        
        # Use dateparser for other specific dates and times
        parsed_date = dateparser.parse(text, settings={'TIMEZONE': str(self.timezone)})
        
        if parsed_date:
            # If only date is specified, assume business hours
            if parsed_date.hour == 0 and parsed_date.minute == 0:
                start_time = parsed_date.replace(hour=9)
                end_time = parsed_date.replace(hour=17)
            else:
                start_time = parsed_date
                end_time = parsed_date + timedelta(hours=1)
            
            return TimeParseResult(
                start_datetime=start_time,
                end_datetime=end_time,
                confidence=0.7
            )
        
        return TimeParseResult(confidence=0.0)
    
    async def _fallback_parse(self, text: str) -> TimeParseResult:
        """Fallback parsing using dateparser"""
        try:
            parsed = dateparser.parse(text, settings={'TIMEZONE': str(self.timezone)})
            if parsed:
                return TimeParseResult(
                    start_datetime=parsed,
                    end_datetime=parsed + timedelta(hours=1),
                    confidence=0.4
                )
        except Exception as e:
            logger.error(f"Fallback parsing failed: {e}")
        
        return TimeParseResult(
            needs_clarification=True,
            clarification_needed="I couldn't understand the time you mentioned. Could you please specify it differently?",
            confidence=0.0
        )
    
    async def parse_duration(self, text: str) -> Optional[int]:
        """Parse duration from text and return minutes"""
        duration_patterns = [
            r'(?P<num>\d+)\s*(?P<unit>minutes?|mins?|hours?|hrs?)',
            r'(?P<num>\d+)\s*(?P<unit>h|m)',
            r'(?P<fraction>half|quarter)\s*(?P<unit>hour|day)',
            r'(?P<num>\d+\.?\d*)\s*(?P<unit>hours?|hrs?)',
        ]
        
        text = text.lower()
        
        for pattern in duration_patterns:
            match = re.search(pattern, text)
            if match:
                groups = match.groupdict()
                
                if 'fraction' in groups:
                    fraction = groups['fraction']
                    unit = groups['unit']
                    
                    if fraction == 'half':
                        if unit == 'hour':
                            return 30
                        elif unit == 'day':
                            return 480  # 8 hours
                    elif fraction == 'quarter':
                        if unit == 'hour':
                            return 15
                        elif unit == 'day':
                            return 120  # 2 hours
                
                if 'num' in groups and 'unit' in groups:
                    try:
                        num = float(groups['num'])
                        unit = groups['unit']
                        
                        if unit.startswith('minute') or unit == 'min' or unit == 'mins' or unit == 'm':
                            return int(num)
                        elif unit.startswith('hour') or unit == 'hr' or unit == 'hrs' or unit == 'h':
                            return int(num * 60)
                    except ValueError:
                        continue
        
        return None
    
    def apply_constraints_to_slots(self, slots: List, constraints: Dict) -> List:
        """Apply time constraints to filter available slots"""
        filtered_slots = []
        
        for slot in slots:
            # Check time range constraints
            if 'time_range' in constraints:
                start_hour, end_hour = constraints['time_range']
                slot_hour = slot.start_time.hour
                
                if not (start_hour <= slot_hour < end_hour):
                    continue
            
            # Check not_before constraint
            if 'not_before' in constraints:
                if slot.start_time.hour < constraints['not_before']:
                    continue
            
            # Check not_after constraint
            if 'not_after' in constraints:
                if slot.start_time.hour >= constraints['not_after']:
                    continue
            
            # Check weekday/weekend constraints
            if 'weekdays_only' in constraints and constraints['weekdays_only']:
                if slot.start_time.weekday() >= 5:  # Saturday = 5, Sunday = 6
                    continue
            
            if 'weekends_only' in constraints and constraints['weekends_only']:
                if slot.start_time.weekday() < 5:
                    continue
            
            # Check excluded days
            if 'excluded_days' in constraints:
                day_names = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
                slot_day = day_names[slot.start_time.weekday()]
                if slot_day in constraints['excluded_days']:
                    continue
            
            filtered_slots.append(slot)
        
        return filtered_slots
    
    async def parse_complex_request(self, text: str) -> Dict:
        """Parse complex scheduling requests with multiple constraints"""
        text_lower = text.lower()
        result = {
            'constraints': {},
            'preferences': {},
            'needs_clarification': False,
            'clarification_needed': '',
            'confidence': 0.0
        }
        
        # Handle "last weekday of month" scenarios
        if 'last weekday' in text_lower and 'month' in text_lower:
            now = datetime.now(self.timezone)
            # Find last weekday of current month
            last_day = (now.replace(day=1) + relativedelta(months=1)) - timedelta(days=1)
            while last_day.weekday() > 4:  # Skip weekends
                last_day -= timedelta(days=1)
            
            result['start_datetime'] = last_day.replace(hour=9, minute=0, second=0, microsecond=0)
            result['end_datetime'] = last_day.replace(hour=17, minute=0, second=0, microsecond=0)
            result['confidence'] = 0.9
            return result
        
        # Handle "usual sync-up" scenarios - requires memory/context
        if 'usual' in text_lower and ('sync' in text_lower or 'meeting' in text_lower):
            # Default to common meeting duration and suggest clarification
            result['duration_minutes'] = 30  # Default assumption
            result['needs_clarification'] = True
            result['clarification_needed'] = "I understand you want to schedule your usual meeting. How long is it typically, and do you have a preferred time?"
            result['confidence'] = 0.6
            return result
        
        # Handle complex evening scenarios with buffer requirements
        if 'evening' in text_lower and ('after' in text_lower or 'decompress' in text_lower):
            # Need to find last meeting of the day and add buffer
            now = datetime.now(self.timezone)
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
            
            # This would require querying calendar for last meeting
            result['constraints']['after_last_meeting'] = True
            result['constraints']['buffer_minutes'] = 60  # 1 hour to decompress
            result['constraints']['time_range'] = (19, 22)  # After 7 PM
            result['preferences']['minimum_start_time'] = '19:00'
            result['confidence'] = 0.7
            return result
        
        # Handle multiple negative constraints
        if 'not' in text_lower:
            excluded_days = []
            excluded_times = []
            
            # Parse excluded days
            for day in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']:
                if f'not on {day}' in text_lower or f'not {day}' in text_lower:
                    excluded_days.append(day)
            
            # Parse excluded time constraints
            if 'not too early' in text_lower:
                excluded_times.append('early_morning')
                result['constraints']['not_before'] = 9
            
            if excluded_days:
                result['constraints']['excluded_days'] = excluded_days
            if excluded_times:
                result['constraints']['excluded_times'] = excluded_times
            
            result['confidence'] = 0.6 if excluded_days or excluded_times else 0.0
        
        # Handle vague time preferences
        if 'sometime' in text_lower and 'next week' in text_lower:
            now = datetime.now(self.timezone)
            next_week_start = now + timedelta(days=7-now.weekday())
            next_week_end = next_week_start + timedelta(days=7)
            
            result['start_datetime'] = next_week_start.replace(hour=9, minute=0, second=0, microsecond=0)
            result['end_datetime'] = next_week_end.replace(hour=17, minute=0, second=0, microsecond=0)
            result['preferences']['flexible'] = True
            result['confidence'] = 0.5
        
        return result
    
    async def parse_deadline_request(self, text: str) -> TimeParseResult:
        """Parse requests with deadlines like 'before my flight that leaves Friday at 6 PM'"""
        text_lower = text.lower()
        
        # Extract deadline information
        deadline_patterns = [
            # "I need to meet for 45 minutes sometime before my flight that leaves on Friday at 6 PM"
            r'for\s+(?P<duration>\d+)\s+(?P<unit>minutes?|hours?)\s+.*?before\s+(?P<event>.*?)\s+(?:that\s+)?(?:leaves|starts|begins)\s+(?:on\s+)?(?P<day>\w+)\s+at\s+(?P<time>\d+(?::\d+)?\s*(?:am|pm))',
            # "before my flight that leaves Friday at 6 PM"
            r'before\s+(?P<event>.*?)\s+(?:that\s+)?(?:leaves|starts|begins)\s+(?:on\s+)?(?P<day>\w+)\s+at\s+(?P<time>\d+(?::\d+)?\s*(?:am|pm))',
            # "before my meeting on Friday at 6 PM"
            r'before\s+(?P<event>.*?)\s+(?:on\s+)?(?P<day>\w+)\s+at\s+(?P<time>\d+(?::\d+)?\s*(?:am|pm))',
            # "45 minutes before my flight"
            r'(?P<duration>\d+)\s+(?P<unit>minutes?|hours?)\s+before\s+(?P<event>.*)'
        ]
        
        for pattern in deadline_patterns:
            match = re.search(pattern, text_lower)
            if match:
                groups = match.groupdict()
                
                if 'day' in groups and 'time' in groups:
                    # Parse the deadline
                    day_name = groups['day']
                    time_str = groups['time']
                    event_name = groups['event']
                    
                    # Get duration from regex groups if available, otherwise extract from text
                    if 'duration' in groups and 'unit' in groups:
                        duration_num = int(groups['duration'])
                        duration_unit = groups['unit']
                        if duration_unit.startswith('hour'):
                            meeting_duration = duration_num * 60
                        else:
                            meeting_duration = duration_num
                    else:
                        # Extract meeting duration from original text
                        duration_match = re.search(r'(\d+)\s+(minutes?|hours?)', text)
                        if duration_match:
                            duration_num = int(duration_match.group(1))
                            duration_unit = duration_match.group(2)
                            
                            if duration_unit.startswith('hour'):
                                meeting_duration = duration_num * 60
                            else:
                                meeting_duration = duration_num
                        else:
                            meeting_duration = 60  # Default 1 hour
                    
                    # Find the specific day
                    now = datetime.now(self.timezone)
                    days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
                    
                    if day_name in days:
                        target_weekday = days.index(day_name)
                        days_ahead = target_weekday - now.weekday()
                        if days_ahead <= 0:  # If day already passed this week
                            days_ahead += 7
                        
                        deadline_date = now + timedelta(days=days_ahead)
                        
                        # Parse time
                        time_match = re.match(r'(\d+)(?::(\d+))?\s*(am|pm)?', time_str)
                        if time_match:
                            hour = int(time_match.group(1))
                            minute = int(time_match.group(2)) if time_match.group(2) else 0
                            ampm = time_match.group(3)
                            
                            if ampm == 'pm' and hour != 12:
                                hour += 12
                            elif ampm == 'am' and hour == 12:
                                hour = 0
                            
                            deadline_datetime = deadline_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
                            
                            # End time should be at least 30 minutes before deadline
                            end_time = deadline_datetime - timedelta(minutes=30)
                            start_time = end_time - timedelta(minutes=meeting_duration)
                            
                            # Expand search window backwards
                            search_start = deadline_datetime - timedelta(hours=8)  # 8 hours before deadline
                            
                            logger.info(f"Deadline parsing: Flight at {deadline_datetime}, meeting must end by {end_time}, duration {meeting_duration} min")
                            
                            return TimeParseResult(
                                start_datetime=search_start,
                                end_datetime=end_time,
                                duration_minutes=meeting_duration,
                                constraints={
                                    'deadline': deadline_datetime.isoformat(),
                                    'deadline_event': event_name,
                                    'must_end_before': end_time.isoformat()
                                },
                                confidence=0.9
                            )
                
                elif 'duration' in groups and 'event' in groups:
                    # Handle "45 minutes before my flight"
                    duration = int(groups['duration'])
                    unit = groups['unit']
                    event_name = groups['event']
                    
                    # Try to find the event in calendar
                    reference_event = await self.calendar_manager.find_existing_event(event_name)
                    
                    if reference_event:
                        if unit.startswith('hour'):
                            duration_minutes = duration * 60
                        else:
                            duration_minutes = duration
                        
                        end_time = reference_event.start_time - timedelta(minutes=15)  # Buffer
                        start_time = end_time - timedelta(minutes=duration_minutes)
                        
                        return TimeParseResult(
                            start_datetime=start_time,
                            end_datetime=end_time,
                            duration_minutes=duration_minutes,
                            constraints={
                                'reference_event': reference_event.summary,
                                'must_end_before': end_time.isoformat()
                            },
                            confidence=0.9
                        )
                    else:
                        return TimeParseResult(
                            needs_clarification=True,
                            clarification_needed=f"I couldn't find '{event_name}' in your calendar. Could you provide the specific date and time for this event?",
                            confidence=0.3
                        )
        
        return TimeParseResult(confidence=0.0) 