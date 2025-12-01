import pytest
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from logic import clean_text_for_reading, split_into_sentences, process_vocabulary, process_passage, save_audio_file

def test_clean_text_for_reading():
    # English tests
    assert clean_text_for_reading("Hello, world.") == "Hello comma world period"
    assert clean_text_for_reading("What? No!") == "What question mark No exclamation mark"
    assert clean_text_for_reading("A-B") == "A hyphen B"
    
    # Chinese tests
    assert clean_text_for_reading("你好，世界。", language="zh-tw") == "你好 逗號 世界 句號"
    assert clean_text_for_reading("真的嗎？", language="zh-tw") == "真的嗎 問號"

def test_split_into_sentences():
    text = "Hello world. How are you? I am fine!"
    sentences = split_into_sentences(text)
    assert len(sentences) == 3
    assert sentences[0] == "Hello world."
    assert sentences[1] == "How are you?"
    assert sentences[2] == "I am fine!"
    
    # Chinese split
    text_zh = "你好。你好嗎？我很好！"
    sentences_zh = split_into_sentences(text_zh)
    assert len(sentences_zh) == 3
    assert sentences_zh[0] == "你好。"
    assert sentences_zh[1] == "你好嗎？"
    assert sentences_zh[2] == "我很好！"

@pytest.mark.asyncio
async def test_process_vocabulary():
    with patch('logic.generate_speech_bytes', new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = b'fake_mp3_bytes'
        
        with patch('pydub.AudioSegment.from_file') as mock_from_file, \
             patch('pydub.AudioSegment.empty') as mock_empty, \
             patch('pydub.AudioSegment.silent') as mock_silent:
            
            mock_audio = MagicMock()
            mock_from_file.return_value = mock_audio
            mock_empty.return_value = MagicMock()
            mock_silent.return_value = MagicMock()
            
            mock_audio.__add__.return_value = mock_audio
            mock_empty.return_value.__add__.return_value = mock_empty.return_value
            
            # Test with shuffle=False and specific voice
            path = await process_vocabulary(["test"], "+0%", repeats=2, silence_duration_sec=1, shuffle=False, voice="zh-TW-HsiaoChenNeural")
            assert mock_gen.call_count == 1
            # Verify voice was passed
            mock_gen.assert_called_with("test", "+0%", voice="zh-TW-HsiaoChenNeural")
            assert path is not None
            
            # Test with shuffle=True (mock random.shuffle)
            with patch('random.shuffle') as mock_shuffle:
                await process_vocabulary(["a", "b", "c"], "+0%", shuffle=True)
                mock_shuffle.assert_called_once()

def test_save_audio_file():
    with patch('os.makedirs') as mock_makedirs, \
         patch('shutil.copy2') as mock_copy, \
         patch('os.path.exists') as mock_exists, \
         patch('os.getcwd') as mock_getcwd:
         
        mock_exists.return_value = True
        mock_getcwd.return_value = "/fake/cwd"
        
        path = save_audio_file("/tmp/source.mp3", "My Recording", "vocab")
        
        mock_makedirs.assert_called_with(os.path.join("/fake/cwd", "recordings"), exist_ok=True)
        mock_copy.assert_called()
        assert "My_Recording_vocab.mp3" in path


@pytest.mark.asyncio
async def test_process_passage():
    with patch('logic.generate_speech_bytes', new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = b'fake_mp3_bytes'
        
        with patch('pydub.AudioSegment.from_file') as mock_from_file, \
             patch('pydub.AudioSegment.empty') as mock_empty, \
             patch('pydub.AudioSegment.silent') as mock_silent:
             
            mock_audio = MagicMock()
            mock_from_file.return_value = mock_audio
            mock_empty.return_value = MagicMock()
            mock_silent.return_value = MagicMock()
            
            mock_audio.__add__.return_value = mock_audio
            mock_empty.return_value.__add__.return_value = mock_empty.return_value

            # Test with Chinese language and voice
            path = await process_passage("你好。世界。", "+0%", sentence_repeats=2, language="zh-tw", voice="zh-TW-HsiaoChenNeural")
            
            # Should be called twice (once for each sentence)
            assert mock_gen.call_count == 2
            # Verify voice was passed
            mock_gen.assert_called_with("世界 句號", "+0%", voice="zh-TW-HsiaoChenNeural") # Check last call
            assert path is not None
            assert "passage_reading.mp3" in path
