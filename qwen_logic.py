import torch
import soundfile as sf
import io
import logging
import gc
from qwen_tts import Qwen3TTSModel

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global model cache
_model = None
_tokenizer = None
# _device = "cuda" if torch.cuda.is_available() else "cpu"
_device = "cpu" # Fallback to CPU due to RTX 5090 Torch support issue

# Default to CustomVoice model for preset speakers
MODEL_ID = "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice" 

def get_device():
    return _device

def load_model(model_id=None):
    global _model, _device
    
    current_model_id = model_id if model_id else MODEL_ID
        
    if _model is not None:
        return _model

    logger.info(f"Loading Qwen model: {current_model_id} on {_device}...")
    
    try:
        # Load model using Qwen3TTSModel API
        # Using bfloat16 is recommended in README, but requires Ampere+ (RTX 5090 is Blackwell, so yes)
        dtype = torch.bfloat16 if _device == "cuda" and torch.cuda.is_bf16_supported() else torch.float16
        
        _model = Qwen3TTSModel.from_pretrained(
            current_model_id,
            device_map=_device,
            dtype=dtype,
            # attn_implementation="flash_attention_2" # Optional: ensure installed if used
        )
        
        logger.info(f"Qwen model loaded successfully. Supported speakers: {_model.get_supported_speakers()}")
        return _model
    except Exception as e:
        logger.error(f"Failed to load Qwen model: {e}")
        print(f"DEBUG: Detailed load error: {e}")
        import traceback
        traceback.print_exc()
        return None

def unload_model():
    global _model
    if _model is not None:
        del _model
        _model = None
        if _device == "cuda":
            torch.cuda.empty_cache()
        gc.collect()
        logger.info("Qwen model unloaded.")

def generate_voice(text, speaker, language="Auto"):
    """
    Generate audio using Qwen3-TTS CustomVoice model.
    """
    model = load_model()
    if not model:
        return None
        
    try:
        logger.info(f"Generating audio for: '{text[:20]}...' Speaker: {speaker}")
        wavs, sr = model.generate_custom_voice(
            text=text,
            language=language,
            speaker=speaker
        )
        
        # Convert to bytes (mp3) implementation logic
        # Qwen returns (numpy_array, sample_rate)
        # We need to return valid audio bytes or path
        
        # Using io BytesIO and soundfile to write to buffer
        import numpy as np
        
        # Taking the first batch item (single inference)
        audio_data = wavs[0]
        
        buffer = io.BytesIO()
        sf.write(buffer, audio_data, sr, format='mp3')
        buffer.seek(0)
        return buffer.read()
        
    except Exception as e:
        logger.error(f"Generation failed: {e}")
        return None

def get_speakers():
    global _model
    if _model is not None:
        return _model.get_supported_speakers()
    return ['aiden', 'dylan', 'eric', 'ono_anna', 'ryan', 'serena', 'sohee', 'uncle_fu', 'vivian']


