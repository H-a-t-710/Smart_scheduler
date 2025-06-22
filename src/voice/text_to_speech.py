import asyncio
import io
import logging
from typing import Optional, BinaryIO
import httpx
try:
    # Try new ElevenLabs API (v1.0+)
    from elevenlabs.client import ElevenLabs
    from elevenlabs import Voice
    NEW_ELEVENLABS_API = True
except ImportError:
    try:
        # Try old ElevenLabs API (v0.x)
        from elevenlabs import generate, save, voices, Voice
        NEW_ELEVENLABS_API = False
    except ImportError:
        # Fallback - no ElevenLabs available
        NEW_ELEVENLABS_API = None
import pyaudio
import wave
import os
from pydub import AudioSegment
from config.environment import config

logger = logging.getLogger(__name__)

class TextToSpeechService:
    def __init__(self):
        if NEW_ELEVENLABS_API is None:
            logger.warning("ElevenLabs not available - TTS will be limited")
            self.client = None
        elif NEW_ELEVENLABS_API:
            self.client = ElevenLabs(api_key=config.ELEVENLABS_API_KEY)
        else:
            self.client = None

        self.voice_id = config.ELEVENLABS_VOICE_ID
        self.audio_player = pyaudio.PyAudio()

    async def get_available_voices(self):
        try:
            if NEW_ELEVENLABS_API is None:
                return []
            elif NEW_ELEVENLABS_API:
                voice_list = self.client.voices.get_all()
                return [(voice.voice_id, voice.name) for voice in voice_list.voices]
            else:
                voice_list = voices()
                return [(voice.voice_id, voice.name) for voice in voice_list]
        except Exception as e:
            logger.error(f"Error fetching voices: {e}")
            return []

    async def synthesize_speech(self, text: str, voice_id: Optional[str] = None) -> Optional[bytes]:
        try:
            if NEW_ELEVENLABS_API is None:
                logger.warning("ElevenLabs not available - returning None")
                return None

            voice_to_use = voice_id or self.voice_id

            if NEW_ELEVENLABS_API:
                audio = self.client.text_to_speech.convert(
                    voice_id=voice_to_use,
                    model_id="eleven_monolingual_v1",
                    text=text
                )
                if hasattr(audio, '__iter__') and not isinstance(audio, bytes):
                    audio = b''.join(audio)
                return audio
            else:
                audio = generate(
                    text=text,
                    voice=voice_to_use,
                    model="eleven_monolingual_v1",
                    stream=False
                )
                return audio

        except Exception as e:
            logger.error(f"Error synthesizing speech: {e}")
            return None

    async def synthesize_and_save(self, text: str, output_file: str, voice_id: Optional[str] = None) -> bool:
        try:
            audio_bytes = await self.synthesize_speech(text, voice_id)
            if audio_bytes:
                with open(output_file, 'wb') as f:
                    f.write(audio_bytes)
                return True
            return False
        except Exception as e:
            logger.error(f"Error saving synthesized speech: {e}")
            return False

    async def synthesize_and_play(self, text: str, voice_id: Optional[str] = None) -> bool:
        try:
            audio_bytes = await self.synthesize_speech(text, voice_id)
            if audio_bytes:
                await self.play_audio_bytes(audio_bytes)
                return True
            return False
        except Exception as e:
            logger.error(f"Error playing synthesized speech: {e}")
            return False

    async def play_audio_bytes(self, audio_bytes: bytes):
        try:
            # Save MP3 bytes to a temporary file
            temp_mp3_file = "temp_audio.mp3"
            temp_wav_file = "temp_audio.wav"
            
            with open(temp_mp3_file, 'wb') as f:
                f.write(audio_bytes)
            
            # Convert MP3 to WAV using pydub
            try:
                audio = AudioSegment.from_mp3(temp_mp3_file)
                audio.export(temp_wav_file, format="wav")
                
                # Play the WAV file
                await self.play_audio_file(temp_wav_file)
            except Exception as e:
                logger.error(f"Error converting MP3 to WAV: {e}")
                # Try direct playback as a fallback
                logger.info("Trying direct playback of audio bytes...")
                self._play_raw_audio_bytes(audio_bytes)
            
            # Clean up temporary files
            if os.path.exists(temp_mp3_file):
                os.remove(temp_mp3_file)
            if os.path.exists(temp_wav_file):
                os.remove(temp_wav_file)
                
        except Exception as e:
            logger.error(f"Error playing audio bytes: {e}")
    
    def _play_raw_audio_bytes(self, audio_bytes: bytes):
        """Direct playback of audio bytes using elevenlabs.play if available"""
        try:
            if NEW_ELEVENLABS_API:
                from elevenlabs import play
                play(audio_bytes)
            else:
                logger.warning("Direct audio playback not available")
        except Exception as e:
            logger.error(f"Error in direct audio playback: {e}")

    async def play_audio_file(self, audio_file_path: str):
        try:
            with wave.open(audio_file_path, 'rb') as wf:
                frames = wf.getnframes()
                sample_rate = wf.getframerate()
                channels = wf.getnchannels()
                sample_width = wf.getsampwidth()
                stream = self.audio_player.open(
                    format=self.audio_player.get_format_from_width(sample_width),
                    channels=channels,
                    rate=sample_rate,
                    output=True
                )
                chunk_size = 1024
                data = wf.readframes(chunk_size)
                while data:
                    stream.write(data)
                    data = wf.readframes(chunk_size)
                stream.stop_stream()
                stream.close()
        except Exception as e:
            logger.error(f"Error playing audio file: {e}")

    async def stream_synthesize_speech(self, text: str, voice_id: Optional[str] = None):
        try:
            if NEW_ELEVENLABS_API is None:
                logger.warning("ElevenLabs not available - cannot stream")
                return

            voice_to_use = voice_id or self.voice_id

            if NEW_ELEVENLABS_API:
                audio_stream = self.client.text_to_speech.convert(
                    voice_id=voice_to_use,
                    model_id="eleven_monolingual_v1",
                    text=text,
                    stream=True
                )
            else:
                audio_stream = generate(
                    text=text,
                    voice=voice_to_use,
                    model="eleven_monolingual_v1",
                    stream=True
                )

            stream = self.audio_player.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=22050,
                output=True
            )

            for chunk in audio_stream:
                if chunk:
                    stream.write(chunk)

            stream.stop_stream()
            stream.close()
        except Exception as e:
            logger.error(f"Error in streaming synthesis: {e}")

    def cleanup(self):
        if self.audio_player:
            self.audio_player.terminate()

class VoiceManager:
    def __init__(self):
        self.tts_service = TextToSpeechService()
        self.current_voice_id = config.ELEVENLABS_VOICE_ID
        self.voice_cache = {}

    async def initialize(self):
        try:
            voices_list = await self.tts_service.get_available_voices()
            self.voice_cache = {name: voice_id for voice_id, name in voices_list}
            logger.info(f"Loaded {len(self.voice_cache)} voices")
        except Exception as e:
            logger.error(f"Error initializing voice manager: {e}")

    async def set_voice_by_name(self, voice_name: str) -> bool:
        if voice_name in self.voice_cache:
            self.current_voice_id = self.voice_cache[voice_name]
            return True
        return False

    async def speak_text(self, text: str, voice_name: Optional[str] = None) -> bool:
        voice_id = self.voice_cache.get(voice_name, self.current_voice_id)
        return await self.tts_service.synthesize_and_play(text, voice_id)

    async def speak_with_streaming(self, text: str, voice_name: Optional[str] = None):
        voice_id = self.voice_cache.get(voice_name, self.current_voice_id)
        await self.tts_service.stream_synthesize_speech(text, voice_id)

    def get_available_voices(self) -> list:
        return list(self.voice_cache.keys())

    def cleanup(self):
        if self.tts_service:
            self.tts_service.cleanup()

class GoogleTextToSpeechService:
    def __init__(self):
        try:
            from google.cloud import texttospeech
            self.client = texttospeech.TextToSpeechClient()
            self.voice = texttospeech.VoiceSelectionParams(
                language_code=config.DEFAULT_VOICE_LANGUAGE,
                ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL
            )
            self.audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.LINEAR16,
                sample_rate_hertz=config.AUDIO_SAMPLE_RATE
            )
            self.audio_player = pyaudio.PyAudio()
        except ImportError:
            logger.warning("Google Cloud Text-to-Speech not available")
            self.client = None

    async def synthesize_speech(self, text: str) -> Optional[bytes]:
        if not self.client:
            return None
        try:
            from google.cloud import texttospeech
            synthesis_input = texttospeech.SynthesisInput(text=text)
            response = self.client.synthesize_speech(
                input=synthesis_input,
                voice=self.voice,
                audio_config=self.audio_config
            )
            return response.audio_content
        except Exception as e:
            logger.error(f"Error with Google TTS: {e}")
            return None

    async def synthesize_and_play(self, text: str) -> bool:
        audio_bytes = await self.synthesize_speech(text)
        if audio_bytes:
            stream = self.audio_player.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=config.AUDIO_SAMPLE_RATE,
                output=True
            )
            stream.write(audio_bytes)
            stream.stop_stream()
            stream.close()
            return True
        return False
