# 🎤 Smart Scheduler Voice Features Setup Guide

## Overview

The Smart Scheduler AI Agent includes full voice capabilities with Speech-to-Text (STT) and Text-to-Speech (TTS) integration. This guide will help you enable and configure these features.

## 🚀 Quick Start (Minimal Setup)

### Step 1: Run Setup Script
```bash
python setup_voice_env.py
```

### Step 2: Get ElevenLabs API Key (Free Tier Available)
1. Go to [ElevenLabs](https://elevenlabs.io/)
2. Sign up for a free account
3. Go to Profile → API Keys
4. Copy your API key
5. Edit `.env` file and replace `your_elevenlabs_api_key_here` with your key

### Step 3: Test and Run
```bash
# Test voice setup
python test_voice_setup.py

# Start the server
python run_server.py
```

### Step 4: Use Voice Features
1. Go to `http://localhost:8000`
2. Click the 🎤 microphone button
3. Start talking!

---

## 🔧 Complete Setup (Full Features)

### Environment Variables Required

Create a `.env` file in your project root with these variables:

```bash
# Google AI Studio Configuration (Required)
GOOGLE_AI_API_KEY=your_google_ai_api_key
MODEL_NAME=gemini-2.0-flash
TEMPERATURE=0.7
MAX_TOKENS=1000

# ElevenLabs Configuration (Required for Voice)
ELEVENLABS_API_KEY=your_elevenlabs_api_key_here
ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM

# Google Cloud Configuration (Optional - for better STT)
GOOGLE_APPLICATION_CREDENTIALS=path/to/your/google-cloud-credentials.json
GOOGLE_CLOUD_PROJECT_ID=your-google-cloud-project-id

# Google Calendar API Configuration (Optional)
GOOGLE_CALENDAR_CREDENTIALS=credentials.json
GOOGLE_CALENDAR_TOKEN=token.json

# Application Settings
APP_HOST=localhost
APP_PORT=8000
DEBUG=True

# Voice Configuration
DEFAULT_VOICE_LANGUAGE=en-US
AUDIO_SAMPLE_RATE=16000
AUDIO_CHUNK_SIZE=1024

# Database
DATABASE_URL=sqlite:///./smart_scheduler.db
```

---

## 📋 Detailed Setup Instructions

### 1. ElevenLabs Text-to-Speech Setup

**Why ElevenLabs?**
- High-quality AI voices
- Natural-sounding speech
- Free tier available (10,000 characters/month)
- Low latency

**Setup Steps:**
1. Visit [ElevenLabs](https://elevenlabs.io/)
2. Create account (free tier available)
3. Go to Profile → API Keys
4. Generate and copy API key
5. Update `ELEVENLABS_API_KEY` in `.env`

**Voice Selection:**
- Default voice ID: `21m00Tcm4TlvDq8ikWAM` (Rachel)
- To use different voice:
  1. Go to ElevenLabs Voice Library
  2. Copy voice ID from URL
  3. Update `ELEVENLABS_VOICE_ID` in `.env`

### 2. Google Cloud Speech-to-Text Setup (Optional)

**Why Google Cloud STT?**
- High accuracy speech recognition
- Optimized for conversations
- Real-time streaming support
- Multiple language support

**Setup Steps:**
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create new project or select existing
3. Enable "Cloud Speech-to-Text API"
4. Go to IAM & Admin → Service Accounts
5. Create service account with Speech API permissions
6. Download JSON credentials file
7. Update paths in `.env`:
   ```bash
   GOOGLE_APPLICATION_CREDENTIALS=/path/to/credentials.json
   GOOGLE_CLOUD_PROJECT_ID=your-project-id
   ```

**Note:** Without Google Cloud STT, the system will gracefully fallback to browser-based speech recognition.

### 3. Install Voice Dependencies

```bash
# Core voice processing libraries
pip install pyaudio speechrecognition pydub

# Platform-specific audio dependencies
# Windows: Usually works with pip
# Mac: brew install portaudio
# Linux: sudo apt-get install portaudio19-dev
```

---

## 🎯 Voice Features Overview

### 1. Web Interface Voice Controls

**New UI Elements:**
- 🎤 **Voice Button**: Click to start/stop recording
- **Voice Status Indicator**: Shows online/offline status
- **Recording Animation**: Pulsing red button when recording
- **Status Messages**: Real-time feedback on voice processing

**How to Use:**
1. Click microphone button to start recording
2. Speak your request (e.g., "Schedule a meeting for tomorrow")
3. Click again to stop recording
4. System processes speech and responds

### 2. Voice Processing Flow

```
User Speech → Browser Recording → Backend STT → LLM Processing → TTS Response
```

**Technical Details:**
- **Audio Format**: WebM with Opus codec
- **Sample Rate**: 16kHz (optimized for speech)
- **Processing**: Real-time with low latency
- **Fallback**: Graceful degradation if services unavailable

### 3. Voice API Endpoints

**Process Voice Input:**
```
POST /api/voice/process
Content-Type: multipart/form-data
Body: audio file

Response:
{
  "success": true,
  "transcript": "I need to schedule a meeting",
  "message": "Voice processed successfully"
}
```

**Synthesize Speech:**
```
POST /api/voice/synthesize
Body: { "text": "Hello, how can I help you?" }

Response: Audio file (MP3)
```

---

## 🧪 Testing Voice Features

### Run Voice Tests
```bash
python test_voice_setup.py
```

**Test Coverage:**
- ✅ Environment variables validation
- ✅ Text-to-Speech functionality
- ✅ Speech-to-Text functionality  
- ✅ Voice Manager integration
- ✅ Full conversation flow

### Manual Testing

1. **Test TTS (Text-to-Speech):**
   - Start server: `python run_server.py`
   - Type message and send
   - Should hear spoken response

2. **Test STT (Speech-to-Text):**
   - Click microphone button
   - Speak clearly: "I need to schedule a meeting"
   - Should see transcribed text

3. **Test Full Voice Conversation:**
   - Click microphone
   - Say: "Schedule a 30-minute meeting for tomorrow afternoon"
   - Should get spoken response with available times

---

## 🔧 Troubleshooting

### Common Issues

**"Voice not supported in this browser"**
- Use Chrome, Firefox, or Edge
- Ensure HTTPS (required for microphone access)
- Check browser permissions

**"Microphone access denied"**
- Allow microphone permissions in browser
- Check system microphone settings
- Try refreshing the page

**"ElevenLabs API error"**
- Verify API key is correct
- Check account quota (free tier: 10k chars/month)
- Ensure internet connection

**"Google Cloud Speech not available"**
- This is normal without Google Cloud setup
- System will use browser STT as fallback
- For better accuracy, set up Google Cloud credentials

**"PyAudio installation failed"**
```bash
# Windows
pip install pipwin
pipwin install pyaudio

# Mac
brew install portaudio
pip install pyaudio

# Linux
sudo apt-get install portaudio19-dev
pip install pyaudio
```

### Debug Mode

Enable detailed logging:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

---

## 🎮 Usage Examples

### Voice Commands That Work

**Scheduling Requests:**
- "I need to schedule a meeting"
- "Find me a 30-minute slot tomorrow afternoon"
- "Schedule a call before my 5 PM meeting on Friday"
- "What's available next Tuesday morning?"

**Follow-up Responses:**
- "Tomorrow afternoon" (when asked for time)
- "One hour" (when asked for duration)
- "The first one" (when selecting from options)

### Conversation Flow Example

```
🎤 User: "I need to schedule a meeting"
🤖 Agent: "How long should the meeting be?"
🎤 User: "One hour"
🤖 Agent: "What day and time would you prefer?"
🎤 User: "Tomorrow afternoon"
🤖 Agent: "Great! I found these available times:
          1. Tomorrow at 2:00 PM - 3:00 PM
          2. Tomorrow at 3:30 PM - 4:30 PM
          Which one works for you?"
🎤 User: "The first one"
🤖 Agent: "Perfect! I've scheduled your meeting for tomorrow at 2:00 PM."
```

---

## 🚀 Advanced Configuration

### Custom Voice Settings

**Change Voice Language:**
```bash
DEFAULT_VOICE_LANGUAGE=es-ES  # Spanish
DEFAULT_VOICE_LANGUAGE=fr-FR  # French
DEFAULT_VOICE_LANGUAGE=de-DE  # German
```

**Audio Quality Settings:**
```bash
AUDIO_SAMPLE_RATE=22050      # Higher quality (more bandwidth)
AUDIO_CHUNK_SIZE=2048        # Larger chunks (less frequent processing)
```

### Multiple Voice Providers

The system supports multiple TTS providers:
1. **ElevenLabs** (Primary) - Best quality
2. **Google Cloud TTS** (Backup) - Good quality
3. **Browser TTS** (Fallback) - Basic quality

### Production Deployment

**Security Considerations:**
- Use HTTPS for microphone access
- Secure API keys with environment variables
- Implement rate limiting for voice endpoints

**Performance Optimization:**
- Use CDN for static assets
- Enable audio compression
- Implement audio caching

---

## 📊 System Requirements

### Minimum Requirements
- **Browser**: Chrome 60+, Firefox 55+, Safari 11+
- **Internet**: Stable connection for API calls
- **Microphone**: Any system microphone
- **RAM**: 512MB available
- **Storage**: 100MB for dependencies

### Recommended Requirements
- **Browser**: Latest Chrome/Firefox
- **Internet**: Broadband connection
- **Microphone**: Noise-canceling headset
- **RAM**: 2GB available
- **Storage**: 1GB for full setup

---

## 🎯 Next Steps

After setting up voice features:

1. **Integrate with Calendar**: Follow Google Calendar setup guide
2. **Customize Voices**: Explore ElevenLabs voice library
3. **Add Languages**: Configure multi-language support
4. **Deploy Production**: Set up HTTPS and domain
5. **Monitor Usage**: Track API usage and costs

---

## 📞 Support

If you encounter issues:

1. Run diagnostic: `python test_voice_setup.py`
2. Check logs for error messages
3. Verify all environment variables are set
4. Test with minimal configuration first
5. Check API quotas and limits

**Common Solutions:**
- Restart browser after permission changes
- Clear browser cache and cookies
- Update to latest browser version
- Check firewall/antivirus settings

---

## 🎉 Success!

Once everything is working, you'll have:

✅ **Voice-enabled web interface** with microphone button  
✅ **Real-time speech recognition** with Google Cloud STT  
✅ **Natural voice responses** with ElevenLabs TTS  
✅ **Seamless conversation flow** with context awareness  
✅ **Graceful fallbacks** when services are unavailable  
✅ **Production-ready architecture** with proper error handling  

Your Smart Scheduler is now a fully voice-enabled AI assistant! 🚀 