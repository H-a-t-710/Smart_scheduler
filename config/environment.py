import os
from dotenv import load_dotenv
from typing import Optional

# Load environment variables
load_dotenv()

class Config:
    """Configuration class for the Smart Scheduler AI Agent"""
    
    # Google AI Studio Configuration
    GOOGLE_AI_API_KEY: str = os.getenv("GOOGLE_AI_API_KEY", "")
    MODEL_NAME: str = os.getenv("MODEL_NAME", "gemini-2.0-flash")
    MAX_TOKENS: int = int(os.getenv("MAX_TOKENS", "1000"))
    TEMPERATURE: float = float(os.getenv("TEMPERATURE", "0.7"))
    
    # ElevenLabs Configuration (TTS)
    ELEVENLABS_API_KEY: str = os.getenv("ELEVENLABS_API_KEY", "")
    ELEVENLABS_VOICE_ID: str = os.getenv("ELEVENLABS_VOICE_ID", "")
    
    # Google Cloud Configuration (STT and alternative TTS)
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    GOOGLE_CLOUD_PROJECT_ID: str = os.getenv("GOOGLE_CLOUD_PROJECT_ID", "")
    
    # Google Calendar API
    GOOGLE_CALENDAR_CREDENTIALS: str = os.getenv("GOOGLE_CALENDAR_CREDENTIALS")
    GOOGLE_CALENDAR_TOKEN: str = os.getenv("GOOGLE_CALENDAR_TOKEN")
    
    # Application Configuration
    APP_HOST: str = os.getenv("APP_HOST", "localhost")
    APP_PORT: int = int(os.getenv("APP_PORT", "8000"))
    DEBUG: bool = os.getenv("DEBUG", "True").lower() == "true"
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./smart_scheduler.db")
    
    # Voice Configuration
    DEFAULT_VOICE_LANGUAGE: str = os.getenv("DEFAULT_VOICE_LANGUAGE", "en-US")
    AUDIO_SAMPLE_RATE: int = int(os.getenv("AUDIO_SAMPLE_RATE", "16000"))
    AUDIO_CHUNK_SIZE: int = int(os.getenv("AUDIO_CHUNK_SIZE", "1024"))
    
    @classmethod
    def validate_config(cls):
        """Validate that all required configuration is present"""
        # Only Google AI API key is truly required
        required_vars = [
            ("GOOGLE_AI_API_KEY", cls.GOOGLE_AI_API_KEY),
        ]
        
        # Optional but recommended
        optional_vars = [
            ("ELEVENLABS_API_KEY", cls.ELEVENLABS_API_KEY, "Text-to-Speech will be limited"),
            ("GOOGLE_APPLICATION_CREDENTIALS", cls.GOOGLE_APPLICATION_CREDENTIALS, "Speech-to-Text will be limited"),
        ]
        
        missing_vars = [var_name for var_name, var_value in required_vars if not var_value]
        
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
        
        # Warn about missing optional vars
        for var_name, var_value, warning in optional_vars:
            if not var_value:
                print(f"⚠️  Warning: {var_name} not set - {warning}")
        
        return True

# Global config instance
config = Config() 