import os
import re
import tempfile
import io
import asyncio
import edge_tts
from pydub import AudioSegment
import random
import shutil
from datetime import datetime

async def generate_speech_bytes(text, rate):
    """
    Generates MP3 audio bytes for the given text using edge-tts.
    """
    communicate = edge_tts.Communicate(text, "en-US-AriaNeural", rate=rate)
    mp3_data = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            mp3_data += chunk["data"]
    return mp3_data

def create_silence(duration_ms):
    return AudioSegment.silent(duration=duration_ms)

def clean_text_for_reading(text):
    """
    Replaces punctuation with spoken words for dictation practice.
    """
    replacements = {
        ".": " period ",
        ",": " comma ",
        "?": " question mark ",
        "!": " exclamation mark ",
        ";": " semi-colon ",
        ":": " colon ",
        "\"": " quote ",
        "'": " apostrophe ",
        "-": " hyphen ",
        "(": " open bracket ",
        ")": " close bracket "
    }
    
    # Sort keys by length descending to avoid partial replacements (though most are 1 char)
    sorted_keys = sorted(replacements.keys(), key=len, reverse=True)
    
    # Escape keys for regex
    pattern = re.compile("|".join(re.escape(k) for k in sorted_keys))
    
    text = pattern.sub(lambda m: replacements[m.group(0)], text)
    
    # Collapse multiple spaces
    return re.sub(r'\s+', ' ', text).strip()

def split_into_sentences(text):
    """
    Splits text into sentences.
    Simple split by period, question mark, exclamation mark.
    """
    # This regex splits by [.?!] followed by space or end of string, keeping the delimiter.
    # It's a basic implementation.
    sentences = re.split(r'(?<=[.?!])\s+', text)
    return [s.strip() for s in sentences if s.strip()]

async def process_vocabulary(vocab_list, rate, repeats=1, silence_duration_sec=3, shuffle=False):
    """
    Generates audio for vocabulary list with configurable repeats and silence.
    Returns path to generated file.
    """
    if not vocab_list:
        return None

    # Shuffle if requested
    processing_list = list(vocab_list)
    if shuffle:
        random.shuffle(processing_list)

    temp_dir = tempfile.gettempdir()
    combined_vocab_audio = AudioSegment.empty()
    silence = create_silence(silence_duration_sec * 1000)

    for i, word in enumerate(processing_list):
        word_bytes = await generate_speech_bytes(word, rate)
        word_audio = AudioSegment.from_file(io.BytesIO(word_bytes), format="mp3")

        # For each word, repeat 'repeats' times with silence in between
        # Pattern: (Word + Silence) * repeats
        
        segment = AudioSegment.empty()
        for _ in range(repeats):
            segment += word_audio + silence
        
        combined_vocab_audio += segment

    vocab_audio_path = os.path.join(temp_dir, "vocab_practice.mp3")
    combined_vocab_audio.export(vocab_audio_path, format="mp3")
    return vocab_audio_path

def save_audio_file(source_path, name, suffix):
    """
    Saves the audio file to the 'recordings' directory.
    """
    if not source_path or not os.path.exists(source_path):
        return None
        
    recordings_dir = os.path.join(os.getcwd(), "recordings")
    os.makedirs(recordings_dir, exist_ok=True)
    
    # Sanitize name
    safe_name = "".join([c if c.isalnum() or c in ('-', '_') else '_' for c in name]).strip('_')
    if not safe_name:
        safe_name = "recording"
        
    filename = f"{safe_name}_{suffix}.mp3"
    dest_path = os.path.join(recordings_dir, filename)
    
    shutil.copy2(source_path, dest_path)
    return dest_path


async def process_passage(passage_text, rate, sentence_repeats=3):
    """
    Generates audio for passage with punctuation reading and sentence repetition.
    Returns path to generated file.
    """
    if not passage_text:
        return None

    temp_dir = tempfile.gettempdir()
    combined_passage_audio = AudioSegment.empty()
    silence_between_sentences = create_silence(2000) # 2 seconds between sentences
    silence_between_repeats = create_silence(1000) # 1 second between repeats of same sentence

    sentences = split_into_sentences(passage_text)

    for sentence in sentences:
        # Convert punctuation to text
        spoken_sentence = clean_text_for_reading(sentence)
        
        # Generate audio for the modified sentence
        sentence_bytes = await generate_speech_bytes(spoken_sentence, rate)
        sentence_audio = AudioSegment.from_file(io.BytesIO(sentence_bytes), format="mp3")

        # Repeat the sentence
        sentence_block = AudioSegment.empty()
        for i in range(sentence_repeats):
            sentence_block += sentence_audio
            if i < sentence_repeats - 1:
                sentence_block += silence_between_repeats
        
        combined_passage_audio += sentence_block + silence_between_sentences

    passage_audio_path = os.path.join(temp_dir, "passage_reading.mp3")
    combined_passage_audio.export(passage_audio_path, format="mp3")
    return passage_audio_path
