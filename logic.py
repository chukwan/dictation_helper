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
        try:
            communicate = edge_tts.Communicate(text, voice, rate=rate)
            mp3_data = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    mp3_data += chunk["data"]
            if not mp3_data:
                raise Exception("No audio received from Edge TTS")
            return mp3_data
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Edge TTS failed: {e}. Falling back to gTTS (Google Translate TTS)...")
            # Fallback to gTTS
            # Map voice/lang roughly
            lang = "en"
            if "zh-" in voice.lower() or "cmn-" in voice.lower():
                # Check for Cantonese (HK usually implies Cantonese in this context, TW might be Mandarin or Cantonese but often users expecting Cantonese might select HK voices)
                # Google Translate TTS uses 'yue' for Cantonese.
                if "hk" in voice.lower():
                    lang = "yue"
                elif "tw" in voice.lower():
                     # Default TW to zh-tw (Mandarin) unless we want to support TW Cantonese? 
                     # Usually standard TW voice is Mandarin. 
                     # But let's check if the user selected a Cantonese specific voice. 
                     # The user said "picked cantonese", which usually means the language selection.
                     # In app.py: conv_lang == "Cantonese" -> lang_code = "zh-HK"
                     # So checking "hk" in voice (which comes from lang_code mapping) is the safest bet for "Cantonese".
                    lang = "zh-tw" 
                else:
                    lang = "zh-cn"
            
            from gtts import gTTS
            
            def run_gtts():
                fp = io.BytesIO()
                tts = gTTS(text=text, lang=lang)
                tts.write_to_fp(fp)
                fp.seek(0)
                return fp.read()

            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, run_gtts)

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
    # Split by [.?!] or [。？！] and now commas [,] or [，]
    sentences = re.split(r'(?<=[.?!,。？！，])\s*', text)
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

    # Avoid overwriting a different session's audio file
    if os.path.exists(dest_path):
        try:
            if os.path.samefile(source_path, dest_path):
                return dest_path  # Re-saving the same file, no action needed
        except (OSError, ValueError):
            pass
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{safe_name}_{suffix}_{timestamp}.mp3"
        dest_path = os.path.join(recordings_dir, filename)

    shutil.copy2(source_path, dest_path)
    return dest_path


async def process_passage(passage_text, rate, sentence_repeats=3, language="en", voice="en-US-AriaNeural", provider="edge", sentence_pause_sec=2.0, repeat_pause_sec=1.0):
    """
    Generates audio for passage with punctuation reading and sentence repetition.
    Returns path to generated file.
    """
    if not passage_text:
        return None

    temp_dir = tempfile.gettempdir()
    combined_passage_audio = AudioSegment.empty()
    silence_between_sentences = create_silence(sentence_pause_sec * 1000) # Configurable silence between sentences
    silence_between_repeats = create_silence(repeat_pause_sec * 1000) # Configurable silence between repeats of same sentence

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

def extract_text_from_image(image_bytes):
    """
    Sends image to Gemini Flash to extract vocabulary, passage, and language.
    """
    import google.generativeai as genai
    from PIL import Image
    
    try:
        model = genai.GenerativeModel('gemini-3-flash-preview')
        
        prompt = """
        Analyze this image and extract the text for a dictation practice session.
        Return ONLY a raw JSON object (no markdown formatting) with the following structure:
        {
            "vocabulary": ["word1", "word2", ...],
            "passage": "The full passage text...",
            "language": "en" 
        }
        "language" should be "en" for English or "zh-tw" for Traditional Chinese. Default to "en" if unsure.
        
        IMPORTANT FOR CHINESE TEXT:
        - Extract the Chinese characters (Hanzi) AND all punctuation marks (，。？！、"").
        - The passage MUST include the original punctuation. Do not strip it.
        - Do NOT extract Pinyin or phonetic guides. 
        - If the image shows both Hanzi and Pinyin, extract ONLY the Hanzi and punctuation.
        
        If there is only vocabulary, leave "passage" as an empty string.
        If there is only a passage, leave "vocabulary" as an empty list.
        Ensure the JSON is valid.
        """
        
        # Convert bytes back to image for Gemini if needed, or pass bytes directly if supported.
        # Gemini Python SDK supports PIL Image.
        image = Image.open(io.BytesIO(image_bytes))
        
        response = model.generate_content([prompt, image])
        text = response.text
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Raw Gemini response: {text}")
        
        # Clean up potential markdown code blocks
        cleaned_text = text.strip()
        if cleaned_text.startswith("```json"):
            cleaned_text = cleaned_text[7:]
        if cleaned_text.endswith("```"):
            cleaned_text = cleaned_text[:-3]
        cleaned_text = cleaned_text.strip()
            
        return json.loads(cleaned_text)
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Error extracting text: {e}")
        if 'text' in locals():
             print(f"[{datetime.now().strftime('%H:%M:%S')}] Full response text that failed: {text}")
        return None

async def process_audio_generation(vocab_list, passage_text, vocab_rate, passage_rate, vocab_repeats, vocab_silence, passage_repeats, passage_sentence_pause, passage_repeat_pause, shuffle_vocab, language, voice, provider):
    """
    Orchestrates the audio generation process.
    Returns paths to the generated temporary files.
    """
    vocab_audio_path = None
    passage_audio_path = None

    # --- Process Vocabulary ---
    if vocab_list:
        vocab_audio_path = await process_vocabulary(vocab_list, vocab_rate, repeats=vocab_repeats, silence_duration_sec=vocab_silence, shuffle=shuffle_vocab, voice=voice, provider=provider)

    # --- Process Passage ---
    if passage_text:
        passage_audio_path = await process_passage(passage_text, passage_rate, sentence_repeats=passage_repeats, language=language, voice=voice, provider=provider, sentence_pause_sec=passage_sentence_pause, repeat_pause_sec=passage_repeat_pause)

    return vocab_audio_path, passage_audio_path
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
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Error in analyze_transcript: {e}")
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

    # Google Cloud TTS voices
    VOICE_MAP_GOOGLE = {
        "zh-HK": ["yue-HK-Standard-A", "yue-HK-Standard-B", "yue-HK-Standard-C", "yue-HK-Standard-D"],
        "en-US": ["en-US-Standard-A", "en-US-Standard-B", "en-US-Standard-C", "en-US-Standard-D"],
        "zh-CN": ["cmn-CN-Standard-A", "cmn-CN-Standard-B", "cmn-CN-Standard-C", "cmn-CN-Standard-D"],
    }
    
    voice_map = VOICE_MAP_GOOGLE if provider == "google" else VOICE_MAP_EDGE
    
    # Fallback to English if not found
    available_voices = voice_map.get(language_code, voice_map.get("en-US", []))
    
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
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Failed to generate segment for {speaker_id}: {e}")
            continue

    output_path = os.path.join(temp_dir, "conversation_output.mp3")
    combined_audio.export(output_path, format="mp3")
    return output_path

