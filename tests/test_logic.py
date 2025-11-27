import pytest
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from logic import clean_text_for_reading, split_into_sentences, process_vocabulary, process_passage, save_audio_file

def test_clean_text_for_reading():
    assert clean_text_for_reading("Hello, world.") == "Hello comma world period"
    assert clean_text_for_reading("What? No!") == "What question mark No exclamation mark"
    assert clean_text_for_reading("A-B") == "A hyphen B"

def test_split_into_sentences():
    text = "Hello world. How are you? I am fine!"
    sentences = split_into_sentences(text)
    assert len(sentences) == 3
    assert sentences[0] == "Hello world."
    assert sentences[1] == "How are you?"
    assert sentences[2] == "I am fine!"

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
            
            # Test with shuffle=False
            path = await process_vocabulary(["test"], "+0%", repeats=2, silence_duration_sec=1, shuffle=False)
            assert mock_gen.call_count == 1
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

            path = await process_passage("Hello. World.", "+0%", sentence_repeats=2)
            
            # Should be called twice (once for each sentence)
            assert mock_gen.call_count == 2
            assert path is not None
            assert "passage_reading.mp3" in path
