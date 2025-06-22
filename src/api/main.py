import asyncio
import logging
import sys
import os
from typing import Dict, Optional
import uuid
from contextlib import asynccontextmanager
import warnings

# Suppress RuntimeWarning from pydub.utils
warnings.filterwarnings("ignore", category=RuntimeWarning, module='pydub.utils')

# Add project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, UploadFile, File, Request
from fastapi.responses import HTMLResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import uvicorn

# Local imports
from config.environment import config
from src.agent.conversation_manager import SmartSchedulerAgent
from src.agent.state_manager import ConversationState

# Import the FFmpeg setup to ensure pydub is configured early
from config import ffmpeg_setup

# Setup logging
logging.basicConfig(
    level=logging.INFO if config.DEBUG else logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global agent instance
agent: Optional[SmartSchedulerAgent] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global agent
    
    # Startup
    logger.info("Starting Smart Scheduler Agent...")
    agent = SmartSchedulerAgent()
    
    try:
        await agent.initialize()
        logger.info("Smart Scheduler Agent initialized successfully")
        yield
    except Exception as e:
        logger.error(f"Failed to initialize agent: {e}")
        raise
    finally:
        # Shutdown
        if agent:
            await agent.cleanup()
        logger.info("Smart Scheduler Agent shutdown complete")

# Create FastAPI app
app = FastAPI(
    title="Smart Scheduler AI Agent",
    description="A voice-enabled AI agent for scheduling meetings with Google Calendar integration",
    version="1.0.0",
    lifespan=lifespan
)

# Pydantic models for API requests
class ScheduleRequest(BaseModel):
    user_input: str
    session_id: Optional[str] = None
    user_id: str = "default_user"

class VoiceSessionRequest(BaseModel):
    user_id: str = "default_user"

class SessionResponse(BaseModel):
    session_id: str
    status: str
    message: str

class ConversationResponse(BaseModel):
    response: str
    session_id: str
    state: str
    needs_clarification: bool = False

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "Smart Scheduler AI Agent",
        "version": "1.0.0"
    }

# Session management endpoints
@app.post("/api/sessions", response_model=SessionResponse)
async def create_session(request: VoiceSessionRequest):
    """Create a new conversation session"""
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")
    
    try:
        session_id = str(uuid.uuid4())
        session = await agent.state_manager.create_session(session_id, request.user_id)
        
        return SessionResponse(
            session_id=session_id,
            status="created",
            message="New session created successfully"
        )
    except Exception as e:
        logger.error(f"Error creating session: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    """Get session information"""
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")
    
    try:
        session = await agent.state_manager.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        stats = await agent.state_manager.get_session_stats(session_id)
        return stats
    except Exception as e:
        logger.error(f"Error getting session: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a session"""
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")
    
    try:
        await agent.state_manager.clear_session(session_id)
        return {"status": "deleted", "session_id": session_id}
    except Exception as e:
        logger.error(f"Error deleting session: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Text-based conversation endpoint
@app.post("/api/chat", response_model=ConversationResponse)
async def text_chat(request: ScheduleRequest):
    """Process text-based conversation input"""
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")
    
    try:
        # Get or create session
        session_id = request.session_id
        if not session_id:
            session_id = str(uuid.uuid4())
            await agent.state_manager.create_session(session_id, request.user_id)
        
        # Process user input
        response = await agent._process_user_input(session_id, request.user_input)
        
        # Get current session state
        session = await agent.state_manager.get_session(session_id)
        current_state = session.state.value if session else ConversationState.IDLE.value
        
        # Save conversation turn
        await agent.state_manager.add_conversation_turn(session_id, request.user_input, response)
        
        return ConversationResponse(
            response=response,
            session_id=session_id,
            state=current_state,
            needs_clarification=False  # Could be enhanced based on state
        )
        
    except Exception as e:
        logger.error(f"Error processing chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Voice conversation endpoint
@app.post("/api/voice/start")
async def start_voice_conversation(request: VoiceSessionRequest):
    """Start a voice conversation session"""
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")
    
    try:
        # This would typically run in a separate process/thread
        # For demo purposes, we'll return session info
        session_id = str(uuid.uuid4())
        session = await agent.state_manager.create_session(session_id, request.user_id)
        
        return {
            "session_id": session_id,
            "status": "voice_ready",
            "message": "Voice session created. Use WebSocket connection for real-time interaction.",
            "websocket_url": f"/ws/{session_id}"
        }
        
    except Exception as e:
        logger.error(f"Error starting voice conversation: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# WebSocket for real-time voice interaction
@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for real-time conversation"""
    await websocket.accept()
    
    if not agent:
        await websocket.send_json({"error": "Agent not initialized"})
        await websocket.close()
        return
    
    try:
        # Get or create session
        session = await agent.state_manager.get_session(session_id)
        if not session:
            await websocket.send_json({"error": "Session not found"})
            await websocket.close()
            return
        
        # Send welcome message
        await websocket.send_json({
            "type": "message",
            "content": "Connected! Send me a message to start scheduling.",
            "session_id": session_id
        })
        
        while True:
            # Receive message from client
            data = await websocket.receive_json()
            
            if data.get("type") == "message":
                user_input = data.get("content", "")
                
                # Process the input
                response = await agent._process_user_input(session_id, user_input)
                
                # Send response back
                await websocket.send_json({
                    "type": "response",
                    "content": response,
                    "session_id": session_id
                })
                
                # Save conversation turn
                await agent.state_manager.add_conversation_turn(session_id, user_input, response)
                
                # Check if conversation is complete
                updated_session = await agent.state_manager.get_session(session_id)
                if updated_session and updated_session.state == ConversationState.COMPLETED:
                    await websocket.send_json({
                        "type": "status",
                        "content": "conversation_complete",
                        "session_id": session_id
                    })
            
            elif data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
                
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for session: {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await websocket.send_json({"error": str(e)})

# Calendar integration endpoints
@app.get("/api/calendar/slots")
async def get_available_slots(
    duration_minutes: int,
    preferred_time: Optional[str] = None,
    date_range_days: int = 7
):
    """Get available calendar slots"""
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")
    
    try:
        # Create temporary session for this request
        temp_session_id = str(uuid.uuid4())
        await agent.state_manager.create_session(temp_session_id, "api_user")
        
        # Find slots
        result = await agent._find_available_slots(
            temp_session_id, 
            duration_minutes, 
            preferred_time, 
            date_range_days
        )
        
        # Clean up temporary session
        await agent.state_manager.clear_session(temp_session_id)
        
        return result
        
    except Exception as e:
        logger.error(f"Error getting available slots: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/calendar/schedule")
async def schedule_meeting_api(
    session_id: str,
    slot_index: int,
    title: str = "Meeting",
    description: str = ""
):
    """Schedule a meeting via API"""
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")
    
    try:
        result = await agent._schedule_meeting(session_id, slot_index, title, description)
        return result
        
    except Exception as e:
        logger.error(f"Error scheduling meeting: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Static files for web interface
try:
    app.mount("/static", StaticFiles(directory="static"), name="static")
except:
    logger.warning("Static files directory not found")

# Simple web interface
@app.get("/", response_class=HTMLResponse)
async def web_interface():
    """Enhanced web interface with voice features"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Smart Scheduler AI Agent</title>
        <style>
            body { 
                font-family: Arial, sans-serif; 
                max-width: 800px; 
                margin: 0 auto; 
                padding: 20px; 
                background-color: #f5f5f5;
            }
            .header {
                text-align: center;
                margin-bottom: 30px;
                padding: 20px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border-radius: 10px;
            }
            .chat-container { 
                border: 1px solid #ddd; 
                height: 400px; 
                overflow-y: scroll; 
                padding: 15px; 
                margin: 10px 0; 
                background: white;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }
            .message { 
                margin: 15px 0; 
                padding: 10px;
                border-radius: 8px;
            }
            .user-message { 
                text-align: right; 
                background-color: #e3f2fd;
                margin-left: 50px;
            }
            .agent-message { 
                text-align: left; 
                background-color: #f1f8e9;
                margin-right: 50px;
            }
            .input-container {
                display: flex;
                gap: 10px;
                margin: 20px 0;
                align-items: center;
            }
            input[type="text"] { 
                flex: 1;
                padding: 12px; 
                border: 2px solid #ddd;
                border-radius: 25px;
                font-size: 16px;
            }
            input[type="text"]:focus {
                outline: none;
                border-color: #667eea;
            }
            button { 
                padding: 12px 20px; 
                margin: 5px; 
                border: none;
                border-radius: 25px;
                cursor: pointer;
                font-size: 16px;
                transition: all 0.3s;
            }
            .send-btn {
                background: #4CAF50;
                color: white;
            }
            .send-btn:hover {
                background: #45a049;
            }
            .clear-btn {
                background: #f44336;
                color: white;
            }
            .clear-btn:hover {
                background: #da190b;
            }
            .voice-btn {
                background: #2196F3;
                color: white;
                font-size: 20px;
                width: 60px;
                height: 60px;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            .voice-btn:hover {
                background: #1976D2;
            }
            .voice-btn.recording {
                background: #f44336;
                animation: pulse 1s infinite;
            }
            @keyframes pulse {
                0% { transform: scale(1); }
                50% { transform: scale(1.1); }
                100% { transform: scale(1); }
            }
            .voice-status {
                text-align: center;
                margin: 10px 0;
                font-style: italic;
                color: #666;
            }
            .examples {
                background: white;
                padding: 20px;
                border-radius: 10px;
                margin: 20px 0;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }
            .examples h3 {
                color: #333;
                margin-top: 0;
            }
            .examples ul {
                list-style-type: none;
                padding: 0;
            }
            .examples li {
                background: #f8f9fa;
                margin: 8px 0;
                padding: 10px;
                border-radius: 5px;
                border-left: 4px solid #667eea;
            }
            .status-indicator {
                display: inline-block;
                width: 10px;
                height: 10px;
                border-radius: 50%;
                margin-right: 8px;
            }
            .status-online { background-color: #4CAF50; }
            .status-offline { background-color: #f44336; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Smart Scheduler AI Agent</h1>
            <p><span id="voiceStatus" class="status-indicator status-offline"></span>Voice-Enabled Meeting Scheduler</p>
        </div>
        
        <div class="examples">
            <h3>Try these voice commands or type them:</h3>
            <ul>
                <li>"I need to schedule a 30-minute meeting for next Tuesday afternoon"</li>
                <li>"Find me an hour slot sometime next week"</li>
                <li>"Schedule a meeting before my 5 PM call on Friday"</li>
                <li>"What's available tomorrow morning?"</li>
            </ul>
        </div>
        
        <div class="chat-container" id="chatContainer">
            <div class="message agent-message">
                <strong>Agent:</strong> Hello! I'm your Smart Scheduler. I can help you find and schedule meetings using voice or text. What would you like to do today?
            </div>
        </div>
        
        <div class="voice-status" id="voiceStatusText">
            🎤 Click the microphone to start voice conversation
        </div>
        
        <div class="input-container">
            <button class="voice-btn" id="voiceBtn" onclick="toggleVoice()" title="Click to start/stop voice input">
                🎤
            </button>
            <input type="text" id="userInput" placeholder="Type your message here or use voice..." onkeypress="handleKeyPress(event)">
            <button class="send-btn" onclick="sendMessage()">Send</button>
            <button class="clear-btn" onclick="clearChat()">Clear</button>
        </div>
        
        <script>
            let sessionId = null;
            let isRecording = false;
            let mediaRecorder = null;
            let audioChunks = [];
            let websocket = null;
            
            // Initialize voice features
            async function initializeVoice() {
                try {
                    // Check if browser supports voice features
                    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                        document.getElementById('voiceStatusText').textContent = '❌ Voice not supported in this browser';
                        return false;
                    }
                    
                    // Test microphone access
                    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                    stream.getTracks().forEach(track => track.stop()); // Stop the test stream
                    
                    document.getElementById('voiceStatus').className = 'status-indicator status-online';
                    document.getElementById('voiceStatusText').textContent = '🎤 Voice ready - click microphone to start';
                    return true;
                } catch (error) {
                    console.error('Voice initialization failed:', error);
                    document.getElementById('voiceStatusText').textContent = '❌ Microphone access denied';
                    return false;
                }
            }
            
            // Toggle voice recording
            async function toggleVoice() {
                if (!isRecording) {
                    await startVoiceRecording();
                } else {
                    await stopVoiceRecording();
                }
            }
            
            // Start voice recording
            async function startVoiceRecording() {
                try {
                    const stream = await navigator.mediaDevices.getUserMedia({ 
                        audio: {
                            sampleRate: 16000,
                            channelCount: 1,
                            echoCancellation: true,
                            noiseSuppression: true
                        } 
                    });
                    
                    mediaRecorder = new MediaRecorder(stream, {
                        mimeType: 'audio/webm;codecs=opus'
                    });
                    
                    audioChunks = [];
                    
                    mediaRecorder.ondataavailable = (event) => {
                        if (event.data.size > 0) {
                            audioChunks.push(event.data);
                        }
                    };
                    
                    mediaRecorder.onstop = async () => {
                        const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
                        await processVoiceInput(audioBlob);
                        
                        // Stop all tracks
                        stream.getTracks().forEach(track => track.stop());
                    };
                    
                    mediaRecorder.start();
                    isRecording = true;
                    
                    document.getElementById('voiceBtn').classList.add('recording');
                    document.getElementById('voiceBtn').textContent = '⏹️';
                    document.getElementById('voiceStatusText').textContent = '🔴 Recording... Click to stop';
                    
                } catch (error) {
                    console.error('Failed to start recording:', error);
                    document.getElementById('voiceStatusText').textContent = '❌ Failed to start recording';
                }
            }
            
            // Stop voice recording
            async function stopVoiceRecording() {
                if (mediaRecorder && isRecording) {
                    mediaRecorder.stop();
                    isRecording = false;
                    
                    document.getElementById('voiceBtn').classList.remove('recording');
                    document.getElementById('voiceBtn').textContent = '🎤';
                    document.getElementById('voiceStatusText').textContent = '🔄 Processing voice input...';
                }
            }
            
            // Process voice input using backend STT service
            async function processVoiceInput(audioBlob) {
                try {
                    document.getElementById('voiceStatusText').textContent = '🔄 Converting speech to text...';
                    
                    // Create form data with audio file
                    const formData = new FormData();
                    formData.append('file', audioBlob, 'audio.webm');
                    
                    // Send audio to backend for processing
                    const response = await fetch('/api/voice/process', {
                        method: 'POST',
                        body: formData
                    });
                    
                    const result = await response.json();
                    
                    if (result.success && result.transcript) {
                        document.getElementById('voiceStatusText').textContent = '✅ Voice processed successfully';
                        
                        // Add the transcribed message to input and send
                        document.getElementById('userInput').value = result.transcript;
                        await sendMessage();
                        
                        // Reset status
                        setTimeout(() => {
                            document.getElementById('voiceStatusText').textContent = '🎤 Ready for next voice input';
                        }, 2000);
                    } else {
                        document.getElementById('voiceStatusText').textContent = '⚠️ No speech detected - try again';
                        setTimeout(() => {
                            document.getElementById('voiceStatusText').textContent = '🎤 Ready for next voice input';
                        }, 3000);
                    }
                    
                } catch (error) {
                    console.error('Voice processing failed:', error);
                    document.getElementById('voiceStatusText').textContent = '❌ Voice processing failed';
                    
                    // Fallback to simulated input for demo
                    setTimeout(async () => {
                        const fallbackMessage = "I need to schedule a meeting for tomorrow afternoon";
                        document.getElementById('userInput').value = fallbackMessage;
                        document.getElementById('voiceStatusText').textContent = '🎤 Using demo voice input';
                        await sendMessage();
                    }, 2000);
                }
            }
            
            // Send message function
            async function sendMessage() {
                const input = document.getElementById('userInput');
                const message = input.value.trim();
                if (!message) return;
                
                // Add user message to chat
                addMessage('user', message);
                input.value = '';
                
                try {
                    const response = await fetch('/api/chat', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            user_input: message,
                            session_id: sessionId,
                            user_id: 'web_user'
                        })
                    });
                    
                    const data = await response.json();
                    sessionId = data.session_id;
                    
                    // Add agent response to chat
                    addMessage('agent', data.response);
                    
                    // Speak the response if voice is enabled
                    if (window.speechSynthesis) {
                        const utterance = new SpeechSynthesisUtterance(data.response);
                        utterance.rate = 0.9;
                        utterance.pitch = 1.0;
                        window.speechSynthesis.speak(utterance);
                    }
                    
                } catch (error) {
                    addMessage('agent', 'Sorry, I encountered an error. Please try again.');
                    console.error('Error:', error);
                }
            }
            
            function addMessage(sender, message) {
                const chatContainer = document.getElementById('chatContainer');
                const messageDiv = document.createElement('div');
                messageDiv.className = `message ${sender}-message`;
                messageDiv.innerHTML = `<strong>${sender === 'user' ? 'You' : 'Agent'}:</strong> ${message}`;
                chatContainer.appendChild(messageDiv);
                chatContainer.scrollTop = chatContainer.scrollHeight;
            }
            
            function clearChat() {
                document.getElementById('chatContainer').innerHTML = `
                    <div class="message agent-message">
                        <strong>Agent:</strong> Hello! I'm your Smart Scheduler. I can help you find and schedule meetings using voice or text. What would you like to do today?
                    </div>
                `;
                sessionId = null;
            }
            
            function handleKeyPress(event) {
                if (event.key === 'Enter') {
                    sendMessage();
                }
            }
            
            // Initialize when page loads
            window.addEventListener('load', () => {
                initializeVoice();
            });
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

# Additional utility endpoints
@app.get("/api/status")
async def get_system_status():
    """Get system status"""
    if not agent:
        return {"status": "error", "message": "Agent not initialized"}
    
    try:
        active_sessions = await agent.state_manager.get_active_sessions()
        
        return {
            "status": "running",
            "agent_initialized": agent is not None,
            "active_sessions": len(active_sessions),
            "config": {
                "model": config.MODEL_NAME,
                "debug": config.DEBUG,
                "voice_enabled": True
            }
        }
    except Exception as e:
        logger.error(f"Error getting system status: {e}")
        return {"status": "error", "message": str(e)}

# Voice processing endpoints
@app.post("/api/voice/process")
async def process_voice_input(file: UploadFile = File(...)):
    """Process uploaded audio file and convert to text"""
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")
    
    try:
        # Save uploaded audio file temporarily
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as temp_file:
            content = await file.read()
            temp_file.write(content)
            temp_file_path = temp_file.name
        
        # Convert audio to text using STT service
        transcript = await agent.stt_service.transcribe_audio_file(temp_file_path)
        
        # Clean up temporary file
        os.unlink(temp_file_path)
        
        if transcript:
            return {
                "success": True,
                "transcript": transcript,
                "message": "Voice processed successfully"
            }
        else:
            return {
                "success": False,
                "transcript": "",
                "message": "No speech detected or processing failed"
            }
            
    except Exception as e:
        logger.error(f"Error processing voice input: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/voice/synthesize")
async def synthesize_speech(text: str):
    """Convert text to speech and return audio"""
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")
    
    try:
        # Generate speech audio
        audio_bytes = await agent.voice_manager.tts_service.synthesize_speech(text)
        
        if audio_bytes:
            return Response(
                content=audio_bytes,
                media_type="audio/mpeg",
                headers={"Content-Disposition": "attachment; filename=speech.mp3"}
            )
        else:
            raise HTTPException(status_code=500, detail="Speech synthesis failed")
            
    except Exception as e:
        logger.error(f"Error synthesizing speech: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    # Run the application
    uvicorn.run(
        "src.api.main:app",
        host=config.APP_HOST,
        port=config.APP_PORT,
        reload=config.DEBUG,
        log_level="info" if config.DEBUG else "warning"
    ) 