import os
from pydub import AudioSegment
import logging

logger = logging.getLogger(__name__)

def setup_ffmpeg():
    # Determine the project root from this file's location
    # Go up one directory from config/ to reach smart_scheduler/
    PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

    # Define the path to your ffmpeg.exe and ffprobe.exe within the project
    FFMPEG_PATH = os.path.join(PROJECT_ROOT, 'bin', 'ffmpeg', 'ffmpeg.exe')
    FFPROBE_PATH = os.path.join(PROJECT_ROOT, 'bin', 'ffmpeg', 'ffprobe.exe')
    FFMPEG_DIR = os.path.dirname(FFMPEG_PATH)

    # Add ffmpeg directory to PATH for Whisper and other tools
    if FFMPEG_DIR not in os.environ["PATH"]:
        os.environ["PATH"] = FFMPEG_DIR + os.pathsep + os.environ["PATH"]

    # Configure pydub if the executables are found
    if os.path.exists(FFMPEG_PATH) and os.path.exists(FFPROBE_PATH):
        AudioSegment.converter = FFMPEG_PATH
        AudioSegment.probe = FFPROBE_PATH
        logger.info(f"FFmpeg configured successfully at {FFMPEG_PATH}")
    else:
        logger.warning(f"FFmpeg executables not found at {FFMPEG_PATH} or {FFPROBE_PATH}. "
                        "Audio processing with pydub may be limited or fail. "
                        "Please download FFmpeg and place ffmpeg.exe and ffprobe.exe "
                        "in the 'bin/ffmpeg' folder inside your project root.")

# Call setup_ffmpeg immediately when this module is imported
setup_ffmpeg() 