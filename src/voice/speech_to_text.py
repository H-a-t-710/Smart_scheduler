import asyncio
import io
import logging
from typing import Optional, AsyncGenerator
import pyaudio
import wave
from config.environment import config

# Try to import Google Cloud Speech - make it optional
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

class SpeechToTextService:
    """Speech-to-Text service using Google Cloud Speech API"""
    
    def __init__(self):
        if not GOOGLE_SPEECH_AVAILABLE:
            logger.warning("Google Cloud Speech not available - STT will be limited")
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
            logger.error(f"Error transcribing audio file: {e}")
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
            logger.error(f"Error in streaming transcription: {e}")
    
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
            logger.error(f"Error recording and transcribing: {e}")
            return None

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
        finally:
            self.stop_recording()
    
    def stop_recording(self):
        """Stop recording"""
        self.recording = False
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        self.audio.terminate()

# Voice Activity Detection (simple implementation)
class VoiceActivityDetector:
    """Simple voice activity detection based on audio amplitude"""
    
    def __init__(self, threshold: float = 0.01, silence_duration: float = 2.0):
        self.threshold = threshold
        self.silence_duration = silence_duration
        self.last_speech_time = 0
    
    def is_speech(self, audio_chunk: bytes) -> bool:
        """Detect if audio chunk contains speech"""
        import numpy as np
        
        # Convert bytes to numpy array
        audio_data = np.frombuffer(audio_chunk, dtype=np.int16)
        
        # Calculate RMS (Root Mean Square) amplitude
        rms = np.sqrt(np.mean(audio_data.astype(np.float64) ** 2))
        
        # Normalize to 0-1 range
        normalized_rms = rms / 32768.0
        
        return normalized_rms > self.threshold
    
    def should_stop_recording(self, audio_chunk: bytes) -> bool:
        """Determine if recording should stop based on silence"""
        import time
        
        if self.is_speech(audio_chunk):
            self.last_speech_time = time.time()
            return False
        
        # If no speech for silence_duration seconds, stop recording
        return time.time() - self.last_speech_time > self.silence_duration