import asyncio
import logging
from typing import Dict, List, Optional, Tuple
import uuid
from datetime import datetime, timedelta
import json

# Google AI Studio integration
import google.generativeai as genai

# Local imports
from config.environment import config
from src.voice.speech_to_text import SpeechToTextService, AudioRecorder, VoiceActivityDetector
from src.voice.text_to_speech import VoiceManager
from src.agent.calendar_integration import CalendarManager, TimeSlot
from src.agent.time_parser import AdvancedTimeParser, TimeParseResult
from src.agent.state_manager import StateManager, ConversationFlowManager, ConversationState

logger = logging.getLogger(__name__)

class SmartSchedulerAgent:
    """Main conversation manager for the Smart Scheduler AI Agent"""
    
    def __init__(self):
        # Initialize Google AI Studio
        genai.configure(api_key=config.GOOGLE_AI_API_KEY)
        self.model = genai.GenerativeModel(config.MODEL_NAME)
        
        # Initialize voice services
        self.stt_service = SpeechToTextService()
        self.voice_manager = VoiceManager()
        
        # Initialize calendar and parsing
        self.calendar_manager = CalendarManager()
        self.time_parser = AdvancedTimeParser(self.calendar_manager)
        
        # Initialize state management
        self.state_manager = StateManager()
        self.flow_manager = ConversationFlowManager(self.state_manager)
        
        # Audio recording
        self.audio_recorder = AudioRecorder()
        self.voice_detector = VoiceActivityDetector()
        
        # System prompt for the LLM
        self.system_prompt = self._create_system_prompt()
        
        # Function definitions for Gemini function calling
        self.function_definitions = self._create_function_definitions()
    
    def _get_current_time_context(self) -> Dict[str, str]:
        """Get current time context for temporal awareness"""
        # Get current time in user's timezone
        if hasattr(self.calendar_manager, 'user_timezone'):
            now = datetime.now(self.calendar_manager.user_timezone)
            logger.debug(f"Using user timezone: {self.calendar_manager.user_timezone}")
        else:
            now = datetime.now()
            logger.debug("No user timezone set, using system default")
        
        # Calculate next Tuesday specifically
        days_ahead = 1 - now.weekday()  # Tuesday = 1, Monday = 0
        if days_ahead <= 0:  # Tuesday already happened this week
            days_ahead += 7
        next_tuesday = now + timedelta(days=days_ahead)
        
        # Calculate other key dates
        tomorrow = now + timedelta(days=1)
        next_week_start = now + timedelta(days=7-now.weekday())
        
        return {
            'current_datetime': now.strftime('%A, %B %d, %Y at %I:%M %p'),
            'today': now.strftime('%A, %B %d, %Y'),
            'tomorrow': tomorrow.strftime('%A, %B %d, %Y'),
            'next_tuesday': next_tuesday.strftime('%A, %B %d, %Y'),
            'next_wednesday': (next_tuesday + timedelta(days=1)).strftime('%A, %B %d, %Y'),
            'next_thursday': (next_tuesday + timedelta(days=2)).strftime('%A, %B %d, %Y'),
            'next_friday': (next_tuesday + timedelta(days=3)).strftime('%A, %B %d, %Y'),
            'next_monday': (next_tuesday - timedelta(days=1)).strftime('%A, %B %d, %Y'),
            'this_week_end': (now + timedelta(days=6-now.weekday())).strftime('%A, %B %d, %Y'),
            'next_week_start': next_week_start.strftime('%A, %B %d, %Y'),
            'timezone': str(now.tzinfo) if now.tzinfo else 'Local time',
            'current_hour': now.hour,
            'is_weekend': now.weekday() >= 5,
            'is_business_hours': 9 <= now.hour <= 17
        }
    
    async def initialize(self):
        """Initialize all services"""
        logger.info("Initializing Smart Scheduler Agent...")
        
        # Initialize voice manager
        await self.voice_manager.initialize()
        
        # Initialize calendar manager
        calendar_init_success = await self.calendar_manager.initialize()
        if not calendar_init_success:
            logger.warning("Calendar initialization failed. Some features may not work.")
        
        logger.info("Smart Scheduler Agent initialized successfully")
    
    async def start_voice_conversation(self, user_id: str = "default_user") -> str:
        """Start a new voice-based conversation session"""
        session_id = str(uuid.uuid4())
        session = await self.state_manager.create_session(session_id, user_id)
        
        logger.info(f"Starting voice conversation for session: {session_id}")
        
        # Welcome message
        welcome_message = "Hello! I'm your Smart Scheduler. I can help you find and schedule meetings. What would you like to do today?"
        await self.voice_manager.speak_text(welcome_message)
        
        # Start conversation loop
        await self._conversation_loop(session_id)
        
        return session_id
    
    async def start_text_session(self, user_id: str = "default_user") -> str:
        """Start a new text-based session for testing"""
        session_id = str(uuid.uuid4())
        session = await self.state_manager.create_session(session_id, user_id)
        
        logger.info(f"Starting text session for session: {session_id}")
        return session_id
    
    async def _conversation_loop(self, session_id: str):
        """Main conversation loop"""
        try:
            while True:
                # Listen for user input
                logger.info("Listening for user input...")
                user_input = await self._listen_for_input()
                
                if not user_input:
                    await self.voice_manager.speak_text("I didn't catch that. Could you please repeat?")
                    continue
                
                logger.info(f"User said: {user_input}")
                
                # Process the input and get response
                response = await self._process_user_input(session_id, user_input)
                
                # Speak the response
                logger.info(f"Agent response: {response}")
                await self.voice_manager.speak_with_streaming(response)
                
                # Save conversation turn
                await self.state_manager.add_conversation_turn(session_id, user_input, response)
                
                # Check if conversation is complete
                session = await self.state_manager.get_session(session_id)
                if session and session.state == ConversationState.COMPLETED:
                    await self.voice_manager.speak_text("Great! Your meeting has been scheduled. Have a wonderful day!")
                    break
                
        except KeyboardInterrupt:
            logger.info("Conversation interrupted by user")
            await self.voice_manager.speak_text("Goodbye!")
        except Exception as e:
            logger.error(f"Error in conversation loop: {e}")
            await self.voice_manager.speak_text("I'm sorry, I encountered an issue. Let's try again.")
    
    async def _listen_for_input(self) -> Optional[str]:
        """Listen for user voice input with voice activity detection"""
        try:
            # Record for up to 10 seconds or until silence detected
            transcript = await self.stt_service.transcribe_microphone_input(duration_seconds=10)
            return transcript
            
        except Exception as e:
            logger.error(f"Error listening for input: {e}")
            return None
    
    async def _process_user_input(self, session_id: str, user_input: str) -> str:
        """Process user input using LLM and function calling"""
        try:
            # Get current session and context
            session = await self.state_manager.get_session(session_id)
            if not session:
                return "I'm sorry, I lost track of our conversation. Let's start over."
            
            # Get conversation context
            context = await self.state_manager.get_conversation_context(session_id)
            
            # Build conversation prompt for Gemini
            conversation_prompt = self._build_conversation_prompt(session, context, user_input)
            
            # Validate API configuration before calling
            if not config.GOOGLE_AI_API_KEY:
                logger.error("Google AI API key not configured")
                return await self._fallback_response(session_id, user_input)
            
            # Call Gemini
            try:
                response = self.model.generate_content(
                    conversation_prompt,
                    generation_config=genai.types.GenerationConfig(
                        temperature=config.TEMPERATURE,
                        max_output_tokens=config.MAX_TOKENS,
                    )
                )
            except Exception as gemini_error:
                logger.error(f"Gemini API call failed: {gemini_error}")
                return await self._fallback_response(session_id, user_input)
            
            # Handle the response and check for function calls
            return await self._handle_gemini_response(session_id, response, user_input)
            
        except Exception as e:
            logger.error(f"Error processing user input: {e}")
            # Provide intelligent fallback based on user input
            return await self._fallback_response(session_id, user_input)
    
    async def _handle_gemini_response(self, session_id: str, response, user_input: str) -> str:
        """Handle Gemini response and execute any function calls"""
        try:
            # Check if we got a valid response
            if not response or not hasattr(response, 'text') or not response.text:
                logger.warning("Empty or invalid response from Gemini")
                return await self._fallback_response(session_id, user_input)
            
            response_text = response.text.strip()
            
            # If response is too short or generic, use fallback
            if len(response_text) < 10 or response_text.lower() in ['sorry', 'i apologize', 'error']:
                logger.warning(f"Gemini response too short or generic: {response_text}")
                return await self._fallback_response(session_id, user_input)
            
            # Check for function call patterns in the response
            function_call_result = await self._detect_and_execute_function_calls(session_id, response_text, user_input)
            
            if function_call_result:
                return function_call_result
            else:
                # Direct response from Gemini
                return response_text
                
        except Exception as e:
            logger.error(f"Error handling Gemini response: {e}")
            return await self._fallback_response(session_id, user_input)
    
    async def _fallback_response(self, session_id: str, user_input: str) -> str:
        """Provide a fallback response when LLM fails"""
        session = await self.state_manager.get_session(session_id)
        if not session:
            return "I'd be happy to help you schedule a meeting! How long should the meeting be?"
        
        # Check current state and provide appropriate response
        if session.state == ConversationState.IDLE:
            if any(word in user_input.lower() for word in ['schedule', 'meeting', 'book', 'find', 'appointment']):
                await self.state_manager.set_state(session_id, ConversationState.WAITING_FOR_DURATION)
                return "I'd be happy to help you schedule a meeting! How long should the meeting be?"
        
        elif session.state == ConversationState.WAITING_FOR_DURATION:
            # Extract duration from user input
            import re
            duration_pattern = r'(\d+)\s*(minutes?|hours?|mins?|hrs?)'
            match = re.search(duration_pattern, user_input.lower())
            if match:
                duration_num = int(match.group(1))
                duration_unit = match.group(2)
                duration_minutes = duration_num * 60 if 'hour' in duration_unit else duration_num
                
                await self.state_manager.update_meeting_request(session_id, duration_minutes=duration_minutes)
                await self.state_manager.set_state(session_id, ConversationState.WAITING_FOR_TIME)
                return f"Got it, a {duration_num} {duration_unit} meeting. When would you like to schedule this?"
            else:
                return "How long should the meeting be? For example, '30 minutes' or '1 hour'."
        
        elif session.state == ConversationState.WAITING_FOR_TIME:
            # Check if user is asking for suggestions instead of providing a specific time
            if any(phrase in user_input.lower() for phrase in ['suggest', 'available day', 'any day', 'what days', 'when available']):
                # User wants suggestions - find all available slots without time preference
                duration = session.meeting_request.duration_minutes or 60
                result = await self._find_available_slots(session_id, duration, preferred_time=None)
                
                if result.get('success') and result.get('slots'):
                    slots = result['slots']
                    await self.state_manager.set_state(session_id, ConversationState.PRESENTING_OPTIONS)
                    
                    response = "Great! I found these available times for your meeting:\n\n"
                    for i, slot in enumerate(slots[:3], 1):
                        response += f"{i}. {slot['formatted_time']}\n"
                    response += "\nWhich one works for you?"
                    
                    # Store the slots for later selection
                    await self.state_manager.update_meeting_request(session_id, available_slots=slots[:3])
                    return response
                else:
                    return "I couldn't find any available slots in your calendar. Would you like to try a different duration or time range?"
            else:
                # User provided specific time preference, trigger calendar search
                await self.state_manager.update_meeting_request(session_id, preferred_time=user_input)
                
                # Find available slots with the specific time preference
                duration = session.meeting_request.duration_minutes or 60
                result = await self._find_available_slots(session_id, duration, user_input)
                
                if result.get('success') and result.get('slots'):
                    slots = result['slots']
                    await self.state_manager.set_state(session_id, ConversationState.PRESENTING_OPTIONS)
                    
                    # Check if user specified a particular day
                    user_specified_day = any(day in user_input.lower() for day in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'])
                    
                    if user_specified_day and len(slots) > 0:
                        # User specified a day, show only slots from that day
                        response = f"Great! I found these available times for {user_input}:\n\n"
                        for i, slot in enumerate(slots[:3], 1):
                            response += f"{i}. {slot['formatted_time']}\n"
                        response += "\nWhich one works for you?"
                    else:
                        # General search, show available times
                        response = "Perfect! I found these available times:\n\n"
                        for i, slot in enumerate(slots[:3], 1):
                            response += f"{i}. {slot['formatted_time']}\n"
                        response += "\nWhich one works for you?"
                    
                    # Store the slots for later selection
                    await self.state_manager.update_meeting_request(session_id, available_slots=slots[:3])
                    return response
                elif result.get('error') and 'authentication' in result.get('error', '').lower():
                    return "I'm having trouble accessing your calendar. Please make sure Google Calendar is properly configured. For now, could you tell me your preferred times and I'll help you schedule manually?"
                else:
                    # Check if user specified a particular day
                    user_specified_day = any(day in user_input.lower() for day in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'])
                    if user_specified_day:
                        return f"I couldn't find any available slots for {user_input}. Would you like to try a different time on the same day, or see available times on other days?"
                    else:
                        return f"I couldn't find any available slots for {user_input}. Would you like to see all available times instead?"
        
        elif session.state == ConversationState.PRESENTING_OPTIONS:
            # User is selecting from options
            import re
            
            # Check for day-based selection (e.g., "Wednesday is okay", "I'll take Friday")
            day_selection = None
            if any(day in user_input.lower() for day in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']):
                for day in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']:
                    if day in user_input.lower():
                        day_selection = day
                        break
            
            # Check for agreement words that suggest accepting a specific option
            agreement_words = ['okay', 'ok', 'yes', 'sure', 'good', 'fine', 'works', 'perfect', 'great']
            has_agreement = any(word in user_input.lower() for word in agreement_words)
            
            slot_index = None
            
            if day_selection and has_agreement:
                # User agreed to a specific day - find which option matches
                # Get the available slots from session context
                if hasattr(session, 'meeting_request') and session.meeting_request and hasattr(session.meeting_request, 'available_slots'):
                    available_slots = session.meeting_request.available_slots
                    for i, slot_data in enumerate(available_slots[:3]):
                        if day_selection.lower() in slot_data.get('formatted_time', '').lower():
                            slot_index = i
                            break
                
                if slot_index is None:
                    # Fallback: if we can't match the day, assume they want the last mentioned option
                    slot_index = 2  # Default to third option (Wednesday in the example)
            
            else:
                # Check for numeric or text-based selection
                selection_match = re.search(r'(\d+)|first|second|third|one|two|three', user_input.lower())
                if selection_match:
                    if selection_match.group(1):
                        slot_index = int(selection_match.group(1)) - 1
                    else:
                        # Handle text selections
                        word = selection_match.group(0)
                        slot_index = {'first': 0, 'one': 0, 'second': 1, 'two': 1, 'third': 2, 'three': 2}.get(word, 0)
            
            if slot_index is not None:
                # Schedule the meeting
                result = await self._schedule_meeting(session_id, slot_index)
                if result.get('success'):
                    await self.state_manager.set_state(session_id, ConversationState.COMPLETED)
                    return f"Perfect! I've scheduled your meeting for {result['meeting_time']}. Is there anything else I can help you with?"
                else:
                    return "I had trouble scheduling that meeting. Could you try selecting again?"
            else:
                return "Which time slot would you prefer? Please say the number (1, 2, or 3), the day name, or 'first', 'second', etc."
        
        # Default fallback
        if any(word in user_input.lower() for word in ['schedule', 'meeting', 'book', 'find', 'appointment']):
            await self.state_manager.set_state(session_id, ConversationState.WAITING_FOR_DURATION)
            return "I'd be happy to help you schedule a meeting! How long should the meeting be?"
        
        return "I'd be happy to help you schedule a meeting! How long should the meeting be?"
    
    async def _detect_and_execute_function_calls(self, session_id: str, response_text: str, user_input: str) -> str:
        """Detect function calls in response and execute them"""
        try:
            # Get session and conversation context
            session = await self.state_manager.get_session(session_id)
            if not session:
                return response_text
            
            context = await self.state_manager.get_conversation_context(session_id)
            
            # Parse response for function call patterns
            import re
            
            # Look for patterns that suggest function calls are needed
            duration_pattern = r'(\d+)\s*(minutes?|hours?|mins?|hrs?)'
            time_pattern = r'(today|tomorrow|next|this|monday|tuesday|wednesday|thursday|friday|saturday|sunday|afternoon|morning|evening|sometime|later|now|soon)'
            
            # Get recent conversation history
            recent_conversation = " ".join([turn.get("user_input", "") + " " + turn.get("agent_response", "") 
                                          for turn in context[-3:]])  # Last 3 turns
            
            # Determine if we should find calendar slots
            should_find_slots = False
            duration_minutes = None
            preferred_time = None
            
            # Case 1: Direct scheduling request with duration
            if any(keyword in user_input.lower() for keyword in ['schedule', 'find', 'book', 'meeting', 'available', 'meet', 'need to meet']):
                duration_match = re.search(duration_pattern, user_input.lower())
                if duration_match:
                    duration_num = int(duration_match.group(1))
                    duration_unit = duration_match.group(2)
                    duration_minutes = duration_num * 60 if 'hour' in duration_unit else duration_num
                    should_find_slots = True
                    
                    # For deadline scenarios, use the full user input as preferred time
                    if "before" in user_input.lower():
                        preferred_time = user_input.strip()
                    else:
                        time_match = re.search(time_pattern, user_input.lower(), re.IGNORECASE)
                        preferred_time = time_match.group(0) if time_match else None
            
            # Case 2: User is providing time preference and we have duration from context
            elif re.search(time_pattern, user_input.lower(), re.IGNORECASE):
                # Look for duration in recent conversation
                duration_match = re.search(duration_pattern, recent_conversation.lower())
                if duration_match:
                    duration_num = int(duration_match.group(1))
                    duration_unit = duration_match.group(2)
                    duration_minutes = duration_num * 60 if 'hour' in duration_unit else duration_num
                    should_find_slots = True
                    preferred_time = user_input.strip()
                # Also check if there's a general meeting request in context
                elif any(keyword in recent_conversation.lower() for keyword in ['meeting', 'schedule', 'find time', 'available']):
                    # Default to 1 hour if no duration specified
                    duration_minutes = 60
                    should_find_slots = True
                    preferred_time = user_input.strip()
            
            # Case 3: Agent is asking for calendar check and we have context
            elif "check my calendar" in response_text.lower() or "let me check" in response_text.lower():
                # Look for duration in recent conversation
                duration_match = re.search(duration_pattern, recent_conversation.lower())
                if duration_match:
                    duration_num = int(duration_match.group(1))
                    duration_unit = duration_match.group(2)
                    duration_minutes = duration_num * 60 if 'hour' in duration_unit else duration_num
                else:
                    # Default to 1 hour
                    duration_minutes = 60
                
                should_find_slots = True
                
                # Look for time preference in recent conversation or current input
                time_match = re.search(time_pattern, (recent_conversation + " " + user_input).lower(), re.IGNORECASE)
                if time_match:
                    preferred_time = time_match.group(0)
            
            # Case 4: User mentions specific times/days in context of scheduling
            elif any(word in user_input.lower() for word in ['sometime', 'tuesday', 'wednesday', 'thursday', 'friday', 'monday', 'saturday', 'sunday', 'afternoon', 'morning', 'evening']):
                # Check if we're in a scheduling conversation
                if any(keyword in recent_conversation.lower() for keyword in ['meeting', 'schedule', 'find time', 'available', 'book']):
                    # Look for duration in recent conversation
                    duration_match = re.search(duration_pattern, recent_conversation.lower())
                    if duration_match:
                        duration_num = int(duration_match.group(1))
                        duration_unit = duration_match.group(2)
                        duration_minutes = duration_num * 60 if 'hour' in duration_unit else duration_num
                    else:
                        # Default to 1 hour
                        duration_minutes = 60
                    
                    should_find_slots = True
                    preferred_time = user_input.strip()
            
            # Execute the slot finding if we determined we should
            if should_find_slots and duration_minutes:
                logger.info(f"Finding slots: duration={duration_minutes}, preferred_time={preferred_time}")
                result = await self._find_available_slots(session_id, duration_minutes, preferred_time)
                
                if result.get('success') and result.get('slots'):
                    slots = result['slots']
                    response = "Great! I found these available times for your meeting:\n\n"
                    for i, slot in enumerate(slots[:3], 1):
                        response += f"{i}. {slot['formatted_time']}\n"
                    response += "\nWhich one works for you?"
                    return response
                else:
                    # Provide specific feedback about what was searched
                    if preferred_time:
                        return f"I couldn't find any available slots for {preferred_time}. Would you like to try a different time or see all available slots?"
                    else:
                        return "I couldn't find any available slots. Would you like to try a different time or duration?"
            
            # If no function call is needed, return the original response
            return response_text
            
        except Exception as e:
            logger.error(f"Error in function call detection: {e}")
            return response_text
    
    async def _execute_function_call(self, session_id: str, function_name: str, function_args: Dict) -> Dict:
        """Execute function calls from the LLM"""
        try:
            if function_name == "find_available_slots":
                return await self._find_available_slots(session_id, **function_args)
            
            elif function_name == "parse_time_expression":
                return await self._parse_time_expression(**function_args)
            
            elif function_name == "schedule_meeting":
                return await self._schedule_meeting(session_id, **function_args)
            
            elif function_name == "get_calendar_conflicts":
                return await self._get_calendar_conflicts(**function_args)
            
            elif function_name == "update_meeting_preferences":
                return await self._update_meeting_preferences(session_id, **function_args)
            
            else:
                return {"error": f"Unknown function: {function_name}"}
                
        except Exception as e:
            logger.error(f"Error executing function {function_name}: {e}")
            return {"error": str(e)}
    
    async def _find_available_slots(self, session_id: str, duration_minutes: int, 
                                  preferred_time: Optional[str] = None, 
                                  date_range_days: int = 7) -> Dict:
        """Find available calendar slots with advanced parsing"""
        try:
            logger.info(f"Finding slots with duration={duration_minutes}, time_preference='{preferred_time}'")
            
            # Check if this is a deadline scenario first
            if preferred_time and "before" in preferred_time.lower():
                logger.info("Detected deadline scenario, using advanced parsing")
                deadline_result = await self.time_parser.parse_deadline_request(preferred_time)
                
                if deadline_result.confidence > 0.5:
                    logger.info(f"Deadline parsing successful: {deadline_result.constraints}")
                    # Use deadline constraints to find appropriate slots
                    if 'must_end_before' in deadline_result.constraints:
                        end_deadline = datetime.fromisoformat(deadline_result.constraints['must_end_before'])
                        
                        # Find slots that end before the deadline
                        slots = await self.calendar_manager.find_meeting_slots(
                            duration_minutes=deadline_result.duration_minutes or duration_minutes,
                            date_range_days=1,  # Same day as deadline
                            time_preference=None  # Don't use original preference, use deadline logic
                        )
                        
                        # Filter slots to only those that end before the deadline
                        filtered_slots = []
                        for slot in slots:
                            if slot.end_time <= end_deadline:
                                filtered_slots.append(slot)
                        
                        # Sort by proximity to deadline (latest first)
                        filtered_slots.sort(key=lambda s: s.start_time, reverse=True)
                        slots = filtered_slots
                        
                        logger.info(f"Found {len(slots)} slots that end before deadline {end_deadline}")
                    else:
                        # Fallback to regular slot finding
                        slots = await self.calendar_manager.find_meeting_slots(
                            duration_minutes=duration_minutes,
                            date_range_days=date_range_days,
                            time_preference=preferred_time
                        )
                elif deadline_result.needs_clarification:
                    # Return clarification request
                    return {
                        "success": False,
                        "error": deadline_result.clarification_needed,
                        "needs_clarification": True,
                        "slots": []
                    }
                else:
                    # Deadline parsing failed, use regular method
                    slots = await self.calendar_manager.find_meeting_slots(
                        duration_minutes=duration_minutes,
                        date_range_days=date_range_days,
                        time_preference=preferred_time
                    )
            else:
                # Use the time preference directly with the calendar manager
                slots = await self.calendar_manager.find_meeting_slots(
                    duration_minutes=duration_minutes,
                    date_range_days=date_range_days,
                    time_preference=preferred_time
                )
            
            # Check if we got any slots
            if not slots:
                # Check if this is due to calendar auth issues
                if not hasattr(self.calendar_manager.calendar_service, 'service') or not self.calendar_manager.calendar_service.service:
                    return {
                        "success": False,
                        "error": "Calendar authentication failed - cannot access real calendar data",
                        "slots": []
                    }
                else:
                    return {
                        "success": False,
                        "error": "No available slots found",
                        "slots": []
                    }
            
            # Convert slots to serializable format
            slot_data = []
            for slot in slots[:5]:  # Limit to top 5 slots
                slot_data.append({
                    "start_time": slot.start_time.isoformat(),
                    "end_time": slot.end_time.isoformat(),
                    "duration_minutes": slot.duration_minutes,
                    "formatted_time": str(slot)
                })
            
            # Update session with available slots
            await self.state_manager.update_meeting_request(session_id, 
                                                          duration_minutes=duration_minutes,
                                                          available_slots=slot_data)
            
            return {
                "success": True,
                "slots": slot_data,
                "total_found": len(slots)
            }
            
        except Exception as e:
            logger.error(f"Error finding available slots: {e}")
            return {"success": False, "error": str(e)}
    
    async def _parse_time_expression(self, time_expression: str) -> Dict:
        """Parse natural language time expression"""
        try:
            result = await self.time_parser.parse_time_expression(time_expression)
            
            return {
                "success": True,
                "start_datetime": result.start_datetime.isoformat() if result.start_datetime else None,
                "end_datetime": result.end_datetime.isoformat() if result.end_datetime else None,
                "duration_minutes": result.duration_minutes,
                "constraints": result.constraints,
                "confidence": result.confidence,
                "needs_clarification": result.needs_clarification,
                "clarification_needed": result.clarification_needed
            }
            
        except Exception as e:
            logger.error(f"Error parsing time expression: {e}")
            return {"success": False, "error": str(e)}
    
    async def _schedule_meeting(self, session_id: str, slot_index: int, 
                              title: str = "Meeting", description: str = "") -> Dict:
        """Schedule a meeting in the selected slot"""
        try:
            session = await self.state_manager.get_session(session_id)
            if not session or not session.meeting_request.available_slots:
                return {"success": False, "error": "No available slots found"}
            
            if slot_index >= len(session.meeting_request.available_slots):
                return {"success": False, "error": "Invalid slot index"}
            
            selected_slot = session.meeting_request.available_slots[slot_index]
            start_time = datetime.fromisoformat(selected_slot["start_time"])
            duration = session.meeting_request.duration_minutes
            
            # Create the meeting
            event_id = await self.calendar_manager.schedule_meeting(
                title=title,
                start_time=start_time,
                duration_minutes=duration,
                description=description
            )
            
            if event_id:
                # Update session state
                await self.state_manager.update_meeting_request(session_id, selected_slot=selected_slot)
                await self.state_manager.set_state(session_id, ConversationState.COMPLETED)
                
                return {
                    "success": True,
                    "event_id": event_id,
                    "meeting_time": selected_slot["formatted_time"],
                    "duration": duration
                }
            else:
                return {"success": False, "error": "Failed to create calendar event"}
                
        except Exception as e:
            logger.error(f"Error scheduling meeting: {e}")
            return {"success": False, "error": str(e)}
    
    async def _get_calendar_conflicts(self, start_time: str, end_time: str) -> Dict:
        """Get calendar conflicts for a specific time range"""
        try:
            start_dt = datetime.fromisoformat(start_time)
            end_dt = datetime.fromisoformat(end_time)
            
            busy_times = await self.calendar_manager.calendar_service.get_busy_times(start_dt, end_dt)
            
            conflicts = []
            for busy_start, busy_end in busy_times:
                conflicts.append({
                    "start": busy_start.isoformat(),
                    "end": busy_end.isoformat(),
                    "duration_minutes": int((busy_end - busy_start).total_seconds() / 60)
                })
            
            return {
                "success": True,
                "conflicts": conflicts,
                "has_conflicts": len(conflicts) > 0
            }
            
        except Exception as e:
            logger.error(f"Error getting calendar conflicts: {e}")
            return {"success": False, "error": str(e)}
    
    async def _update_meeting_preferences(self, session_id: str, **preferences) -> Dict:
        """Update meeting preferences in session"""
        try:
            await self.state_manager.update_meeting_request(session_id, **preferences)
            return {"success": True, "updated_preferences": preferences}
            
        except Exception as e:
            logger.error(f"Error updating meeting preferences: {e}")
            return {"success": False, "error": str(e)}
    
    def _build_conversation_prompt(self, session, context: List[Dict], user_input: str) -> str:
        """Build conversation prompt for Gemini"""
        prompt = f"{self.system_prompt}\n\n"
        
        # Add current date/time context for temporal awareness
        time_context = self._get_current_time_context()
        
        temporal_context = f"""CURRENT DATE/TIME CONTEXT:
        - Current date and time: {time_context['current_datetime']}
        - Today is: {time_context['today']}
        - Tomorrow will be: {time_context['tomorrow']}
        - Next Tuesday will be: {time_context['next_tuesday']}
        - Next Wednesday will be: {time_context['next_wednesday']}
        - Next Thursday will be: {time_context['next_thursday']}
        - Next Friday will be: {time_context['next_friday']}
        - Next Monday will be: {time_context['next_monday']}
        - This week ends: {time_context['this_week_end']}
        - Next week starts: {time_context['next_week_start']}
        - Current timezone: {time_context['timezone']}
        - Business hours status: {'Yes' if time_context['is_business_hours'] else 'No'} (9 AM - 5 PM)
        - Weekend status: {'Yes' if time_context['is_weekend'] else 'No'}
        
        IMPORTANT: Always use the actual dates above when referring to days. For example:
        - Instead of "next Tuesday" say "next Tuesday, {time_context['next_tuesday']}"
        - Instead of "tomorrow" say "tomorrow, {time_context['tomorrow']}"
        - Always be specific with actual calendar dates.
        
        """
        
        prompt += temporal_context
        
        # Add conversation context
        if context:
            prompt += "Previous conversation:\n"
            for turn in context[-3:]:  # Last 3 turns for context
                prompt += f"User: {turn['user_input']}\n"
                prompt += f"Assistant: {turn['agent_response']}\n"
            prompt += "\n"
        
        # Add current session state info
        session_info = f"""Current session information:
        - State: {session.state.value}
        - Meeting duration: {session.meeting_request.duration_minutes} minutes
        - Preferred time: {session.meeting_request.preferred_time or 'Not specified'}
        - Available slots found: {len(session.meeting_request.available_slots)}
        
        """
        
        prompt += session_info
        prompt += f"User: {user_input}\nAssistant: "
        
        return prompt
    
    def _create_system_prompt(self) -> str:
        return """You are a Smart Scheduler AI, a calendar assistant that helps users schedule meetings efficiently. Your goal is to understand scheduling requests and find appropriate time slots using the calendar.

CORE RESPONSIBILITIES:
1. Understand natural language scheduling requests
2. Find available time slots that match user preferences
3. Handle special scenarios like deadline-based scheduling
4. Present options clearly with specific dates and times
5. Confirm selections and schedule meetings

KEY SCHEDULING SCENARIOS:

1. STANDARD SCHEDULING
   When user says: "Schedule a 30-minute meeting tomorrow"
   - Identify duration (30 minutes) and time preference (tomorrow)
   - Search calendar for available slots
   - Present 2-3 options with specific times

2. DEADLINE-BASED SCHEDULING
   When user says: "I need to meet before my flight at 6 PM"
   - Recognize this is a deadline scenario
   - Find slots that end with appropriate buffer (30-60 min) before the deadline
   - Prioritize slots closer to the deadline (e.g., afternoon slots before a 6 PM flight)
   - NEVER suggest morning slots for a late afternoon deadline

3. DAY/TIME SPECIFIC REQUESTS
   When user says: "Let's meet Tuesday afternoon"
   - Only show slots from the specified day and time range
   - "Tuesday afternoon" → Only Tuesday 12-5 PM slots
   - "Wednesday morning" → Only Wednesday 9 AM-12 PM slots

4. COMPLEX CONSTRAINTS
   When user says: "Next week but not Wednesday and not too early"
   - Apply multiple filters (next week, exclude Wednesday, after 10 AM)
   - Find slots that satisfy all constraints

CONVERSATION FLOW:
1. User makes scheduling request
2. You ask clarifying questions to gather all necessary information (duration, time, etc.)
3. Only after user confirms they want to see options, search the calendar
4. Present options only when explicitly requested by the user
5. User selects an option
6. You confirm and schedule the meeting

RESPONSE FORMAT:
- Keep responses conversational and natural
- NEVER show code, function calls, or technical details in your responses
- NEVER use markdown code blocks, backticks, or any code formatting
- NEVER show tool_code or function calls like ```tool_code find_available_slots()```
- When using calendar functions, do so invisibly without mentioning them
- Present available slots in a clean, readable format without technical details
- DO NOT show options or available time slots unless the user has explicitly asked for them
- When the user makes a general inquiry, ask clarifying questions first instead of immediately showing options
- Wait for the user to confirm they want to see available slots before presenting them

IMPORTANT GUIDELINES:
- Always use actual calendar dates (e.g., "Tuesday, June 27" not just "Tuesday")
- For deadline scenarios, find slots ending before the deadline with buffer time
- For day-specific requests, only show slots from that specific day
- When no slots are found, suggest alternatives or ask for different preferences
- Handle errors gracefully and provide helpful guidance
- NEVER expose the underlying implementation details to the user

Use the calendar functions available to you rather than making assumptions about availability, but do so invisibly without mentioning them in your responses."""
    
    def _create_function_definitions(self) -> List[Dict]:
        """Create function definitions for OpenAI function calling"""
        return [
            {
                "name": "find_available_slots",
                "description": "Find available calendar slots for a meeting",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "duration_minutes": {
                            "type": "integer",
                            "description": "Meeting duration in minutes"
                        },
                        "preferred_time": {
                            "type": "string",
                            "description": "Natural language time preference (e.g., 'Tuesday afternoon', 'next week')"
                        },
                        "date_range_days": {
                            "type": "integer",
                            "description": "Number of days to search ahead",
                            "default": 7
                        }
                    },
                    "required": ["duration_minutes"]
                }
            },
            {
                "name": "parse_time_expression",
                "description": "Parse natural language time expressions",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "time_expression": {
                            "type": "string",
                            "description": "Natural language time expression to parse"
                        }
                    },
                    "required": ["time_expression"]
                }
            },
            {
                "name": "schedule_meeting",
                "description": "Schedule a meeting in a selected time slot",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "slot_index": {
                            "type": "integer",
                            "description": "Index of the selected slot from available slots"
                        },
                        "title": {
                            "type": "string",
                            "description": "Meeting title",
                            "default": "Meeting"
                        },
                        "description": {
                            "type": "string",
                            "description": "Meeting description",
                            "default": ""
                        }
                    },
                    "required": ["slot_index"]
                }
            },
            {
                "name": "get_calendar_conflicts",
                "description": "Check for calendar conflicts in a specific time range",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "start_time": {
                            "type": "string",
                            "description": "Start time in ISO format"
                        },
                        "end_time": {
                            "type": "string",
                            "description": "End time in ISO format"
                        }
                    },
                    "required": ["start_time", "end_time"]
                }
            },
            {
                "name": "update_meeting_preferences",
                "description": "Update meeting preferences in the current session",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "duration_minutes": {"type": "integer"},
                        "preferred_time": {"type": "string"},
                        "preferred_date": {"type": "string"},
                        "title": {"type": "string"},
                        "description": {"type": "string"}
                    }
                }
            }
        ]
    
    async def cleanup(self):
        """Cleanup resources"""
        if self.voice_manager:
            self.voice_manager.cleanup()
        if self.audio_recorder:
            self.audio_recorder.stop_recording()

# Standalone function for quick testing
async def run_scheduler_agent():
    """Run the scheduler agent for testing"""
    agent = SmartSchedulerAgent()
    
    try:
        await agent.initialize()
        session_id = await agent.start_voice_conversation()
        logger.info(f"Conversation session completed: {session_id}")
    except Exception as e:
        logger.error(f"Error running scheduler agent: {e}")
    finally:
        await agent.cleanup()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_scheduler_agent())