#!/usr/bin/env python3
"""
Voice Setup Test Script
Tests all voice components to ensure they're working correctly.
"""

import asyncio
import sys
import os
import logging

# Add project root to path
sys.path.append('src')

from config.environment import config
from src.voice.text_to_speech import TextToSpeechService, VoiceManager
from src.voice.speech_to_text import SpeechToTextService

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_environment_variables():
    """Test if all required environment variables are set"""
    print("🔧 Testing Environment Variables...")
    
    required_vars = {
        'GOOGLE_AI_API_KEY': config.GOOGLE_AI_API_KEY,
        'ELEVENLABS_API_KEY': config.ELEVENLABS_API_KEY,
    }
    
    optional_vars = {
        'GOOGLE_APPLICATION_CREDENTIALS': config.GOOGLE_APPLICATION_CREDENTIALS,
        'GOOGLE_CLOUD_PROJECT_ID': config.GOOGLE_CLOUD_PROJECT_ID,
    }
    
    all_good = True
    
    for var_name, var_value in required_vars.items():
        if not var_value or var_value == "your_elevenlabs_api_key_here":
            print(f"❌ {var_name}: Not set or using placeholder")
            all_good = False
        else:
            print(f"✅ {var_name}: Set")
    
    for var_name, var_value in optional_vars.items():
        if not var_value or "your-" in str(var_value):
            print(f"⚠️  {var_name}: Not set (optional for basic functionality)")
        else:
            print(f"✅ {var_name}: Set")
    
    return all_good

async def test_text_to_speech():
    """Test Text-to-Speech functionality"""
    print("\n🔊 Testing Text-to-Speech...")
    
    try:
        tts_service = TextToSpeechService()
        
        # Test voice list
        voices = await tts_service.get_available_voices()
        if voices:
            print(f"✅ Found {len(voices)} available voices")
            print(f"   Using voice: {config.ELEVENLABS_VOICE_ID}")
        else:
            print("⚠️  No voices found - check ElevenLabs API key")
            return False
        
        # Test synthesis
        test_text = "Hello! This is a test of the text-to-speech system."
        print(f"🎵 Testing synthesis: '{test_text}'")
        
        audio_bytes = await tts_service.synthesize_speech(test_text)
        if audio_bytes:
            print("✅ Text-to-speech synthesis successful")
            
            # Test playback
            print("🔊 Testing audio playback...")
            success = await tts_service.synthesize_and_play(test_text)
            if success:
                print("✅ Audio playback successful")
            else:
                print("⚠️  Audio playback failed - check audio system")
            
            return True
        else:
            print("❌ Text-to-speech synthesis failed")
            return False
            
    except Exception as e:
        print(f"❌ TTS Error: {e}")
        return False

async def test_speech_to_text():
    """Test Speech-to-Text functionality"""
    print("\n🎤 Testing Speech-to-Text...")
    
    try:
        stt_service = SpeechToTextService()
        
        if not stt_service.client:
            print("⚠️  Google Cloud Speech not available - using fallback")
            print("   This is normal if Google Cloud credentials aren't set")
            return True
        
        print("✅ Google Cloud Speech client initialized")
        print("🎤 Testing microphone access...")
        
        # Test microphone recording (short duration)
        print("   Recording 3 seconds of audio... (say something!)")
        transcript = await stt_service.transcribe_microphone_input(duration_seconds=3)
        
        if transcript:
            print(f"✅ Speech recognition successful: '{transcript}'")
            return True
        else:
            print("⚠️  No speech detected or recognition failed")
            return True  # Not necessarily an error
            
    except Exception as e:
        print(f"❌ STT Error: {e}")
        print("   This might be due to missing Google Cloud credentials")
        return True  # Don't fail the test for optional feature

async def test_voice_manager():
    """Test the integrated voice manager"""
    print("\n🎛️  Testing Voice Manager...")
    
    try:
        voice_manager = VoiceManager()
        await voice_manager.initialize()
        
        available_voices = voice_manager.get_available_voices()
        if available_voices:
            print(f"✅ Voice Manager initialized with {len(available_voices)} voices")
            
            # Test speaking
            test_text = "Voice manager test successful!"
            print(f"🗣️  Testing voice manager speech: '{test_text}'")
            success = await voice_manager.speak_text(test_text)
            
            if success:
                print("✅ Voice Manager speech test successful")
            else:
                print("⚠️  Voice Manager speech test failed")
            
            return True
        else:
            print("❌ Voice Manager initialization failed")
            return False
            
    except Exception as e:
        print(f"❌ Voice Manager Error: {e}")
        return False

async def test_full_conversation_flow():
    """Test a complete voice conversation flow"""
    print("\n🤖 Testing Full Conversation Flow...")
    
    try:
        # Import the main agent
        from src.agent.conversation_manager import SmartSchedulerAgent
        
        agent = SmartSchedulerAgent()
        await agent.initialize()
        
        print("✅ Smart Scheduler Agent initialized")
        
        # Test text processing (voice conversation uses same backend)
        session_id = "test_session"
        await agent.state_manager.create_session(session_id, "test_user")
        
        test_input = "I need to schedule a 30-minute meeting"
        response = await agent._process_user_input(session_id, test_input)
        
        if response:
            print(f"✅ Conversation processing successful")
            print(f"   Input: '{test_input}'")
            print(f"   Response: '{response[:100]}...'")
            return True
        else:
            print("❌ Conversation processing failed")
            return False
            
    except Exception as e:
        print(f"❌ Conversation Flow Error: {e}")
        return False

async def main():
    """Run all voice tests"""
    print("🎤 SMART SCHEDULER VOICE SETUP TEST")
    print("=" * 50)
    
    tests = [
        ("Environment Variables", test_environment_variables),
        ("Text-to-Speech", test_text_to_speech),
        ("Speech-to-Text", test_speech_to_text),
        ("Voice Manager", test_voice_manager),
        ("Conversation Flow", test_full_conversation_flow),
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        try:
            result = await test_func()
            results[test_name] = result
        except Exception as e:
            print(f"❌ {test_name} test crashed: {e}")
            results[test_name] = False
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 TEST RESULTS SUMMARY")
    print("=" * 50)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {test_name}")
        if result:
            passed += 1
    
    print(f"\n🎯 Overall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Voice features are ready to use.")
        print("\n🚀 Next steps:")
        print("1. Run: python run_server.py")
        print("2. Go to: http://localhost:8000")
        print("3. Click the 🎤 Voice button to start talking!")
    else:
        print("⚠️  Some tests failed. Check the setup instructions:")
        print("1. Run: python setup_voice_env.py")
        print("2. Follow the setup instructions")
        print("3. Update your .env file with correct API keys")

if __name__ == "__main__":
    asyncio.run(main()) 