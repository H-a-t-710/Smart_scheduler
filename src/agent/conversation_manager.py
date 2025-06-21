import asyncio
import logging
from typing import Dict, List, Optional, Tuple
import uuid
from datetime import datetime
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
            
            # Call Gemini
            response = self.model.generate_content(
                conversation_prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=config.TEMPERATURE,
                    max_output_tokens=config.MAX_TOKENS,
                )
            )
            
            # Handle the response and check for function calls
            return await self._handle_gemini_response(session_id, response, user_input)
            
        except Exception as e:
            logger.error(f"Error processing user input: {e}")
            return "I'm sorry, I had trouble understanding that. Could you please try again?"
    
    async def _handle_gemini_response(self, session_id: str, response, user_input: str) -> str:
        """Handle Gemini response and execute any function calls"""
        try:
            response_text = response.text
            
            # Check for function call patterns in the response
            function_call_result = await self._detect_and_execute_function_calls(session_id, response_text, user_input)
            
            if function_call_result:
                return function_call_result
            else:
                # Direct response from Gemini
                return response_text
                
        except Exception as e:
            logger.error(f"Error handling Gemini response: {e}")
            return "I apologize, but I encountered an issue processing your request. Could you please try again?"
    
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
            time_pattern = r'(next|this|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday|afternoon|morning|evening|sometime)'
            
            # Get recent conversation history
            recent_conversation = " ".join([turn.get("user_input", "") + " " + turn.get("agent_response", "") 
                                          for turn in context[-3:]])  # Last 3 turns
            
            # Determine if we should find calendar slots
            should_find_slots = False
            duration_minutes = None
            preferred_time = None
            
            # Case 1: Direct scheduling request with duration
            if any(keyword in user_input.lower() for keyword in ['schedule', 'find', 'book', 'meeting', 'available']):
                duration_match = re.search(duration_pattern, user_input.lower())
                if duration_match:
                    duration_num = int(duration_match.group(1))
                    duration_unit = duration_match.group(2)
                    duration_minutes = duration_num * 60 if 'hour' in duration_unit else duration_num
                    should_find_slots = True
                    
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
                    return "I couldn't find any available slots for that time. Would you like to try a different time or duration?"
            
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
        """Find available calendar slots"""
        try:
            # Parse time preferences if provided
            if preferred_time:
                time_result = await self.time_parser.parse_time_expression(preferred_time)
                if time_result.confidence > 0.5:
                    # Use parsed time preferences
                    slots = await self.calendar_manager.find_meeting_slots(
                        duration_minutes=duration_minutes,
                        preferred_date=time_result.start_datetime.strftime("%Y-%m-%d") if time_result.start_datetime else None,
                        preferred_time=time_result.start_datetime.strftime("%H:%M") if time_result.start_datetime else None,
                        date_range_days=date_range_days
                    )
                    
                    # Apply constraints if any
                    if time_result.constraints:
                        slots = self.time_parser.apply_constraints_to_slots(slots, time_result.constraints)
                else:
                    # Fallback to basic search
                    slots = await self.calendar_manager.find_meeting_slots(
                        duration_minutes=duration_minutes,
                        date_range_days=date_range_days
                    )
            else:
                # Basic search without preferences
                slots = await self.calendar_manager.find_meeting_slots(
                    duration_minutes=duration_minutes,
                    date_range_days=date_range_days
                )
            
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
        """Create the system prompt for Gemini"""
        return """You are a Smart Scheduler AI Agent, a helpful assistant specialized in scheduling meetings and managing calendars. You have a warm, professional, and conversational tone.

PRIMARY RESPONSIBILITIES:
1. Help users find available time slots for meetings
2. Parse natural language time expressions and dates
3. Handle complex scheduling scenarios gracefully
4. Provide intelligent conflict resolution when slots are unavailable
5. Guide users through the scheduling process step by step

CORE CAPABILITIES:
- Advanced time parsing: "next Tuesday afternoon", "before my 5 PM meeting", "last weekday of the month"
- Real-time calendar integration and availability checking
- Smart conflict resolution with alternative suggestions
- Stateful conversation awareness across multiple turns
- Voice-optimized responses for natural conversation flow

CONVERSATION GUIDELINES:
- Always confirm important details before taking action
- Ask ONE clarifying question at a time when information is missing
- Provide helpful alternatives when conflicts arise
- Keep responses concise and natural for voice interaction
- Guide users through complex scenarios step by step
- Remember context from previous conversation turns

SCHEDULING PROCESS:
1. Determine meeting duration (ask if not provided)
2. Understand time preferences (parse natural language)
3. Check calendar availability
4. Present options clearly (max 3 options)
5. Confirm selection before creating event

RESPONSE FORMAT:
- Be conversational and friendly
- Use numbered lists for multiple options
- Acknowledge user preferences explicitly
- Provide clear next steps

Remember: This is a voice conversation, so responses should sound natural when spoken aloud."""
    
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