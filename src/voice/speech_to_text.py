import asyncio
import io
import logging
import os
from typing import Optional, AsyncGenerator
import pyaudio
import wave
import httpx
from config.environment import config
import whisper

# Try to import ElevenLabs API
try:
    from elevenlabs.client import ElevenLabs
    ELEVENLABS_AVAILABLE = True
except ImportError:
    ELEVENLABS_AVAILABLE = False

# Try to import Google Cloud Speech - make it optional fallback
try:
    from google.cloud import speech
    from google.cloud.speech import RecognitionConfig, StreamingRecognitionConfig
    GOOGLE_SPEECH_AVAILABLE = True
except ImportError:
    GOOGLE_SPEECH_AVAILABLE = False
    speech = None
    RecognitionConfig = None
    StreamingRecognitionConfig = None

logger = logging.getLogger(__name__)

class ElevenLabsSpeechToTextService:
    """Speech-to-Text service using ElevenLabs Scribe v1 API"""
    
    def __init__(self):
        if not ELEVENLABS_AVAILABLE:
            logger.warning("ElevenLabs API not available - STT will be limited")
            self.client = None
            return
            
        try:
            self.client = ElevenLabs(api_key=config.ELEVENLABS_API_KEY)
            logger.info("ElevenLabs Speech-to-Text initialized successfully")
        except Exception as e:
            logger.warning(f"ElevenLabs initialization failed: {e}")
            self.client = None
    
    async def transcribe_audio_file(self, audio_file_path: str) -> Optional[str]:
        """Transcribe audio from a file using ElevenLabs Scribe v1"""
        if not self.client:
            logger.warning("ElevenLabs not available - cannot transcribe file")
            return None
            
        try:
            with open(audio_file_path, "rb") as audio_file:
                # Use ElevenLabs speech to text API
                response = self.client.speech_to_text.convert(
                    file=audio_file,
                    model_id="scribe_v1"
                )
                
                if response and hasattr(response, "text"):
                    return response.text
                return None
                
        except Exception as e:
            logger.error(f"Error transcribing audio file with ElevenLabs: {e}")
            return None
    
    async def transcribe_audio_stream(self, audio_generator: AsyncGenerator[bytes, None]) -> AsyncGenerator[str, None]:
        """Transcribe audio from a stream with real-time results (not yet supported by ElevenLabs)"""
        if not self.client:
            logger.warning("ElevenLabs not available - cannot transcribe stream")
            return
            
        try:
            # ElevenLabs doesn't support streaming transcription yet, so we need to collect all audio first
            audio_chunks = []
            async for chunk in audio_generator:
                audio_chunks.append(chunk)
            
            # Save the audio to a temporary file
            temp_file = "temp_audio_for_transcription.wav"
            with wave.open(temp_file, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)  # 16-bit
                wf.setframerate(config.AUDIO_SAMPLE_RATE)
                wf.writeframes(b''.join(audio_chunks))
            
            # Transcribe the temporary file
            with open(temp_file, "rb") as audio_file:
                response = self.client.speech_to_text.convert(
                    file=audio_file,
                    model_id="scribe_v1"
                )
                
                if response and hasattr(response, "text"):
                    yield response.text
            
            # Clean up
            if os.path.exists(temp_file):
                os.remove(temp_file)
                
        except Exception as e:
            logger.error(f"Error in streaming transcription with ElevenLabs: {e}")
    
    async def transcribe_microphone_input(self, duration_seconds: int = 5) -> Optional[str]:
        """Record from microphone and transcribe using ElevenLabs"""
        if not self.client:
            logger.warning("ElevenLabs not available - cannot transcribe microphone")
            return None
            
        try:
            # Initialize PyAudio
            audio = pyaudio.PyAudio()
            
            # Record audio
            stream = audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=config.AUDIO_SAMPLE_RATE,
                input=True,
                frames_per_buffer=config.AUDIO_CHUNK_SIZE
            )
            
            logger.info("Recording...")
            frames = []
            
            for _ in range(0, int(config.AUDIO_SAMPLE_RATE / config.AUDIO_CHUNK_SIZE * duration_seconds)):
                data = stream.read(config.AUDIO_CHUNK_SIZE)
                frames.append(data)
            
            logger.info("Recording finished")
            
            # Stop and close stream
            stream.stop_stream()
            stream.close()
            audio.terminate()
            
            # Save to temporary file
            temp_file = "temp_microphone_recording.wav"
            with wave.open(temp_file, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)  # 16-bit
                wf.setframerate(config.AUDIO_SAMPLE_RATE)
                wf.writeframes(b''.join(frames))
            
            # Transcribe the temporary file
            with open(temp_file, "rb") as audio_file:
                response = self.client.speech_to_text.convert(
                    file=audio_file,
                    model_id="scribe_v1"
                )
                
                transcript = None
                if response and hasattr(response, "text"):
                    transcript = response.text
                    logger.info(f"Transcribed: {transcript}")
            
            # Clean up
            if os.path.exists(temp_file):
                os.remove(temp_file)
                
            return transcript
            
        except Exception as e:
            logger.error(f"Error recording and transcribing with ElevenLabs: {e}")
            return None

class GoogleSpeechToTextService:
    """Speech-to-Text service using Google Cloud Speech API as fallback"""
    
    def __init__(self):
        if not GOOGLE_SPEECH_AVAILABLE:
            logger.warning("Google Cloud Speech not available - STT fallback will be limited")
            self.client = None
            self.config = None
            self.streaming_config = None
            return
            
        try:
            self.client = speech.SpeechClient()
            self.config = RecognitionConfig(
                encoding=RecognitionConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=config.AUDIO_SAMPLE_RATE,
                language_code=config.DEFAULT_VOICE_LANGUAGE,
                enable_automatic_punctuation=True,
                use_enhanced=True,
                model="phone_call",  # Optimized for phone calls/conversations
            )
            
            self.streaming_config = StreamingRecognitionConfig(
                config=self.config,
                interim_results=True,
            )
        except Exception as e:
            logger.warning(f"Google Cloud Speech initialization failed: {e}")
            self.client = None
            self.config = None
            self.streaming_config = None
    
    async def transcribe_audio_file(self, audio_file_path: str) -> Optional[str]:
        """Transcribe audio from a file"""
        if not self.client:
            logger.warning("Google Cloud Speech not available - cannot transcribe file")
            return None
            
        try:
            with io.open(audio_file_path, "rb") as audio_file:
                content = audio_file.read()
            
            audio = speech.RecognitionAudio(content=content)
            response = self.client.recognize(config=self.config, audio=audio)
            
            if response.results:
                return response.results[0].alternatives[0].transcript
            return None
            
        except Exception as e:
            logger.error(f"Error transcribing audio file with Google: {e}")
            return None
    
    async def transcribe_audio_stream(self, audio_generator: AsyncGenerator[bytes, None]) -> AsyncGenerator[str, None]:
        """Transcribe audio from a stream with real-time results"""
        if not self.client:
            logger.warning("Google Cloud Speech not available - cannot transcribe stream")
            return
            
        try:
            def request_generator():
                # First, send the configuration
                yield speech.StreamingRecognizeRequest(
                    streaming_config=self.streaming_config
                )
                
                # Then, send audio data
                async def audio_loop():
                    async for chunk in audio_generator:
                        yield speech.StreamingRecognizeRequest(audio_content=chunk)
                
                # Convert async generator to sync for gRPC
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                audio_gen = audio_loop()
                try:
                    while True:
                        chunk = loop.run_until_complete(audio_gen.__anext__())
                        yield chunk
                except StopAsyncIteration:
                    pass
                finally:
                    loop.close()
            
            responses = self.client.streaming_recognize(
                config=self.streaming_config,
                requests=request_generator()
            )
            
            for response in responses:
                if response.results:
                    result = response.results[0]
                    if result.is_final:
                        yield result.alternatives[0].transcript
                        
        except Exception as e:
            logger.error(f"Error in streaming transcription with Google: {e}")
    
    async def transcribe_microphone_input(self, duration_seconds: int = 5) -> Optional[str]:
        """Record from microphone and transcribe"""
        if not self.client:
            logger.warning("Google Cloud Speech not available - cannot transcribe microphone")
            return None
            
        try:
            # Initialize PyAudio
            audio = pyaudio.PyAudio()
            
            # Record audio
            stream = audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=config.AUDIO_SAMPLE_RATE,
                input=True,
                frames_per_buffer=config.AUDIO_CHUNK_SIZE
            )
            
            logger.info("Recording...")
            frames = []
            
            for _ in range(0, int(config.AUDIO_SAMPLE_RATE / config.AUDIO_CHUNK_SIZE * duration_seconds)):
                data = stream.read(config.AUDIO_CHUNK_SIZE)
                frames.append(data)
            
            logger.info("Recording finished")
            
            # Stop and close stream
            stream.stop_stream()
            stream.close()
            audio.terminate()
            
            # Convert to bytes
            audio_data = b''.join(frames)
            
            # Create audio object for Google Speech API
            audio_input = speech.RecognitionAudio(content=audio_data)
            
            # Transcribe
            response = self.client.recognize(config=self.config, audio=audio_input)
            
            if response.results:
                transcript = response.results[0].alternatives[0].transcript
                logger.info(f"Transcribed: {transcript}")
                return transcript
            
            return None
            
        except Exception as e:
            logger.error(f"Error recording and transcribing with Google: {e}")
            return None

class WhisperSpeechToTextService:
    def __init__(self, model_name="tiny"):
        self.model = whisper.load_model(model_name)

    async def transcribe_audio_file(self, audio_file_path: str) -> Optional[str]:
        try:
            result = self.model.transcribe(audio_file_path)
            return result.get("text", "").strip()
        except Exception as e:
            logger.error(f"Whisper transcription failed: {e}")
            return None

class SpeechToTextService:
    """Main Speech-to-Text service that uses ElevenLabs as primary and Google as fallback"""
    
    def __init__(self):
        self.elevenlabs_service = ElevenLabsSpeechToTextService()
        self.google_service = GoogleSpeechToTextService()
        self.whisper_service = WhisperSpeechToTextService()
        
    def is_available(self) -> bool:
        """Check if any STT service is available"""
        return (self.elevenlabs_service and self.elevenlabs_service.client is not None) or \
               (self.google_service and self.google_service.client is not None) or \
               (self.whisper_service)

    async def transcribe_audio_file(self, audio_file_path: str) -> Optional[str]:
        """Transcribe audio from a file, using Whisper first, then ElevenLabs, then Google as fallback"""
        # Try Whisper first
        transcript = await self.whisper_service.transcribe_audio_file(audio_file_path)
        if transcript:
            return transcript
            
        # Try ElevenLabs next
        if self.elevenlabs_service.client:
            logger.info("Falling back to ElevenLabs Speech-to-Text")
            transcript = await self.elevenlabs_service.transcribe_audio_file(audio_file_path)
            if transcript:
                return transcript
            
        # Fallback to Google
        logger.info("Falling back to Google Speech-to-Text")
        return await self.google_service.transcribe_audio_file(audio_file_path)
    
    async def transcribe_audio_stream(self, audio_generator: AsyncGenerator[bytes, None]) -> AsyncGenerator[str, None]:
        """Transcribe audio from a stream with real-time results"""
        # Since ElevenLabs doesn't support real-time streaming yet, use Google for streaming
        async for transcript in self.google_service.transcribe_audio_stream(audio_generator):
            yield transcript
    
    async def transcribe_microphone_input(self, duration_seconds: int = 5) -> Optional[str]:
        """Record from microphone and transcribe"""
        # Try Whisper first
        transcript = await self.whisper_service.transcribe_audio_file(audio_file_path)
        if transcript:
            return transcript
            
        # Try ElevenLabs next
        if self.elevenlabs_service.client:
            logger.info("Falling back to ElevenLabs Speech-to-Text for microphone input")
            transcript = await self.elevenlabs_service.transcribe_microphone_input(duration_seconds)
            if transcript:
                return transcript
            
        # Fallback to Google
        logger.info("Falling back to Google Speech-to-Text for microphone input")
        return await self.google_service.transcribe_microphone_input(duration_seconds)

class AudioRecorder:
    """Helper class for recording audio from microphone"""
    
    def __init__(self):
        self.audio = pyaudio.PyAudio()
        self.stream = None
        self.recording = False
    
    async def start_recording(self) -> AsyncGenerator[bytes, None]:
        """Start recording and yield audio chunks"""
        try:
            self.stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=config.AUDIO_SAMPLE_RATE,
                input=True,
                frames_per_buffer=config.AUDIO_CHUNK_SIZE,
                stream_callback=None
            )
            
            self.recording = True
            
            while self.recording:
                data = self.stream.read(config.AUDIO_CHUNK_SIZE, exception_on_overflow=False)
                yield data
                await asyncio.sleep(0.01)  # Small delay to prevent overwhelming
                
        except Exception as e:
            logger.error(f"Error in audio recording: {e}")
            self.recording = False
    
    def stop_recording(self):
        """Stop recording"""
        self.recording = False
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None
        
        self.audio.terminate()

class VoiceActivityDetector:
    """Detects voice activity in audio chunks to determine when to stop recording"""
    
    def __init__(self, threshold: float = 0.01, silence_duration: float = 2.0):
        self.threshold = threshold
        self.silence_duration = silence_duration
        self.silence_start = None
    
    def is_speech(self, audio_chunk: bytes) -> bool:
        """Determine if an audio chunk contains speech based on amplitude"""
        import numpy as np
        
        # Convert bytes to numpy array
        audio_data = np.frombuffer(audio_chunk, dtype=np.int16)
        
        # Calculate RMS amplitude
        rms = np.sqrt(np.mean(np.square(audio_data.astype(np.float32))))
        
        # Normalize and check if above threshold
        return (rms / 32768.0) > self.threshold
    
    def should_stop_recording(self, audio_chunk: bytes) -> bool:
        """Determine if recording should stop based on silence duration"""
        import time
        
        if self.is_speech(audio_chunk):
            # Reset silence timer if speech detected
            self.silence_start = None
            return False
        else:
            # Start or continue tracking silence
            current_time = time.time()
            if self.silence_start is None:
                self.silence_start = current_time
            elif (current_time - self.silence_start) >= self.silence_duration:
                return True
            
        return False