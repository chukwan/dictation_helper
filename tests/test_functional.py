import os
import pytest
import asyncio
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logic import extract_text_from_image, process_audio_generation, generate_speech_bytes
from dotenv import load_dotenv
import google.generativeai as genai

# Load environment variables
load_dotenv()

# Configure Gemini
api_key = os.getenv("GOOGLE_API_KEY")
if api_key:
    genai.configure(api_key=api_key)

TEST_IMAGE_PATH = os.path.join(os.path.dirname(__file__), "test-materials", "IMG_8201.JPEG")

@pytest.mark.asyncio
async def test_preview_sound_generation():
    """
    Tests that audio bytes are generated for a preview word.
    """
    word = "TestWord"
    try:
        # Use a safe rate and voice
        audio_bytes = await generate_speech_bytes(word, "+0%", voice="en-US-AriaNeural")
        assert audio_bytes is not None
        assert len(audio_bytes) > 0
        print("\nPreview audio generated successfully.")
    except Exception as e:
        pytest.fail(f"Preview generation failed: {e}")

@pytest.mark.asyncio
async def test_full_flow():
    """
    Functional test to verify the end-to-end flow:
    1. Extract text from the provided test image.
    2. Verify extracted content (vocabulary and passage).
    3. Generate audio for vocabulary and passage.
    4. Verify audio files are created and have content.
    """
    if not api_key:
        pytest.skip("GOOGLE_API_KEY not found in environment variables.")
        
    if not os.path.exists(TEST_IMAGE_PATH):
        pytest.fail(f"Test image not found at {TEST_IMAGE_PATH}")

    print(f"Testing with image: {TEST_IMAGE_PATH}")

    # 1. Extract Text
    with open(TEST_IMAGE_PATH, "rb") as f:
        image_bytes = f.read()
    
    data = extract_text_from_image(image_bytes)
    
    assert data is not None, "Failed to extract text from image."
    assert "vocabulary" in data, "Response missing 'vocabulary' key."
    assert "passage" in data, "Response missing 'passage' key."
    
    vocab_list = data["vocabulary"]
    passage_text = data["passage"]
    language = data.get("language", "en")
    
    print(f"Extracted {len(vocab_list)} vocabulary words.")
    print(f"Extracted passage of length {len(passage_text)}.")
    
    # Basic validation of extraction quality
    assert len(vocab_list) > 0, "No vocabulary words found."
    assert len(passage_text) > 0, "No passage text found."
    
    # Check for Chinese punctuation if language is Chinese, or common ones otherwise
    # The test image is zh-tw (from context), so let's check for '，' or '。'
    if language == "zh-tw":
        assert '，' in passage_text or '。' in passage_text, "Extracted passage is missing punctuation."


    # 2. Generate Audio
    # Using default settings for testing
    vocab_rate = "+0%"
    passage_rate = "+0%"
    vocab_repeats = 1
    vocab_silence = 1
    passage_repeats = 1
    shuffle_vocab = False
    voice = "en-US-AriaNeural" # Default voice, logic handles language mapping if needed or we can specify
    # Note: The app logic selects voice based on language. 
    # For this test, we'll just use a default or let the logic handle it if we passed the right params.
    # process_audio_generation expects specific voice string.
    # Let's pick a voice based on detected language to be safe, similar to app.py logic.
    
    if language == "zh-tw":
        voice = "zh-TW-HsiaoChenNeural"
    else:
        voice = "en-US-AriaNeural"
        
    provider = "edge" # Use Edge TTS for free testing

    vocab_path, passage_path = await process_audio_generation(
        vocab_list, 
        passage_text, 
        vocab_rate, 
        passage_rate, 
        vocab_repeats, 
        vocab_silence, 
        passage_repeats, 
        shuffle_vocab, 
        language, 
        voice, 
        provider
    )

    # 3. Verify Audio Files
    if vocab_list:
        assert vocab_path is not None, "Vocabulary audio path is None."
        assert os.path.exists(vocab_path), f"Vocabulary audio file not found at {vocab_path}"
        assert os.path.getsize(vocab_path) > 0, "Vocabulary audio file is empty."
        print(f"Vocabulary audio generated at: {vocab_path}")

    if passage_text:
        assert passage_path is not None, "Passage audio path is None."
        assert os.path.exists(passage_path), f"Passage audio file not found at {passage_path}"
        assert os.path.getsize(passage_path) > 0, "Passage audio file is empty."
        print(f"Passage audio generated at: {passage_path}")

if __name__ == "__main__":
    # Allow running directly with python
    loop = asyncio.get_event_loop()
    loop.run_until_complete(test_full_flow())
