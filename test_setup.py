#!/usr/bin/env python3
"""
Test script to verify Smart Scheduler AI Agent setup and basic functionality.
Run this script after setting up your environment to ensure everything works.
"""

import asyncio
import os
import sys
import logging
from datetime import datetime, timedelta
import traceback

# Add project root to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Configure logging for tests
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_imports():
    """Test if all required modules can be imported"""
    print("🔍 Testing imports...")
    
    try:
        # Core dependencies
        import fastapi
        import uvicorn
        import google.generativeai
        import pyaudio
        import dateparser
        import pytz
        import sqlalchemy
        print("✅ Core dependencies imported successfully")
        
        # Voice processing
        try:
            from elevenlabs import generate
            print("✅ ElevenLabs imported successfully")
        except ImportError:
            print("⚠️  ElevenLabs not available - TTS will be limited")
        
        try:
            from google.cloud import speech, texttospeech
            print("✅ Google Cloud Speech APIs imported successfully")
        except ImportError:
            print("⚠️  Google Cloud Speech APIs not available")
        
        # Google Calendar
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            print("✅ Google Calendar API imported successfully")
        except ImportError:
            print("⚠️  Google Calendar API not available")
        
        # Local imports
        from config.environment import config
        print("✅ Configuration loaded successfully")
        
        return True
        
    except Exception as e:
        print(f"❌ Import error: {e}")
        traceback.print_exc()
        return False

def test_environment_variables():
    """Test if required environment variables are set"""
    print("\n🔧 Testing environment variables...")
    
    required_vars = [
        "GOOGLE_AI_API_KEY",
        "ELEVENLABS_API_KEY",
    ]
    
    missing_vars = []
    for var in required_vars:
        value = os.getenv(var)
        if not value or value == "your_api_key_here":
            missing_vars.append(var)
        else:
            print(f"✅ {var} is set")
    
    if missing_vars:
        print(f"❌ Missing required environment variables: {', '.join(missing_vars)}")
        print("Please set these in your .env file or environment")
        return False
    
    print("✅ All required environment variables are set")
    return True

async def test_basic_functionality():
    """Test basic functionality without external services"""
    print("\n🧪 Testing basic functionality...")
    
    try:
        # Test state manager
        from src.agent.state_manager import StateManager, ConversationState
        state_manager = StateManager("test_scheduler.db")
        
        # Create a test session
        session = await state_manager.create_session("test_session", "test_user")
        print("✅ Session creation successful")
        
        # Test state transitions
        await state_manager.set_state("test_session", ConversationState.WAITING_FOR_DURATION)
        updated_session = await state_manager.get_session("test_session")
        assert updated_session.state == ConversationState.WAITING_FOR_DURATION
        print("✅ State management working")
        
        # Test conversation turns
        await state_manager.add_conversation_turn("test_session", "Hello", "Hi there!")
        context = await state_manager.get_conversation_context("test_session")
        assert len(context) == 1
        print("✅ Conversation history working")
        
        # Clean up
        await state_manager.clear_session("test_session")
        if os.path.exists("test_scheduler.db"):
            os.remove("test_scheduler.db")
        
        print("✅ Basic functionality tests passed")
        return True
        
    except Exception as e:
        print(f"❌ Basic functionality test failed: {e}")
        traceback.print_exc()
        return False

async def test_time_parsing():
    """Test time parsing functionality"""
    print("\n⏰ Testing time parsing...")
    
    try:
        from src.agent.time_parser import AdvancedTimeParser
        from src.agent.calendar_integration import CalendarManager
        
        # Create a mock calendar manager for testing
        calendar_manager = CalendarManager()
        time_parser = AdvancedTimeParser(calendar_manager)
        
        # Test duration parsing
        test_durations = [
            ("30 minutes", 30),
            ("1 hour", 60),
            ("45 mins", 45),
            ("2 hours", 120)
        ]
        
        for text, expected in test_durations:
            result = await time_parser.parse_duration(text)
            if result == expected:
                print(f"✅ Duration parsing: '{text}' → {result} minutes")
            else:
                print(f"❌ Duration parsing failed: '{text}' → {result} (expected {expected})")
                return False
        
        # Test time expression parsing
        test_expressions = [
            "next Tuesday",
            "tomorrow afternoon",
            "in 2 days"
        ]
        
        for expr in test_expressions:
            result = await time_parser.parse_time_expression(expr)
            if result.confidence > 0:
                print(f"✅ Time expression parsing: '{expr}' → confidence {result.confidence:.2f}")
            else:
                print(f"⚠️  Time expression parsing: '{expr}' → low confidence")
        
        print("✅ Time parsing tests completed")
        return True
        
    except Exception as e:
        print(f"❌ Time parsing test failed: {e}")
        traceback.print_exc()
        return False

async def test_gemini_connection():
    """Test Google AI Studio (Gemini) API connection"""
    print("\n🤖 Testing Google AI Studio (Gemini) connection...")
    
    try:
        import google.generativeai as genai
        from config.environment import config
        
        genai.configure(api_key=config.GOOGLE_AI_API_KEY)
        model = genai.GenerativeModel(config.MODEL_NAME)
        
        # Simple test request
        response = model.generate_content("Say 'Hello from Smart Scheduler test!'")
        
        if response.text:
            print(f"✅ Google AI Studio connection successful")
            print(f"   Response: {response.text.strip()}")
            return True
        else:
            print("❌ Google AI Studio connection failed - no response content")
            return False
            
    except Exception as e:
        print(f"❌ Google AI Studio connection test failed: {e}")
        return False

def test_audio_devices():
    """Test audio device availability"""
    print("\n🔊 Testing audio devices...")
    
    try:
        import pyaudio
        
        pa = pyaudio.PyAudio()
        device_count = pa.get_device_count()
        
        print(f"✅ Found {device_count} audio devices")
        
        # Find input and output devices
        input_devices = []
        output_devices = []
        
        for i in range(device_count):
            device_info = pa.get_device_info_by_index(i)
            if device_info['maxInputChannels'] > 0:
                input_devices.append(device_info['name'])
            if device_info['maxOutputChannels'] > 0:
                output_devices.append(device_info['name'])
        
        if input_devices:
            print(f"✅ Input devices available: {len(input_devices)}")
        else:
            print("⚠️  No input devices found - voice input may not work")
        
        if output_devices:
            print(f"✅ Output devices available: {len(output_devices)}")
        else:
            print("⚠️  No output devices found - voice output may not work")
        
        pa.terminate()
        return len(input_devices) > 0 and len(output_devices) > 0
        
    except Exception as e:
        print(f"❌ Audio device test failed: {e}")
        return False

async def test_web_server():
    """Test if the web server can start"""
    print("\n🌐 Testing web server startup...")
    
    try:
        from src.api.main import app
        from fastapi.testclient import TestClient
        
        # Create test client
        client = TestClient(app)
        
        # Test health endpoint
        response = client.get("/health")
        if response.status_code == 200:
            print("✅ Health endpoint accessible")
        else:
            print(f"❌ Health endpoint failed: {response.status_code}")
            return False
        
        # Test status endpoint
        response = client.get("/api/status")
        if response.status_code == 200:
            print("✅ Status endpoint accessible")
        else:
            print(f"❌ Status endpoint failed: {response.status_code}")
            return False
        
        print("✅ Web server tests passed")
        return True
        
    except Exception as e:
        print(f"❌ Web server test failed: {e}")
        traceback.print_exc()
        return False

async def run_all_tests():
    """Run all tests and provide summary"""
    print("🚀 Starting Smart Scheduler AI Agent Setup Tests\n")
    
    tests = [
        ("Import Tests", test_imports),
        ("Environment Variables", test_environment_variables),
        ("Audio Devices", test_audio_devices),
        ("Basic Functionality", test_basic_functionality),
        ("Time Parsing", test_time_parsing),
        ("Google AI Studio Connection", test_gemini_connection),
        ("Web Server", test_web_server),
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        try:
            if asyncio.iscoroutinefunction(test_func):
                result = await test_func()
            else:
                result = test_func()
            results[test_name] = result
        except Exception as e:
            print(f"❌ {test_name} crashed: {e}")
            results[test_name] = False
    
    # Summary
    print("\n" + "="*50)
    print("📊 TEST SUMMARY")
    print("="*50)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {test_name}")
        if result:
            passed += 1
    
    print(f"\nResults: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! Your Smart Scheduler is ready to go!")
        print("\nNext steps:")
        print("1. Run: python src/api/main.py")
        print("2. Open: http://localhost:8000")
        print("3. Start scheduling meetings!")
    else:
        print(f"\n⚠️  {total - passed} tests failed. Please check the issues above.")
        print("\nCommon solutions:")
        if not results.get("Environment Variables", True):
            print("- Set up your .env file with API keys")
        if not results.get("Google AI Studio Connection", True):
            print("- Verify your Google AI Studio API key and internet connection")
        if not results.get("Audio Devices", True):
            print("- Check microphone and speaker connections")
    
    return passed == total

if __name__ == "__main__":
    # Ensure we can import from the src directory
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    
    try:
        success = asyncio.run(run_all_tests())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⏹️  Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n💥 Test runner crashed: {e}")
        traceback.print_exc()
        sys.exit(1) 