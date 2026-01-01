
import asyncio
import os
import sys

# Ensure we can import logic
sys.path.append(os.getcwd())
from logic import generate_speech_bytes

async def test_fallback():
    print("Attempting to generate audio (expecting Edge TTS failure -> gTTS fallback)...")
    try:
        # "Hello" is simple. If Edge fails, it should print "Edge TTS failed..." and switch to gTTS.
        # We can't easily force Edge to fail unless it's already broken in this env (which it seems to be).
        # If Edge *suddenly works*, we still get audio.
        # If Edge fails, we get audio via gTTS.
        
        audio_bytes = await generate_speech_bytes("Hello Fallback", "+0%", voice="en-US-AriaNeural")
        
        if audio_bytes and len(audio_bytes) > 0:
            print(f"Success! Generated {len(audio_bytes)} bytes of audio.")
            # Check if it looks like MP3 headers? gTTS and Edge both produce MP3.
            # We mostly care that we got bytes back without crashing.
        else:
            print("Failure: Returned empty bytes.")
            
    except Exception as e:
        print(f"Critical Failure: {e}")

if __name__ == "__main__":
    asyncio.run(test_fallback())
