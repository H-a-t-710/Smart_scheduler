# 🤖 Smart Scheduler AI Agent

A sophisticated voice-enabled AI agent that helps users find and schedule meetings through natural conversation, with advanced time parsing and Google Calendar integration.

## 🌟 Features

### Core Capabilities
- **Voice-Enabled Conversations**: Natural speech-to-speech interaction using separate TTS/STT services
- **Advanced Time Parsing**: Handles complex natural language expressions like:
  - "Next Tuesday afternoon"
  - "An hour before my 5 PM meeting on Friday"
  - "Sometime late next week, but not Wednesday"
  - "Last weekday of this month"
- **Smart Calendar Integration**: Real-time Google Calendar availability checking
- **Intelligent Conflict Resolution**: Suggests alternatives when requested times are unavailable
- **Stateful Conversations**: Maintains context across multiple conversation turns
- **Multi-Modal Interface**: Supports both voice and text interactions

### Technical Highlights
- **Advanced Voice Stack**: 
  - Speech-to-Text: ElevenLabs Scribe v1 (primary) with Google Cloud Speech fallback
  - Text-to-Speech: ElevenLabs with Google Cloud TTS fallback
- **LLM Integration**: Google Gemini Pro with intelligent function detection for tool orchestration
- **Advanced Architecture**: Modular design with clear separation of concerns
- **Session Management**: Persistent conversation state with SQLite storage
- **RESTful API**: Complete FastAPI-based web service with WebSocket support

## 🏗️ Architecture Overview

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   User Voice    │    │  Speech-to-Text │    │ Conversation    │
│     Input       │───▶│  (ElevenLabs)   │───▶│   Manager       │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                                        │
┌─────────────────┐    ┌─────────────────┐             │
│   Audio Output  │    │ Text-to-Speech  │             │
│   (Speakers)    │◀───│  (ElevenLabs)   │◀────────────┘
└─────────────────┘    └─────────────────┘
                                                        │
                       ┌─────────────────┐             │
                       │ Google Gemini   │◀────────────┤
                       │      Pro        │             │
                       └─────────────────┘             │
                                │                      │
        ┌─────────────────────────┼──────────────────────┘
        │                        │
        ▼                        ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ Time Parser     │    │ Calendar API    │    │ State Manager   │
│ (NLP + Logic)   │    │ (Google Cal)    │    │ (SQLite)        │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 📋 Prerequisites

Before setting up the Smart Scheduler, you'll need:

1. **Python 3.8+**
2. **ElevenLabs API Key** (for Speech-to-Text and Text-to-Speech)
3. **Google Cloud Account** (for fallback Speech-to-Text API)
4. **Google Calendar API Access**
5. **Google AI Studio API Key** (for Gemini Pro)
6. **Audio Input/Output** (microphone and speakers)

## 🚀 Installation & Setup

### 1. Clone the Repository

```bash
git clone <repository-url>
cd smart-scheduler-agent
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Set Up Google Cloud Services

#### Google Calendar API:
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Enable the Google Calendar API
4. Create credentials (OAuth 2.0 for web application)
5. Download the credentials JSON file as `credentials.json`

#### Google Cloud Speech-to-Text (Fallback):
1. Enable the Google Cloud Speech-to-Text API
2. Create a service account
3. Download the service account key as JSON
4. Set the path in environment variables

### 4. Set Up API Keys

Create a `.env` file in the root directory:

```env
# Google AI Studio Configuration
GOOGLE_AI_API_KEY=your_google_ai_studio_api_key_here

# ElevenLabs Configuration (for TTS and STT)
ELEVENLABS_API_KEY=your_elevenlabs_api_key_here
ELEVENLABS_VOICE_ID=your_preferred_voice_id

# Google Cloud Configuration (for fallback STT)
GOOGLE_APPLICATION_CREDENTIALS=path/to/your/service-account-key.json
GOOGLE_CLOUD_PROJECT_ID=your_google_cloud_project_id

# Google Calendar API
GOOGLE_CALENDAR_CREDENTIALS=credentials.json
GOOGLE_CALENDAR_TOKEN=token.json

# Application Configuration
APP_HOST=localhost
APP_PORT=8000
DEBUG=True

# Voice Configuration
DEFAULT_VOICE_LANGUAGE=en-US
AUDIO_SAMPLE_RATE=16000
AUDIO_CHUNK_SIZE=1024

# LLM Configuration
MODEL_NAME=gemini-pro
MAX_TOKENS=1000
TEMPERATURE=0.7
```

### 5. Initial Setup

```bash
# Install system dependencies (Ubuntu/Debian)
sudo apt-get update
sudo apt-get install portaudio19-dev python3-pyaudio

# For macOS
brew install portaudio

# For Windows
# PyAudio should install automatically with pip
```

## 🎯 Usage

### Option 1: Run the Web Interface

```bash
python src/api/main.py
```

Then open your browser to `http://localhost:8000` for a web-based chat interface.

### Option 2: Run Voice Conversation

```bash
python -m src.agent.conversation_manager
```

This starts a direct voice conversation in the terminal.

### Option 3: API Integration

Use the REST API endpoints:

```python
import requests

# Start a conversation session
response = requests.post("http://localhost:8000/api/sessions", 
                        json={"user_id": "test_user"})
session_id = response.json()["session_id"]

# Send a message
response = requests.post("http://localhost:8000/api/chat", 
                        json={
                            "user_input": "I need to schedule a 30-minute meeting for next Tuesday",
                            "session_id": session_id,
                            "user_id": "test_user"
                        })
print(response.json()["response"])
```

## 💬 Example Conversations

### Basic Scheduling
```
User: "I need to schedule a meeting"
Agent: "I'd be happy to help! How long should the meeting be?"
User: "30 minutes"
Agent: "Got it. When would you like to schedule this meeting?"
User: "Next Tuesday afternoon"
Agent: "Let me check your calendar... I found these options: 
        1) Tuesday 2:00 PM - 2:30 PM
        2) Tuesday 4:00 PM - 4:30 PM
        Which works better for you?"
User: "The first one"
Agent: "Perfect! I'll schedule a 30-minute meeting for Tuesday at 2:00 PM."
```

### Advanced Time Parsing
```
User: "Schedule a 1-hour meeting before my 5 PM call on Friday"
Agent: "I found your 5 PM call on Friday. How about 3:00 PM - 4:00 PM on Friday? 
        That gives you an hour break before your call."
User: "Perfect!"
Agent: "Great! Your meeting is scheduled for Friday 3:00 PM - 4:00 PM."
```

### Conflict Resolution
```
User: "Find me a slot Tuesday afternoon"
Agent: "I checked Tuesday afternoon, but you're fully booked. 
        However, I have these alternatives:
        - Wednesday 2:00 PM
        - Tuesday evening at 6:00 PM
        - Thursday morning at 10:00 AM
        Would any of these work?"
```

## 🛠️ Configuration

### Voice Settings

Customize voice processing in `config/environment.py`:

```python
# Audio quality
AUDIO_SAMPLE_RATE = 16000  # Higher for better quality
AUDIO_CHUNK_SIZE = 1024    # Smaller for lower latency

# Voice activity detection
VOICE_THRESHOLD = 0.01     # Sensitivity for speech detection
SILENCE_DURATION = 2.0     # Seconds of silence before stopping
```

### Speech-to-Text Options

The system now uses ElevenLabs Scribe v1 as the primary Speech-to-Text service, with Google Cloud Speech as a fallback:

- **ElevenLabs STT**: High accuracy transcription with support for 99 languages
- **Google Cloud Speech**: Used as fallback and for real-time streaming (until ElevenLabs supports streaming)

To test the Speech-to-Text functionality:

```bash
python test_stt_elevenlabs.py
```

### Time Parsing

The system can handle various time expressions:

- **Relative**: "next week", "tomorrow", "in 3 days"
- **Contextual**: "before my meeting", "after lunch"
- **Constraint-based**: "not too early", "afternoon only"
- **Complex**: "last weekday of the month", "2 hours before my flight"

## 🧪 Testing

### Unit Tests

```bash
pytest tests/
```

### Manual Testing Scenarios

1. **Basic Scheduling Flow**
   - Request a meeting → Specify duration → Choose time → Confirm

2. **Complex Time Parsing**
   - "Find me 45 minutes before my Project Alpha meeting"
   - "Schedule for the last Tuesday of this month"

3. **Conflict Resolution**
   - Request a fully booked time slot
   - Test alternative suggestions

4. **Context Switching**
   - Change meeting duration mid-conversation
   - Modify time preferences after seeing options

## 📊 Performance & Latency

### Optimizations Implemented

- **Streaming TTS**: ElevenLabs streaming for sub-2-second response times
- **Concurrent Processing**: Parallel STT and calendar API calls
- **Intelligent Caching**: Session state and calendar data caching
- **Voice Activity Detection**: Automatic conversation turn detection

### Expected Performance
- **Voice Response Latency**: < 2 seconds end-to-end
- **Calendar Query Time**: < 1 second for 7-day availability
- **Concurrent Sessions**: Supports 50+ simultaneous users

## 🔧 Troubleshooting

### Common Issues

1. **Audio Issues**
   ```bash
   # Check audio devices
   python -c "import pyaudio; pa = pyaudio.PyAudio(); [print(f'{i}: {pa.get_device_info_by_index(i)}') for i in range(pa.get_device_count())]"
   ```

2. **Google Calendar Authentication**
   - Ensure `credentials.json` is in the root directory
   - Check that Calendar API is enabled in Google Cloud Console
   - Verify OAuth consent screen is configured

3. **API Key Issues**
   - Verify all API keys are correctly set in `.env`
   - Check API key permissions and quotas

4. **Import Errors**
   - Ensure all dependencies are installed: `pip install -r requirements.txt`
   - Check Python path includes the project directory

### Debug Mode

Enable detailed logging:

```bash
DEBUG=True python src/api/main.py
```

## 🏆 Advanced Features

### Custom Voice Models
Integrate custom voice models by extending the `VoiceManager` class:

```python
class CustomVoiceManager(VoiceManager):
    async def synthesize_with_custom_model(self, text: str):
        # Your custom TTS implementation
        pass
```

### Multi-Language Support
Add support for additional languages:

```python
# In config/environment.py
SUPPORTED_LANGUAGES = ["en-US", "es-ES", "fr-FR"]
DEFAULT_VOICE_LANGUAGE = "en-US"
```

### Calendar Integration Extensions
Support for multiple calendar providers:

```python
class CalendarProvider:
    async def get_availability(self, start_time, end_time):
        # Implement for Outlook, Apple Calendar, etc.
        pass
```

## 📈 Scalability

### Deployment Options

1. **Single Server**: Run directly with uvicorn
2. **Containerized**: Docker deployment with proper resource limits
3. **Microservices**: Separate voice, calendar, and conversation services
4. **Cloud**: Deploy on AWS/GCP with auto-scaling

### Production Considerations

- **Rate Limiting**: Implement API rate limits
- **Monitoring**: Add health checks and metrics
- **Security**: JWT authentication, input validation
- **Backup**: Database backup strategies for session data

## 🤝 Contributing

### Development Setup

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Install dev dependencies: `pip install -r requirements-dev.txt`
4. Make your changes
5. Run tests: `pytest`
6. Submit a pull request

### Code Style

- Follow PEP 8 guidelines
- Use type hints throughout
- Write comprehensive docstrings
- Add unit tests for new features

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **OpenAI** for GPT-4 and function calling capabilities
- **ElevenLabs** for high-quality text-to-speech
- **Google Cloud** for Speech-to-Text and Calendar APIs
- **FastAPI** for the excellent web framework
- **dateparser** for robust natural language date parsing

## 📞 Support

For questions, issues, or contributions:

1. Check the [Issues](https://github.com/your-repo/issues) page
2. Review existing [Discussions](https://github.com/your-repo/discussions)
3. Create a new issue with detailed information

---

**Built for NextDimension - The future of AI-powered scheduling**