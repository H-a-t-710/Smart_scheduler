import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

class ConversationState(Enum):
    """Enum for conversation states"""
    IDLE = "idle"
    WAITING_FOR_DURATION = "waiting_for_duration"
    WAITING_FOR_TIME = "waiting_for_time"
    PRESENTING_OPTIONS = "presenting_options"
    WAITING_FOR_SELECTION = "waiting_for_selection"
    CONFIRMING_DETAILS = "confirming_details"
    CREATING_EVENT = "creating_event"
    COMPLETED = "completed"
    ERROR = "error"

@dataclass
class MeetingRequest:
    """Data class for meeting request information"""
    duration_minutes: Optional[int] = None
    preferred_time: Optional[str] = None
    preferred_date: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    attendees: List[str] = None
    constraints: Dict[str, Any] = None
    available_slots: List[Dict] = None
    selected_slot: Optional[Dict] = None
    
    def __post_init__(self):
        if self.attendees is None:
            self.attendees = []
        if self.constraints is None:
            self.constraints = {}
        if self.available_slots is None:
            self.available_slots = []

@dataclass
class ConversationSession:
    """Data class for conversation session"""
    session_id: str
    user_id: str
    state: ConversationState
    meeting_request: MeetingRequest
    conversation_history: List[Dict[str, str]]
    created_at: datetime
    updated_at: datetime
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

class StateManager:
    """Manages conversation state and session persistence"""
    
    def __init__(self, database_path: str = "smart_scheduler.db"):
        self.database_path = database_path
        self.sessions: Dict[str, ConversationSession] = {}
        self._setup_database()
    
    def _setup_database(self):
        """Setup SQLite database for session persistence"""
        try:
            conn = sqlite3.connect(self.database_path)
            cursor = conn.cursor()
            
            # Create sessions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    meeting_request_json TEXT,
                    conversation_history_json TEXT,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP,
                    metadata_json TEXT
                )
            """)
            
            # Create conversation_turns table for detailed history
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversation_turns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    turn_number INTEGER NOT NULL,
                    user_input TEXT,
                    agent_response TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions (session_id)
                )
            """)
            
            conn.commit()
            conn.close()
            logger.info("Database setup completed")
            
        except Exception as e:
            logger.error(f"Error setting up database: {e}")
    
    async def create_session(self, session_id: str, user_id: str) -> ConversationSession:
        """Create a new conversation session"""
        session = ConversationSession(
            session_id=session_id,
            user_id=user_id,
            state=ConversationState.IDLE,
            meeting_request=MeetingRequest(),
            conversation_history=[],
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        self.sessions[session_id] = session
        await self._save_session(session)
        
        logger.info(f"Created new session: {session_id}")
        return session
    
    async def get_session(self, session_id: str) -> Optional[ConversationSession]:
        """Get session by ID"""
        if session_id in self.sessions:
            return self.sessions[session_id]
        
        # Try to load from database
        session = await self._load_session(session_id)
        if session:
            self.sessions[session_id] = session
        
        return session
    
    async def update_session(self, session: ConversationSession):
        """Update session state"""
        session.updated_at = datetime.now()
        self.sessions[session.session_id] = session
        await self._save_session(session)
    
    async def set_state(self, session_id: str, state: ConversationState):
        """Set conversation state"""
        session = await self.get_session(session_id)
        if session:
            session.state = state
            await self.update_session(session)
    
    async def update_meeting_request(self, session_id: str, **kwargs):
        """Update meeting request details"""
        session = await self.get_session(session_id)
        if session:
            for key, value in kwargs.items():
                if hasattr(session.meeting_request, key):
                    setattr(session.meeting_request, key, value)
            await self.update_session(session)
    
    async def add_conversation_turn(self, session_id: str, user_input: str, agent_response: str):
        """Add a conversation turn to history"""
        session = await self.get_session(session_id)
        if session:
            turn = {
                "timestamp": datetime.now().isoformat(),
                "user_input": user_input,
                "agent_response": agent_response
            }
            session.conversation_history.append(turn)
            await self.update_session(session)
            
            # Also save to database for detailed tracking
            await self._save_conversation_turn(session_id, len(session.conversation_history), 
                                             user_input, agent_response)
    
    async def get_conversation_context(self, session_id: str, last_n_turns: int = 5) -> List[Dict]:
        """Get recent conversation context"""
        session = await self.get_session(session_id)
        if session:
            return session.conversation_history[-last_n_turns:]
        return []
    
    async def clear_session(self, session_id: str):
        """Clear session data"""
        if session_id in self.sessions:
            del self.sessions[session_id]
        
        # Remove from database
        try:
            conn = sqlite3.connect(self.database_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            cursor.execute("DELETE FROM conversation_turns WHERE session_id = ?", (session_id,))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error clearing session from database: {e}")
    
    async def _save_session(self, session: ConversationSession):
        """Save session to database"""
        try:
            conn = sqlite3.connect(self.database_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT OR REPLACE INTO sessions 
                (session_id, user_id, state, meeting_request_json, conversation_history_json, 
                 created_at, updated_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                session.session_id,
                session.user_id,
                session.state.value,
                json.dumps(asdict(session.meeting_request)),
                json.dumps(session.conversation_history),
                session.created_at.isoformat(),
                session.updated_at.isoformat(),
                json.dumps(session.metadata)
            ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error saving session to database: {e}")
    
    async def _load_session(self, session_id: str) -> Optional[ConversationSession]:
        """Load session from database"""
        try:
            conn = sqlite3.connect(self.database_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,))
            row = cursor.fetchone()
            
            if row:
                session = ConversationSession(
                    session_id=row[0],
                    user_id=row[1],
                    state=ConversationState(row[2]),
                    meeting_request=MeetingRequest(**json.loads(row[3])),
                    conversation_history=json.loads(row[4]),
                    created_at=datetime.fromisoformat(row[5]),
                    updated_at=datetime.fromisoformat(row[6]),
                    metadata=json.loads(row[7]) if row[7] else {}
                )
                
                conn.close()
                return session
            
            conn.close()
            return None
            
        except Exception as e:
            logger.error(f"Error loading session from database: {e}")
            return None
    
    async def _save_conversation_turn(self, session_id: str, turn_number: int, 
                                    user_input: str, agent_response: str):
        """Save individual conversation turn to database"""
        try:
            conn = sqlite3.connect(self.database_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO conversation_turns 
                (session_id, turn_number, user_input, agent_response)
                VALUES (?, ?, ?, ?)
            """, (session_id, turn_number, user_input, agent_response))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error saving conversation turn: {e}")
    
    async def get_session_stats(self, session_id: str) -> Dict[str, Any]:
        """Get session statistics"""
        session = await self.get_session(session_id)
        if not session:
            return {}
        
        return {
            "session_id": session.session_id,
            "user_id": session.user_id,
            "state": session.state.value,
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat(),
            "conversation_turns": len(session.conversation_history),
            "meeting_request_complete": self._is_meeting_request_complete(session.meeting_request),
            "duration": session.meeting_request.duration_minutes,
            "has_available_slots": len(session.meeting_request.available_slots) > 0
        }
    
    def _is_meeting_request_complete(self, meeting_request: MeetingRequest) -> bool:
        """Check if meeting request has all required information"""
        return (
            meeting_request.duration_minutes is not None and
            (meeting_request.preferred_time is not None or 
             meeting_request.preferred_date is not None or
             len(meeting_request.available_slots) > 0)
        )
    
    async def get_active_sessions(self) -> List[str]:
        """Get list of active session IDs"""
        active_sessions = []
        
        try:
            conn = sqlite3.connect(self.database_path)
            cursor = conn.cursor()
            
            # Get sessions updated in the last 24 hours
            yesterday = (datetime.now() - timedelta(days=1)).isoformat()
            cursor.execute("""
                SELECT session_id FROM sessions 
                WHERE updated_at > ? AND state != ?
            """, (yesterday, ConversationState.COMPLETED.value))
            
            rows = cursor.fetchall()
            active_sessions = [row[0] for row in rows]
            
            conn.close()
            
        except Exception as e:
            logger.error(f"Error getting active sessions: {e}")
        
        return active_sessions
    
    async def cleanup_old_sessions(self, days_old: int = 7):
        """Clean up sessions older than specified days"""
        try:
            conn = sqlite3.connect(self.database_path)
            cursor = conn.cursor()
            
            cutoff_date = (datetime.now() - timedelta(days=days_old)).isoformat()
            
            # Delete old sessions
            cursor.execute("DELETE FROM sessions WHERE updated_at < ?", (cutoff_date,))
            cursor.execute("DELETE FROM conversation_turns WHERE session_id NOT IN (SELECT session_id FROM sessions)")
            
            deleted_count = cursor.rowcount
            conn.commit()
            conn.close()
            
            logger.info(f"Cleaned up {deleted_count} old sessions")
            
        except Exception as e:
            logger.error(f"Error cleaning up old sessions: {e}")

class ConversationFlowManager:
    """Manages conversation flow and state transitions"""
    
    def __init__(self, state_manager: StateManager):
        self.state_manager = state_manager
    
    async def handle_user_input(self, session_id: str, user_input: str) -> Tuple[str, ConversationState]:
        """Handle user input and determine next state and response"""
        session = await self.state_manager.get_session(session_id)
        if not session:
            return "I'm sorry, I couldn't find your session. Please start over.", ConversationState.IDLE
        
        current_state = session.state
        
        # State-specific handling
        if current_state == ConversationState.IDLE:
            return await self._handle_idle_state(session, user_input)
        elif current_state == ConversationState.WAITING_FOR_DURATION:
            return await self._handle_duration_state(session, user_input)
        elif current_state == ConversationState.WAITING_FOR_TIME:
            return await self._handle_time_state(session, user_input)
        elif current_state == ConversationState.PRESENTING_OPTIONS:
            return await self._handle_options_state(session, user_input)
        elif current_state == ConversationState.WAITING_FOR_SELECTION:
            return await self._handle_selection_state(session, user_input)
        elif current_state == ConversationState.CONFIRMING_DETAILS:
            return await self._handle_confirmation_state(session, user_input)
        else:
            return "I'm not sure how to help with that. Let's start over.", ConversationState.IDLE
    
    async def _handle_idle_state(self, session: ConversationSession, user_input: str) -> Tuple[str, ConversationState]:
        """Handle input when conversation is idle"""
        # Check if user wants to schedule a meeting
        if any(keyword in user_input.lower() for keyword in ['schedule', 'meeting', 'book', 'calendar']):
            await self.state_manager.set_state(session.session_id, ConversationState.WAITING_FOR_DURATION)
            return "I'd be happy to help you schedule a meeting! How long should the meeting be?", ConversationState.WAITING_FOR_DURATION
        else:
            return "Hello! I can help you schedule meetings. Just say something like 'I need to schedule a meeting' to get started.", ConversationState.IDLE
    
    async def _handle_duration_state(self, session: ConversationSession, user_input: str) -> Tuple[str, ConversationState]:
        """Handle duration input"""
        # This would integrate with the time parser
        # For now, simple parsing
        duration = self._extract_duration(user_input)
        if duration:
            await self.state_manager.update_meeting_request(session.session_id, duration_minutes=duration)
            await self.state_manager.set_state(session.session_id, ConversationState.WAITING_FOR_TIME)
            return f"Got it, {duration} minutes. When would you like to schedule this meeting?", ConversationState.WAITING_FOR_TIME
        else:
            return "I couldn't understand the duration. Please specify how long the meeting should be (e.g., '30 minutes', '1 hour').", ConversationState.WAITING_FOR_DURATION
    
    async def _handle_time_state(self, session: ConversationSession, user_input: str) -> Tuple[str, ConversationState]:
        """Handle time preference input"""
        # This would integrate with the time parser and calendar
        # For now, simple acknowledgment
        await self.state_manager.update_meeting_request(session.session_id, preferred_time=user_input)
        await self.state_manager.set_state(session.session_id, ConversationState.PRESENTING_OPTIONS)
        return "Let me check your calendar for available times...", ConversationState.PRESENTING_OPTIONS
    
    async def _handle_options_state(self, session: ConversationSession, user_input: str) -> Tuple[str, ConversationState]:
        """Handle when presenting options"""
        # This would present actual calendar options
        await self.state_manager.set_state(session.session_id, ConversationState.WAITING_FOR_SELECTION)
        return "I found these available times: 1) Tuesday 2:00 PM, 2) Wednesday 10:00 AM. Which one works for you?", ConversationState.WAITING_FOR_SELECTION
    
    async def _handle_selection_state(self, session: ConversationSession, user_input: str) -> Tuple[str, ConversationState]:
        """Handle time slot selection"""
        # Parse selection
        if '1' in user_input or 'tuesday' in user_input.lower():
            selected_slot = {"time": "Tuesday 2:00 PM", "datetime": "2024-01-16T14:00:00"}
        elif '2' in user_input or 'wednesday' in user_input.lower():
            selected_slot = {"time": "Wednesday 10:00 AM", "datetime": "2024-01-17T10:00:00"}
        else:
            return "Please select option 1 or 2.", ConversationState.WAITING_FOR_SELECTION
        
        await self.state_manager.update_meeting_request(session.session_id, selected_slot=selected_slot)
        await self.state_manager.set_state(session.session_id, ConversationState.CONFIRMING_DETAILS)
        return f"Perfect! I'll schedule a {session.meeting_request.duration_minutes}-minute meeting for {selected_slot['time']}. Should I go ahead and create this meeting?", ConversationState.CONFIRMING_DETAILS
    
    async def _handle_confirmation_state(self, session: ConversationSession, user_input: str) -> Tuple[str, ConversationState]:
        """Handle confirmation"""
        if any(word in user_input.lower() for word in ['yes', 'confirm', 'ok', 'sure']):
            await self.state_manager.set_state(session.session_id, ConversationState.CREATING_EVENT)
            return "Great! I'm creating the meeting now...", ConversationState.CREATING_EVENT
        else:
            await self.state_manager.set_state(session.session_id, ConversationState.WAITING_FOR_TIME)
            return "No problem. When would you prefer to schedule the meeting?", ConversationState.WAITING_FOR_TIME
    
    def _extract_duration(self, text: str) -> Optional[int]:
        """Simple duration extraction"""
        import re
        
        # Look for patterns like "30 minutes", "1 hour", etc.
        patterns = [
            r'(\d+)\s*(?:minutes?|mins?)',
            r'(\d+)\s*(?:hours?|hrs?)',
            r'(\d+)\s*h',
            r'(\d+)\s*m'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text.lower())
            if match:
                num = int(match.group(1))
                if 'hour' in pattern or 'h' in pattern:
                    return num * 60
                else:
                    return num
        
        return None 