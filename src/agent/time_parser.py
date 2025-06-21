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
        self.timezone = pytz.timezone('UTC')  # Default, should be configurable
        
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
                            if days_ahead <= 0:  # Target day already happened this week
                                days_ahead += 7
                            
                            if 'next' in text:
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
                            context = groups.get('context', 'before')
                            duration = groups.get('duration', '1')
                            unit = groups.get('unit', 'hours')
                            
                            try:
                                duration_num = int(duration)
                            except ValueError:
                                duration_num = 1
                            
                            if unit.startswith('minute'):
                                delta = timedelta(minutes=duration_num)
                            else:
                                delta = timedelta(hours=duration_num)
                            
                            if context == 'before':
                                target_time = reference_event.start_time - delta
                            else:
                                target_time = reference_event.end_time + delta
                            
                            return TimeParseResult(
                                start_datetime=target_time,
                                end_datetime=target_time + timedelta(hours=2),
                                constraints={'reference_event': reference_event.summary},
                                confidence=0.9
                            )
                        else:
                            # Event not found, need clarification
                            return TimeParseResult(
                                needs_clarification=True,
                                clarification_needed=f"I couldn't find the event '{event_description}' in your calendar. Could you provide more details or a different time reference?",
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
        # Use dateparser for specific dates and times
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
        """Parse complex scheduling requests with multiple components"""
        result = {
            'duration': None,
            'time_preferences': None,
            'constraints': {},
            'needs_clarification': False,
            'clarification_needed': []
        }
        
        # Parse duration
        duration = await self.parse_duration(text)
        if duration:
            result['duration'] = duration
        else:
            result['needs_clarification'] = True
            result['clarification_needed'].append("How long should the meeting be?")
        
        # Parse time preferences
        time_result = await self.parse_time_expression(text)
        if time_result.confidence > 0.5:
            result['time_preferences'] = time_result
            result['constraints'].update(time_result.constraints)
        else:
            if time_result.needs_clarification:
                result['needs_clarification'] = True
                result['clarification_needed'].append(time_result.clarification_needed)
            else:
                result['needs_clarification'] = True
                result['clarification_needed'].append("When would you like to schedule the meeting?")
        
        return result 