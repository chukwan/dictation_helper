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

import requests
import base64
import json

async def generate_speech_bytes(text, rate, voice="en-US-AriaNeural", provider="edge"):
    """
    Generates MP3 audio bytes for the given text using edge-tts or Google Cloud TTS.
    """
    if provider == "google":
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY not found.")
            
        url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={api_key}"
        
        # Google TTS doesn't support "rate" like "+50%" directly in the same way.
        # It uses "speakingRate" (0.25 to 4.0).
        # We need to map our rate string (e.g. "-20%") to a float.
        # Default is 1.0.
        speaking_rate = 1.0
        try:
            if rate.endswith("%"):
                # "-20%" -> -0.2 -> 0.8
                percent = int(rate.strip("%"))
                speaking_rate = 1.0 + (percent / 100.0)
        except:
            pass
            
        # Clamp rate
        speaking_rate = max(0.25, min(4.0, speaking_rate))

        data = {
            "input": {"text": text},
            "voice": {"languageCode": voice.split("-")[0] + "-" + voice.split("-")[1], "name": voice},
            "audioConfig": {"audioEncoding": "MP3", "speakingRate": speaking_rate}
        }
        
        # Run synchronous request in async function
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: requests.post(url, headers={"Content-Type": "application/json"}, data=json.dumps(data)))
        
        if response.status_code == 200:
            json_response = response.json()
            return base64.b64decode(json_response["audioContent"])
        else:
            raise Exception(f"Google TTS API failed: {response.text}")

    else:
        # Edge TTS
        communicate = edge_tts.Communicate(text, voice, rate=rate)
        mp3_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                mp3_data += chunk["data"]
        return mp3_data

def create_silence(duration_ms):
    return AudioSegment.silent(duration=duration_ms)

def clean_text_for_reading(text, language="en"):
    """
    Replaces punctuation with spoken words for dictation practice.
    Supports English ('en') and Traditional Chinese ('zh-tw').
    """
    if language == "zh-tw":
        replacements = {
            "，": " 逗號 ",
            "。": " 句號 ",
            "？": " 問號 ",
            "！": " 驚嘆號 ",
            "；": " 分號 ",
            "：": " 冒號 ",
            "「": " 上引號 ",
            "」": " 下引號 ",
            "（": " 左括號 ",
            "）": " 右括號 ",
            "、": " 頓號 ",
            ".": " 句號 ", # Handle standard punctuation in Chinese text too
            ",": " 逗號 ",
            "?": " 問號 ",
            "!": " 驚嘆號 "
        }
    else:
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
    
    # Sort keys by length descending to avoid partial replacements
    sorted_keys = sorted(replacements.keys(), key=len, reverse=True)
    
    # Escape keys for regex
    pattern = re.compile("|".join(re.escape(k) for k in sorted_keys))
    
    text = pattern.sub(lambda m: replacements[m.group(0)], text)
    
    # Collapse multiple spaces
    return re.sub(r'\s+', ' ', text).strip()

def split_into_sentences(text):
    """
    Splits text into sentences.
    Simple split by period, question mark, exclamation mark (English and Chinese).
    """
    # Split by [.?!] or [。？！]
    sentences = re.split(r'(?<=[.?!。？！])\s*', text)
    return [s.strip() for s in sentences if s.strip()]

async def process_vocabulary(vocab_list, rate, repeats=1, silence_duration_sec=3, shuffle=False, voice="en-US-AriaNeural", provider="edge"):
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
        word_bytes = await generate_speech_bytes(word, rate, voice=voice, provider=provider)
        word_audio = AudioSegment.from_file(io.BytesIO(word_bytes), format="mp3")

        # For each word, repeat 'repeats' times with silence in between
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


async def process_passage(passage_text, rate, sentence_repeats=3, language="en", voice="en-US-AriaNeural", provider="edge"):
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
        spoken_sentence = clean_text_for_reading(sentence, language=language)
        
        # Generate audio for the modified sentence
        sentence_bytes = await generate_speech_bytes(spoken_sentence, rate, voice=voice, provider=provider)
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

# --- New Conversation Logic ---

import google.generativeai as genai

def analyze_transcript(text, num_speakers, language_code="zh-HK"):
    """
    Uses Gemini to analyze the transcript and split it into speaker segments.
    """
    try:
        model = genai.GenerativeModel('gemini-3-flash-preview')
        
        prompt = f"""
        Analyze the following text and split it into a conversation between up to {num_speakers} speakers.
        The text might be a script (e.g., "A: Hello") or just a story.
        
        Target Language: {language_code}
        
        Return a RAW JSON list of objects (no markdown blocks). Each object must have:
        - "speaker_id": integer (1 to {num_speakers})
        - "speaker": string (name of the speaker if detected, e.g. "Teacher", "Mary", otherwise "Speaker 1")
        - "text": string (the spoken content)
        
        Rules:
        1. If the text has explicit labels (like "A:", "Bob:"), use them to assign speaker IDs consistently.
        2. If no labels, try to infer speaker changes from context.
        3. Do not include stage directions or non-spoken text in the "text" field.
        
        Input Text:
        {text}
        """
        
        response = model.generate_content(prompt)
        content = response.text
        
        # Clean markdown
        if content.startswith("```json"):
            content = content[7:]
        if content.endswith("```"):
            content = content[:-3]
            
        return json.loads(content)
        
    except Exception as e:
        print(f"Error in analyze_transcript: {e}")
        return []

async def generate_conversation_audio(segments, language_code="zh-HK", provider="edge"):
    """
    Generates audio for a conversation list.
    segments: [{"speaker_id": 1, "text": "Hello"}, ...]
    """
    if not segments:
        return None
        
    # Define Voice Maps (limit to ~3-4 distinct voices per lang for now)
    # Edge TTS voices
    VOICE_MAP_EDGE = {
        "zh-HK": ["zh-HK-HiuGaaiNeural", "zh-HK-WanLungNeural", "zh-HK-HiuMinNeural"],
        "en-US": ["en-US-AriaNeural", "en-US-GuyNeural", "en-US-JennyNeural", "en-US-EricNeural"],
        "zh-CN": ["zh-CN-XiaoxiaoNeural", "zh-CN-YunxiNeural", "zh-CN-XiaoyiNeural", "zh-CN-YunjianNeural"],
    }
    
    # Fallback to English if not found
    available_voices = VOICE_MAP_EDGE.get(language_code, VOICE_MAP_EDGE["en-US"])
    
    temp_dir = tempfile.gettempdir()
    combined_audio = AudioSegment.empty()
    pause = AudioSegment.silent(duration=300) # 300ms pause between turns
    
    for seg in segments:
        text = seg.get("text", "")
        if not text:
            continue
            
        speaker_id = seg.get("speaker_id", 1)
        
        # Select voice based on speaker_id (round-robin)
        # speaker_id 1 -> index 0
        voice_index = (speaker_id - 1) % len(available_voices)
        selected_voice = available_voices[voice_index]
        
        try:
            # Generate audio for this segment
            # We use default rate "+0%" for conversation
            audio_bytes = await generate_speech_bytes(text, "+0%", voice=selected_voice, provider=provider)
            segment_audio = AudioSegment.from_file(io.BytesIO(audio_bytes), format="mp3")
            
            combined_audio += segment_audio + pause
            
        except Exception as e:
            print(f"Failed to generate segment for {speaker_id}: {e}")
            continue

    output_path = os.path.join(temp_dir, "conversation_output.mp3")
    combined_audio.export(output_path, format="mp3")
    return output_path
