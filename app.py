import streamlit as st
import os
import json
import asyncio
import edge_tts
from pydub import AudioSegment
import google.generativeai as genai
from dotenv import load_dotenv
from PIL import Image
import io
import tempfile
from datetime import datetime

# Load environment variables
load_dotenv()

# --- Configuration ---
st.set_page_config(page_title="Dictation Buddy", page_icon="📝", layout="wide")

# --- Sidebar ---
st.sidebar.title("Settings")

api_key = st.sidebar.text_input("Google API Key", value=os.getenv("GOOGLE_API_KEY", ""), type="password")
if not api_key:
    st.sidebar.warning("Please enter your Google API Key to proceed.")
    st.stop()

genai.configure(api_key=api_key)

speed_adjustment = st.sidebar.slider("Speech Rate Adjustment (%)", min_value=-50, max_value=50, value=-20, step=10)
speed_str = f"{speed_adjustment:+d}%"

# --- Helper Functions ---

@st.cache_data(show_spinner=False)
def extract_text_from_image(image_bytes):
    """
    Sends image to Gemini Flash to extract vocabulary, passage, and language.
    """
    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        
        prompt = """
        Analyze this image and extract the text for a dictation practice session.
        Return ONLY a raw JSON object (no markdown formatting) with the following structure:
        {
            "vocabulary": ["word1", "word2", ...],
            "passage": "The full passage text...",
            "language": "en" 
        }
        "language" should be "en" for English or "zh-tw" for Traditional Chinese. Default to "en" if unsure.
        If there is only vocabulary, leave "passage" as an empty string.
        If there is only a passage, leave "vocabulary" as an empty list.
        Ensure the JSON is valid.
        """
        
        # Convert bytes back to image for Gemini if needed, or pass bytes directly if supported.
        # Gemini Python SDK supports PIL Image.
        image = Image.open(io.BytesIO(image_bytes))
        
        response = model.generate_content([prompt, image])
        text = response.text
        
        # Clean up potential markdown code blocks
        if text.startswith("```json"):
            text = text[7:]
        if text.endswith("```"):
            text = text[:-3]
            
        return json.loads(text)
    except Exception as e:
        st.error(f"Error extracting text: {e}")
        return None

# Import logic from logic.py
from logic import process_vocabulary, process_passage, save_audio_file, generate_speech_bytes, split_into_sentences, clean_text_for_reading

async def process_audio_generation(vocab_list, passage_text, vocab_rate, passage_rate, vocab_repeats, vocab_silence, passage_repeats, shuffle_vocab, language, voice):
    """
    Orchestrates the audio generation process.
    Returns paths to the generated temporary files.
    """
    vocab_audio_path = None
    passage_audio_path = None

    # --- Process Vocabulary ---
    if vocab_list:
        with st.spinner("Generating Vocabulary Audio..."):
            vocab_audio_path = await process_vocabulary(vocab_list, vocab_rate, repeats=vocab_repeats, silence_duration_sec=vocab_silence, shuffle=shuffle_vocab, voice=voice)

    # --- Process Passage ---
    if passage_text:
        with st.spinner("Generating Passage Audio..."):
            passage_audio_path = await process_passage(passage_text, passage_rate, sentence_repeats=passage_repeats, language=language, voice=voice)

    return vocab_audio_path, passage_audio_path

async def generate_preview_audio(text, rate, voice):
    """Generates a single preview audio file for a word or sentence."""
    if not text:
        return None
    try:
        mp3_bytes = await generate_speech_bytes(text, rate, voice=voice)
        # We need a file path for st.audio
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
            f.write(mp3_bytes)
            return f.name
    except Exception:
        return None

# --- Main UI ---

st.title("Dictation Buddy 🎧")

tab1, tab2 = st.tabs(["Create Practice", "Recordings Library"])

with tab1:
    st.markdown("Upload a photo of your dictation sheet to generate practice audio.")

    uploaded_file = st.file_uploader("Choose an image...", type=["jpg", "png", "jpeg"])

    if uploaded_file is not None:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Image received: {uploaded_file.name}")
        # Display image
        st.image(uploaded_file, caption='Uploaded Image')
        
        # Extract Text
        if "extracted_data" not in st.session_state or st.session_state.get("last_uploaded_file") != uploaded_file.name:
            with st.spinner("Analyzing image with Gemini..."):
                # Read file buffer as bytes for caching key
                image_bytes = uploaded_file.getvalue()
                data = extract_text_from_image(image_bytes)
                
                if data:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Dictation content detected.")
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Language detected: {data.get('language', 'en')}")
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Vocabulary identified: {len(data.get('vocabulary', []))} words.")
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Passage identified: {len(data.get('passage', ''))} chars.")
                else:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Failed to detect dictation content.")

                st.session_state["extracted_data"] = data
                st.session_state["last_uploaded_file"] = uploaded_file.name
                # Clear preview cache on new file
                st.session_state["preview_cache"] = {}
        
        data = st.session_state.get("extracted_data")

        if data:
            # Determine Language and Voice Options
            detected_lang = data.get("language", "en")
            
            voice_options = {}
            if detected_lang == "zh-tw":
                voice_options = {
                    "HsiaoChen (Taiwan, Female, Soft)": "zh-TW-HsiaoChenNeural",
                    "HsiaoYu (Taiwan, Female, Crisp)": "zh-TW-HsiaoYuNeural",
                    "YunJhe (Taiwan, Male, Gentle)": "zh-TW-YunJheNeural",
                    "Xiaoxiao (Mainland, Female, Warm)": "zh-CN-XiaoxiaoNeural"
                }
            else:
                voice_options = {
                    "Aria (US, Female)": "en-US-AriaNeural",
                    "Guy (US, Male)": "en-US-GuyNeural",
                    "Sonia (UK, Female)": "en-GB-SoniaNeural"
                }
            
            st.divider()
            st.subheader("Review & Edit Content")
            
            # Voice Selection UI
            c_lang, c_voice = st.columns([1, 3])
            with c_lang:
                st.info(f"Detected Language: {detected_lang}")
            with c_voice:
                selected_voice_label = st.selectbox("Select Voice", list(voice_options.keys()))
                selected_voice = voice_options[selected_voice_label]

            col1, col2 = st.columns(2)
            
            # --- Vocabulary Section ---
            with col1:
                st.markdown("**Vocabulary List**")
                
                # Initialize vocab list in session state if not present
                if "vocab_list" not in st.session_state:
                    st.session_state["vocab_list"] = data.get("vocabulary", [])

                # Display list with previews
                updated_vocab_list = []
                for i, word in enumerate(st.session_state["vocab_list"]):
                    c1, c2 = st.columns([3, 1])
                    with c1:
                        new_word = st.text_input(f"Word {i+1}", value=word, key=f"vocab_{i}")
                        updated_vocab_list.append(new_word)
                    with c2:
                        # Preview Button
                        preview_key = f"vocab_preview_{i}_{new_word}_{speed_str}_{selected_voice}"
                        if preview_key not in st.session_state.get("preview_cache", {}):
                             # Generate preview on the fly (async in sync context workaround)
                             try:
                                loop = asyncio.new_event_loop()
                                asyncio.set_event_loop(loop)
                                path = loop.run_until_complete(generate_preview_audio(new_word, speed_str, selected_voice))
                                loop.close()
                                if "preview_cache" not in st.session_state:
                                    st.session_state["preview_cache"] = {}
                                st.session_state["preview_cache"][preview_key] = path
                                print(f"[{datetime.now().strftime('%H:%M:%S')}] Preview generated for word: {new_word}")
                             except Exception as e:
                                 print(f"[{datetime.now().strftime('%H:%M:%S')}] Failed to generate preview for word {new_word}: {e}")
                        
                        audio_path = st.session_state.get("preview_cache", {}).get(preview_key)
                        if audio_path:
                            st.audio(audio_path, format="audio/mp3")

                st.session_state["vocab_list"] = updated_vocab_list
                vocab_list = [w for w in updated_vocab_list if w.strip()]
                
                st.markdown("---")
                st.markdown("**Vocabulary Settings**")
                vocab_repeats = st.number_input("Repeats per word", min_value=1, max_value=5, value=2)
                vocab_silence = st.number_input("Silence duration (seconds)", min_value=1, max_value=10, value=3)
                shuffle_vocab = st.checkbox("Shuffle Vocabulary Order")

            # --- Passage Section ---
            with col2:
                st.markdown("**Passage Text**")
                passage_text = st.text_area(
                    "Edit the passage if needed:",
                    value=data.get("passage", ""),
                    height=300,
                    key="passage_text_area"
                )
                
                st.markdown("**Passage Settings**")
                passage_repeats = st.number_input("Repeats per sentence", min_value=1, max_value=5, value=3)
                
                # Passage Speed Control
                passage_speed_adj = st.slider("Passage Speed Adjustment (%)", min_value=-50, max_value=50, value=-20, step=10, key="passage_speed")
                passage_speed_str = f"{passage_speed_adj:+d}%"

                # Passage Previews
                if passage_text:
                    st.markdown("**Sentence Previews**")
                    sentences = split_into_sentences(passage_text)
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Passage split into {len(sentences)} sentences.")

                    for i, sentence in enumerate(sentences):
                        c1, c2 = st.columns([3, 1])
                        with c1:
                            st.caption(f"{i+1}. {sentence}")
                        with c2:
                             preview_key = f"passage_preview_{i}_{sentence[:20]}_{passage_speed_str}_{selected_voice}"
                             if preview_key not in st.session_state.get("preview_cache", {}):
                                 try:
                                    loop = asyncio.new_event_loop()
                                    asyncio.set_event_loop(loop)
                                    # Clean text for reading (punctuation to words)
                                    spoken_sentence = clean_text_for_reading(sentence, language=detected_lang)
                                    path = loop.run_until_complete(generate_preview_audio(spoken_sentence, passage_speed_str, selected_voice))
                                    loop.close()
                                    if "preview_cache" not in st.session_state:
                                        st.session_state["preview_cache"] = {}
                                    st.session_state["preview_cache"][preview_key] = path
                                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Sentence preview generated: {sentence[:20]}...")
                                 except Exception as e:
                                     print(f"[{datetime.now().strftime('%H:%M:%S')}] Failed to generate preview for sentence {i}: {e}")
                             
                             audio_path = st.session_state.get("preview_cache", {}).get(preview_key)
                             if audio_path:
                                st.audio(audio_path, format="audio/mp3")

            st.divider()
            
            if st.button("Generate Audio 🎵", type="primary"):
                # Run async audio generation
                try:
                    # Handle async loop for Streamlit
                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                    
                    if loop.is_running():
                        vocab_path, passage_path = loop.run_until_complete(process_audio_generation(vocab_list, passage_text, speed_str, passage_speed_str, vocab_repeats, vocab_silence, passage_repeats, shuffle_vocab, detected_lang, selected_voice))
                    else:
                         vocab_path, passage_path = loop.run_until_complete(process_audio_generation(vocab_list, passage_text, speed_str, passage_speed_str, vocab_repeats, vocab_silence, passage_repeats, shuffle_vocab, detected_lang, selected_voice))

                    st.session_state["generated_vocab_path"] = vocab_path
                    st.session_state["generated_passage_path"] = passage_path
                    st.success("Audio Generation Complete!")
                    
                except Exception as e:
                    st.error(f"An error occurred during audio generation: {e}")

            # Display Generated Audio & Save Options
            if st.session_state.get("generated_vocab_path") or st.session_state.get("generated_passage_path"):
                st.divider()
                st.subheader("Final Audio")
                
                if st.session_state.get("generated_vocab_path"):
                    st.markdown("### Part A: Vocabulary Practice")
                    st.audio(st.session_state["generated_vocab_path"], format="audio/mp3")
                    with open(st.session_state["generated_vocab_path"], "rb") as f:
                         st.download_button("Download Vocab Audio", f, file_name="vocab_practice.mp3")

                if st.session_state.get("generated_passage_path"):
                    st.markdown("### Part B: Passage Reading")
                    st.audio(st.session_state["generated_passage_path"], format="audio/mp3")
                    with open(st.session_state["generated_passage_path"], "rb") as f:
                        st.download_button("Download Passage Audio", f, file_name="passage_reading.mp3")
                
                st.divider()
                st.subheader("Save to Library")
                with st.form("save_form"):
                    save_name = st.text_input("Enter a name for this recording session:", value="My_Dictation")
                    submitted = st.form_submit_button("Save Recordings")
                    if submitted:
                        saved_files = []
                        if st.session_state.get("generated_vocab_path"):
                            path = save_audio_file(st.session_state["generated_vocab_path"], save_name, "vocab")
                            if path: saved_files.append(os.path.basename(path))
                        
                        if st.session_state.get("generated_passage_path"):
                            path = save_audio_file(st.session_state["generated_passage_path"], save_name, "passage")
                            if path: saved_files.append(os.path.basename(path))
                        
                        if saved_files:
                            st.success(f"Saved: {', '.join(saved_files)}")
                        else:
                            st.warning("No files to save.")

with tab2:
    st.header("Recordings Library")
    recordings_dir = os.path.join(os.getcwd(), "recordings")
    
    if not os.path.exists(recordings_dir):
        st.info("No recordings found yet.")
    else:
        files = [f for f in os.listdir(recordings_dir) if f.endswith(".mp3")]
        if not files:
            st.info("No recordings found yet.")
        else:
            # Sort by modification time (newest first)
            files.sort(key=lambda x: os.path.getmtime(os.path.join(recordings_dir, x)), reverse=True)
            
            for filename in files:
                filepath = os.path.join(recordings_dir, filename)
                with st.expander(filename):
                    st.audio(filepath, format="audio/mp3")
                    with open(filepath, "rb") as f:
                        st.download_button(f"Download {filename}", f, file_name=filename)
