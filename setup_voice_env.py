#!/usr/bin/env python3
"""
Setup script for Smart Scheduler Voice Features
This script helps you configure the environment variables needed for voice functionality.
"""

import os
import sys

def create_env_file():
    """Create .env file with voice configuration"""
    
    env_content = """# Google AI Studio Configuration (Required)
GOOGLE_AI_API_KEY=AIzaSyCaBn9HWwGjgodnwiIWKwNQUNLHuSj4aiU
MODEL_NAME=gemini-2.0-flash
TEMPERATURE=0.7
MAX_TOKENS=1000

# ElevenLabs Configuration (Required for Voice)
ELEVENLABS_API_KEY=your_elevenlabs_api_key_here
ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM

# Google Cloud Configuration (Required for Voice)
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
"""
    
    # Check if .env already exists
    if os.path.exists('.env.example'):
        print("⚠️  .env.example file already exists!")
        response = input("Do you want to overwrite it? (y/N): ")
        if response.lower() != 'y':
            print("Skipping .env.example file creation.")
            return False
    
    # Write .env file
    with open('.env.example', 'w') as f:
        f.write(env_content)
    
    print("✅ .env.example file created successfully!")
    return True

def print_setup_instructions():
    """Print detailed setup instructions"""
    
    print("\n" + "="*60)
    print("🎤 SMART SCHEDULER VOICE SETUP INSTRUCTIONS")
    print("="*60)
    
    print("\n📋 STEP 1: Get ElevenLabs API Key")
    print("   1. Go to https://elevenlabs.io/")
    print("   2. Sign up for a free account")
    print("   3. Go to Profile → API Keys")
    print("   4. Copy your API key")
    print("   5. Replace 'your_elevenlabs_api_key_here' in .env file")
    
    print("\n📋 STEP 2: Set up Google Cloud Speech-to-Text")
    print("   1. Go to https://console.cloud.google.com/")
    print("   2. Create a new project or select existing")
    print("   3. Enable 'Cloud Speech-to-Text API'")
    print("   4. Go to IAM & Admin → Service Accounts")
    print("   5. Create service account with Speech API permissions")
    print("   6. Download JSON credentials file")
    print("   7. Update GOOGLE_APPLICATION_CREDENTIALS path in .env")
    print("   8. Update GOOGLE_CLOUD_PROJECT_ID in .env")
    
    print("\n📋 STEP 3: Install Voice Dependencies")
    print("   Run: pip install pyaudio speechrecognition pydub")
    print("   Note: PyAudio might need system dependencies:")
    print("   - Windows: Usually works with pip")
    print("   - Mac: brew install portaudio")
    print("   - Linux: sudo apt-get install portaudio19-dev")
    
    print("\n📋 STEP 4: Test Voice Setup")
    print("   Run: python test_voice_setup.py")
    
    print("\n📋 STEP 5: Start with Voice UI")
    print("   Run: python run_server.py")
    print("   Go to: http://localhost:8000")
    print("   Click the 🎤 Voice button to start talking!")
    
    print("\n" + "="*60)
    print("🎯 QUICK START (Minimal Setup)")
    print("="*60)
    print("If you just want to test voice features quickly:")
    print("1. Get ElevenLabs API key (free tier available)")
    print("2. Update ELEVENLABS_API_KEY in .env")
    print("3. Run: python run_server.py")
    print("4. Voice features will work with basic microphone input")
    print("   (Google Cloud STT will gracefully fallback)")

def main():
    print("🤖 Smart Scheduler Voice Setup")
    print("This script will help you set up voice features.\n")
    
    # Create .env file
    if create_env_file():
        print_setup_instructions()
    else:
        print("Setup cancelled.")
        return
    
    print("\n✨ Next steps:")
    print("1. Edit the .env file with your API keys")
    print("2. Follow the setup instructions above")
    print("3. Run: python test_voice_setup.py")

if __name__ == "__main__":
    main() 