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
import database

# Load environment variables
load_dotenv()

# Initialize Database
database.init_db()

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

# Import logic from logic.py
from logic import (
    process_vocabulary, process_passage, save_audio_file, generate_speech_bytes, 
    split_into_sentences, clean_text_for_reading, extract_text_from_image, 
    process_audio_generation, analyze_transcript, generate_conversation_audio
)

# Import Qwen Logic (Lazy load or try/except to avoid crash if not installed)
try:
    import qwen_logic
except ImportError:
    qwen_logic = None



# Wrap extract_text_from_image with cache for Streamlit
@st.cache_data(show_spinner=False)
def cached_extract_text_from_image(image_bytes):
    return extract_text_from_image(image_bytes)

async def generate_preview_audio(text, rate, voice, provider):
    """Generates a single preview audio file for a word or sentence."""
    if not text:
        return None
    try:
        mp3_bytes = await generate_speech_bytes(text, rate, voice=voice, provider=provider)
        # We need a file path for st.audio
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
            f.write(mp3_bytes)
            return f.name
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Preview generation failed: {e}")
        return None

# --- Main UI ---

st.title("Dictation Buddy 🎧")

tab1, tab2, tab3, tab4 = st.tabs(["Create Practice", "Recordings Library", "Conversation Generator", "Qwen Script Builder"])

with tab3:
    st.header("Conversation Generator")
    st.markdown("Generate multi-speaker audio from a transcript.")
    
    col_input, col_settings = st.columns([2, 1])
    
    with col_settings:
        conv_lang = st.selectbox("Language", ["Cantonese", "English", "Mandarin"], index=0)
        num_speakers = st.number_input("Number of Speakers", min_value=1, max_value=5, value=2)
        
        # Map friendly name to code
        lang_code = "zh-HK"
        if conv_lang == "English": lang_code = "en-US"
        elif conv_lang == "Mandarin": lang_code = "zh-CN"
        
        conv_provider = st.radio("Provider", ["Edge TTS (Free)", "Google Cloud TTS"], key="conv_provider")
        conv_provider_code = "google" if conv_provider == "Google Cloud TTS" else "edge"

    with col_input:
        transcript_text = st.text_area("Enter Transcript / Dialogue", height=300,  placeholder="Teacher: Hello everyone.\nStudent: Good morning!")
    
    if st.button("Analyze Transcript", type="primary"):
        if not transcript_text:
            st.warning("Please enter some text.")
        else:
            with st.spinner("Analyzing speakers..."):
                segments = analyze_transcript(transcript_text, num_speakers, lang_code)
                st.session_state["conv_segments"] = segments
                st.session_state["conv_lang"] = lang_code # Store for generation
    
    # Display Segments if available
    if "conv_segments" in st.session_state and st.session_state["conv_segments"]:
        st.divider()
        st.subheader("Detected Segments")
        
        segments = st.session_state["conv_segments"]
        updated_segments = []
        
        for i, seg in enumerate(segments):
            c1, c2 = st.columns([1, 4])
            with c1:
                speaker_label = st.text_input(f"Speaker", value=seg.get("speaker", f"Speaker {seg.get('speaker_id', '?')}"), key=f"s_lbl_{i}")
            with c2:
                text_content = st.text_area(f"Text", value=seg.get("text", ""), key=f"s_txt_{i}", height=70)
            
            updated_segments.append({"speaker": speaker_label, "text": text_content, "speaker_id": seg.get("speaker_id")})
        
        st.session_state["conv_segments"] = updated_segments

        if st.button("Generate Conversation Audio", type="primary"):
            with st.spinner("Synthesizing conversation..."):
                try:
                    # Async handling
                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                    
                    final_audio_path = loop.run_until_complete(generate_conversation_audio(updated_segments, lang_code, conv_provider_code))
                    
                    if final_audio_path:
                        st.session_state["conv_audio_path"] = final_audio_path
                        st.success("Conversation Audio Generated!")
                    else:
                        st.error("Failed to generate audio.")
                        
                except Exception as e:
                     st.error(f"Error: {e}")

        if st.session_state.get("conv_audio_path"):
            st.audio(st.session_state["conv_audio_path"], format="audio/mp3")
            with open(st.session_state["conv_audio_path"], "rb") as f:
                st.download_button("Download Conversation", f, file_name="conversation.mp3")


with tab1:
    # Check if a session is currently loaded
    loaded_session_id = st.session_state.get("loaded_session_id")
    
    if loaded_session_id:
        st.info(f"Editing Loaded Session: **{st.session_state.get('loaded_session_name', 'Unknown')}**")
        if st.button("Start New Session (Clear Logic)", type="secondary"):
            # Clear all session state related to current session
            keys_to_clear = ["extracted_data", "vocab_list", "loaded_session_id", "loaded_session_name", "last_uploaded_files", "preview_cache"]
            for k in keys_to_clear:
                if k in st.session_state:
                    del st.session_state[k]
            st.rerun()
    else:
        st.markdown("Upload photos of your dictation sheet (max 5) to generate practice audio.")

        uploaded_files = st.file_uploader("Choose images...", type=["jpg", "png", "jpeg"], accept_multiple_files=True)

        if uploaded_files:
            if len(uploaded_files) > 5:
                st.warning(f"You uploaded {len(uploaded_files)} images. Only the first 5 will be processed.")
                uploaded_files = uploaded_files[:5]
            
            # Create a unique key for the set of files to prevent re-processing on every rerun if unchanged
            current_files_key = ",".join([f.name for f in uploaded_files])
            
            st.write(f"Processing {len(uploaded_files)} images...")
            
            # Extract Text
            if "extracted_data" not in st.session_state or st.session_state.get("last_uploaded_files") != current_files_key:
                
                # Aggregation containers
                all_vocab = []
                all_passage_parts = []
                detected_language = "en" # Default to en, update with first detection
                
                with st.spinner("Analyzing images with Gemini..."):
                    progress_bar = st.progress(0)
                    
                    for idx, uploaded_file in enumerate(uploaded_files):
                        # Read file buffer as bytes for caching key
                        image_bytes = uploaded_file.getvalue()
                        data = cached_extract_text_from_image(image_bytes)
                        
                        if data:
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] Image {idx+1} processed.")
                            
                            # Aggregate Vocabulary
                            new_vocab = data.get("vocabulary", [])
                            if new_vocab:
                                all_vocab.extend(new_vocab)
                                
                            # Aggregate Passage
                            new_passage = data.get("passage", "")
                            if new_passage:
                                all_passage_parts.append(new_passage)
                                
                            # Capture language from the first file that has it
                            if idx == 0:
                                detected_language = data.get("language", "en")
                        else:
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] Failed to detect dictation content in image {idx+1}.")
                        
                        progress_bar.progress((idx + 1) / len(uploaded_files))

                # Combine results
                final_data = {
                    "vocabulary": list(dict.fromkeys(all_vocab)), # Remove duplicates
                    "passage": "\n\n".join(all_passage_parts),
                    "language": detected_language
                }

                st.session_state["extracted_data"] = final_data
                st.session_state["last_uploaded_files"] = current_files_key
                # Clear preview cache on new file set
                st.session_state["preview_cache"] = {}
                
                st.success("Analysis Complete!")
        
    data = st.session_state.get("extracted_data")

    if data:
        # Determine Language and Voice Options
        detected_lang = data.get("language", "en")
        
        st.divider()
        st.subheader("Review & Edit Content")
        
        # --- TTS Settings ---
        c_lang, c_provider, c_voice = st.columns([1, 2, 3])
        
        with c_lang:
            st.info(f"Detected: {detected_lang}")
            
        with c_provider:
            tts_provider = st.radio("TTS Provider", ["Edge TTS (Free)", "Google Cloud TTS"], horizontal=True)
            provider_code = "google" if tts_provider == "Google Cloud TTS" else "edge"

        with c_voice:
            voice_options = {}
            if provider_code == "edge":
                if detected_lang == "zh-tw":
                    voice_options = {
                        "HsiaoChen (Taiwan, Female, Soft)": "zh-TW-HsiaoChenNeural",
                        "HsiaoYu (Taiwan, Female, Crisp)": "zh-TW-HsiaoYuNeural",
                        "YunJhe (Taiwan, Male, Gentle)": "zh-TW-YunJheNeural",
                        "Xiaoxiao (Mainland, Female, Warm)": "zh-CN-XiaoxiaoNeural",
                        "Yunxi (Mainland, Male, Calm)": "zh-CN-YunxiNeural",
                        "Xiaoyi (Mainland, Female, Gentle)": "zh-CN-XiaoyiNeural",
                        "Yunjian (Mainland, Male, Sports)": "zh-CN-YunjianNeural"
                    }
                else:
                    voice_options = {
                        "Aria (US, Female)": "en-US-AriaNeural",
                        "Guy (US, Male)": "en-US-GuyNeural",
                        "Sonia (UK, Female)": "en-GB-SoniaNeural"
                    }
            else: # Google
                if detected_lang == "zh-tw":
                    voice_options = {
                        "Cantonese Standard A (HK, Female)": "yue-HK-Standard-A",
                        "Cantonese Standard B (HK, Male)": "yue-HK-Standard-B",
                        "Cantonese Standard C (HK, Female)": "yue-HK-Standard-C",
                        "Cantonese Standard D (HK, Male)": "yue-HK-Standard-D",
                        "Mandarin Standard A (Mainland, Female)": "cmn-CN-Standard-A",
                        "Mandarin Standard B (Mainland, Male)": "cmn-CN-Standard-B",
                        "Mandarin Standard C (Mainland, Male)": "cmn-CN-Standard-C",
                        "Mandarin TW Standard A (Taiwan, Female)": "cmn-TW-Standard-A",
                        "Mandarin TW Standard B (Taiwan, Male)": "cmn-TW-Standard-B",
                        "Mandarin TW Standard C (Taiwan, Male)": "cmn-TW-Standard-C"
                    }
                else:
                    voice_options = {
                        "Standard A (US, Male)": "en-US-Standard-A",
                        "Standard B (US, Male)": "en-US-Standard-B",
                        "Standard C (US, Female)": "en-US-Standard-C",
                        "Standard D (US, Male)": "en-US-Standard-D"
                    }

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
                    preview_key = f"vocab_preview_{i}_{new_word}_{speed_str}_{selected_voice}_{provider_code}"
                    cached_path = st.session_state.get("preview_cache", {}).get(preview_key)
                    
                    if not cached_path or not os.path.exists(cached_path):
                         # Generate preview on the fly
                         try:
                            # Use asyncio.run for safer loop management
                            path = asyncio.run(generate_preview_audio(new_word, speed_str, selected_voice, provider_code))
                            
                            if path:
                                if "preview_cache" not in st.session_state:
                                    st.session_state["preview_cache"] = {}
                                st.session_state["preview_cache"][preview_key] = path
                                print(f"[{datetime.now().strftime('%H:%M:%S')}] Preview generated for word: {new_word}")
                                cached_path = path
                            else:
                                st.caption("No audio generated.")
                         except Exception as e:
                             print(f"[{datetime.now().strftime('%H:%M:%S')}] Failed to generate preview for word {new_word}: {e}")
                             st.caption(f"⚠️ Preview error: {e}")

                    if cached_path:
                        st.audio(cached_path, format="audio/mp3")

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

                for i, sentence in enumerate(sentences):
                    c1, c2 = st.columns([3, 1])
                    with c1:
                        st.caption(f"{i+1}. {sentence}")
                    with c2:
                         preview_key = f"passage_preview_{i}_{sentence[:20]}_{passage_speed_str}_{selected_voice}_{provider_code}"
                         cached_path = st.session_state.get("preview_cache", {}).get(preview_key)
                         
                         if not cached_path or not os.path.exists(cached_path):
                             try:
                                spoken_sentence = clean_text_for_reading(sentence, language=detected_lang)
                                path = asyncio.run(generate_preview_audio(spoken_sentence, passage_speed_str, selected_voice, provider_code))
                                
                                if path:
                                    if "preview_cache" not in st.session_state:
                                        st.session_state["preview_cache"] = {}
                                    st.session_state["preview_cache"][preview_key] = path
                                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Sentence preview generated: {sentence[:20]}...")
                                    cached_path = path
                                else:
                                     st.caption("No audio.")
                             except Exception as e:
                                 print(f"[{datetime.now().strftime('%H:%M:%S')}] Failed to generate preview for sentence {i}: {e}")
                                 st.caption(f"⚠️ Error: {e}")
                         
                         if cached_path:
                            st.audio(cached_path, format="audio/mp3")

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
                
                with st.spinner("Generating Audio..."):
                    if loop.is_running():
                        vocab_path, passage_path = loop.run_until_complete(process_audio_generation(vocab_list, passage_text, speed_str, passage_speed_str, vocab_repeats, vocab_silence, passage_repeats, shuffle_vocab, detected_lang, selected_voice, provider_code))
                    else:
                         vocab_path, passage_path = loop.run_until_complete(process_audio_generation(vocab_list, passage_text, speed_str, passage_speed_str, vocab_repeats, vocab_silence, passage_repeats, shuffle_vocab, detected_lang, selected_voice, provider_code))

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
            # Save/Update Logic
            with st.form("save_form"):
                # If we loaded a session, default to its name
                default_name = "My_Dictation"
                loaded_session_id = st.session_state.get("loaded_session_id")
                
                if loaded_session_id:
                    # Fetch current name if possible, or just keep what's in input if user changed it
                    # For simplicity, we might just show the input. 
                    # If we want to show the loaded name, we should have set it in session_state when loading.
                    pass

                save_name = st.text_input("Enter a name for this recording session:", value=st.session_state.get("loaded_session_name", "My_Dictation"))
                
                # Dynamic button text
                submit_label = "Update Session" if loaded_session_id else "Save Recordings"
                submitted = st.form_submit_button(submit_label)
                
                if submitted:
                    saved_files = []
                    vocab_audio_path = None
                    passage_audio_path = None
                    
                    if st.session_state.get("generated_vocab_path"):
                        path = save_audio_file(st.session_state["generated_vocab_path"], save_name, "vocab")
                        if path: 
                            saved_files.append(os.path.basename(path))
                            vocab_audio_path = path
                    
                    if st.session_state.get("generated_passage_path"):
                        path = save_audio_file(st.session_state["generated_passage_path"], save_name, "passage")
                        if path: 
                            saved_files.append(os.path.basename(path))
                            passage_audio_path = path
                    
                    if saved_files:
                        # Save to Database
                        try:
                            if loaded_session_id:
                                # Update existing session
                                # First, optionally delete old files if we want to clean up.
                                # For now, we just update the DB record to point to new files.
                                database.update_session(
                                    session_id=loaded_session_id,
                                    vocab_list=vocab_list,
                                    vocab_audio_path=vocab_audio_path,
                                    sentences=sentences if 'sentences' in locals() else [],
                                    passage_audio_path=passage_audio_path,
                                    language=detected_lang
                                )
                                st.success(f"Session '{save_name}' updated successfully!")
                            else:
                                # Create new session
                                database.save_session(
                                    name=save_name,
                                    vocab_list=vocab_list,
                                    vocab_audio_path=vocab_audio_path,
                                    sentences=sentences if 'sentences' in locals() else [],
                                    passage_audio_path=passage_audio_path,
                                    language=detected_lang
                                )
                                st.success(f"Saved to Library & Database: {', '.join(saved_files)}")
                        except Exception as e:
                            st.error(f"Saved files but failed to save/update database: {e}")
                    else:
                        st.warning("No files to save.")

with tab2:
    st.header("Saved Sessions")
    
    sessions = database.get_all_sessions()
    
    if not sessions:
        st.info("No saved sessions found.")
    else:
        for session in sessions:
            session_id = session["id"]
            session_name = session["name"]
            created_at = session["created_at"]
            
            with st.expander(f"{session_name} ({created_at})"):
                # Fetch details
                vocab_list, sentences = database.get_session_details(session_id)
                
                # Load Session Button
                if st.button("Load Session", key=f"load_{session_id}"):
                    # Set session state variables
                    st.session_state["vocab_list"] = vocab_list
                    # Reconstruct extracted_data structure for consistency
                    st.session_state["extracted_data"] = {
                        "vocabulary": vocab_list,
                        "passage": " ".join(sentences), # Reconstruct passage from sentences
                        "language": session.get("language", "en")
                    }
                    st.session_state["loaded_session_id"] = session_id
                    st.session_state["loaded_session_name"] = session_name
                    
                    # Clear generated paths to force regeneration or at least show they aren't fresh yet
                    if "generated_vocab_path" in st.session_state: del st.session_state["generated_vocab_path"]
                    if "generated_passage_path" in st.session_state: del st.session_state["generated_passage_path"]
                    
                    st.success(f"Loaded session '{session_name}'. Switch to 'Create Practice' tab to edit.")
                    st.rerun()
                    # Optional: Force switch to tab 1 (not easily done in Streamlit without extra hacks, so just message)
                
                # Vocabulary Section
                if vocab_list:
                    st.subheader("Vocabulary")
                    st.write(", ".join(vocab_list))
                    if session["vocab_audio_path"] and os.path.exists(session["vocab_audio_path"]):
                        st.audio(session["vocab_audio_path"], format="audio/mp3")
                        with open(session["vocab_audio_path"], "rb") as f:
                            st.download_button(f"Download Vocab Audio", f, file_name=f"{session_name}_vocab.mp3", key=f"dl_vocab_{session_id}")
                
                # Passage Section
                if sentences:
                    st.subheader("Passage")
                    for i, sentence in enumerate(sentences):
                        st.write(f"{i+1}. {sentence}")
                    
                    if session["passage_audio_path"] and os.path.exists(session["passage_audio_path"]):
                        st.audio(session["passage_audio_path"], format="audio/mp3")
                        with open(session["passage_audio_path"], "rb") as f:
                            st.download_button(f"Download Passage Audio", f, file_name=f"{session_name}_passage.mp3", key=f"dl_passage_{session_id}")
                
                st.divider()
                if st.button("Delete Session", key=f"del_{session_id}", type="secondary"):
                    database.delete_session(session_id)
                    st.rerun()

with tab4:
    st.header("Qwen3-TTS Script Builder 🎙️")
    
    if qwen_logic is None:
        st.error("Qwen module not found. Please install dependencies.")
    else:
        # Sidebar-like column for settings
        c_main, c_config = st.columns([3, 1])
        
        with c_config:
            st.markdown("### Settings")
            st.info(f"Device: {qwen_logic.get_device()}")
            
            if st.button("Load Qwen Model", type="primary"):
                with st.spinner("Loading Model (1.7B)... this may take a moment"):
                    model = qwen_logic.load_model()
                    if model:
                        st.success("Model Loaded!")
                    else:
                        st.error("Failed to load model.")
            
            if st.button("Unload Model"):
                qwen_logic.unload_model()
                st.info("Model Unloaded.")

        with c_main:
            # Session State for Script
            if "qwen_script" not in st.session_state:
                st.session_state["qwen_script"] = [{"speaker": "Speaker 1", "text": ""}]
            
            # Speaker Config
            st.subheader("Speaker Settings")
            speakers_available = qwen_logic.get_speakers()
            # Default fallback if checking before model load
            if not speakers_available: 
                speakers_available = ["Vivian", "Ryan", "Classic Male", "Classic Female"] 

            col_s1, col_s2 = st.columns(2)
            with col_s1:
                st.markdown("🟡 **Speaker 1**")
                s1_name = st.text_input("Name", "Speaker 1", key="s1_name")
                s1_voice = st.selectbox("Voice", speakers_available, index=0, key="s1_voice")
            
            with col_s2:
                st.markdown("🟣 **Speaker 2**")
                s2_name = st.text_input("Name", "Speaker 2", key="s2_name")
                s2_voice = st.selectbox("Voice", speakers_available, index=1 if len(speakers_available)>1 else 0, key="s2_voice")
            
            st.divider()
            
            # Script Builder UI
            st.subheader("Script Builder")
            
            script_items = st.session_state["qwen_script"]
            new_script_items = []
            
            for idx, item in enumerate(script_items):
                c_spk, c_txt, c_act = st.columns([1, 4, 0.5])
                
                with c_spk:
                    # Select Speaker 1 or 2
                    current_spk = item.get("speaker", "Speaker 1")
                    options = ["Speaker 1", "Speaker 2"]
                    sel_idx = 0 if current_spk == "Speaker 1" else 1
                    
                    spk_sel = st.selectbox(
                        "Speaker", 
                        options, 
                        index=sel_idx, 
                        key=f"q_spk_{idx}", 
                        label_visibility="collapsed"
                    )
                    
                    # Visual indicator
                    if spk_sel == "Speaker 1":
                        st.caption(f"🟡 {s1_name}")
                    else:
                        st.caption(f"🟣 {s2_name}")
                
                with c_txt:
                    text_val = st.text_area(
                        "Text", 
                        value=item.get("text", ""), 
                        key=f"q_txt_{idx}", 
                        height=70, 
                        label_visibility="collapsed",
                        placeholder="Enter dialogue..."
                    )
                
                with c_act:
                    if st.button("❌", key=f"q_del_{idx}"):
                        continue # Skip appending to delete
                
                new_script_items.append({"speaker": spk_sel, "text": text_val})
            
            st.session_state["qwen_script"] = new_script_items
            
            if st.button("⊕ Add Dialog"):
                # Determine next speaker (toggle)
                last_spk = new_script_items[-1]["speaker"] if new_script_items else "Speaker 2"
                next_spk = "Speaker 2" if last_spk == "Speaker 1" else "Speaker 1"
                st.session_state["qwen_script"].append({"speaker": next_spk, "text": ""})
                st.rerun()

            st.divider()
            
            if st.button("Run (Ctrl + Enter)", type="primary"):
                # Generation Logic
                with st.spinner("Generating Speech..."):
                    combined_audio = AudioSegment.empty()
                    
                    for idx, item in enumerate(st.session_state["qwen_script"]):
                        text = item["text"]
                        if not text.strip(): continue
                        
                        spk_role = item["speaker"]
                        # Map role to selected voice
                        target_voice = s1_voice if spk_role == "Speaker 1" else s2_voice
                        
                        audio_result = qwen_logic.generate_voice(text, target_voice)
                        
                        if audio_result:
                            # Convert bytes -> AudioSegment
                            seg = AudioSegment.from_file(io.BytesIO(audio_result), format="mp3")
                            combined_audio += seg
                            # Add small pause
                            combined_audio += AudioSegment.silent(duration=300)
                        else:
                            st.error(f"Failed to generate line {idx+1}")
                    
                    # Export final
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
                        combined_audio.export(f.name, format="mp3")
                        st.session_state["qwen_final_audio"] = f.name
                        st.success("Generation Complete!")
            
            if st.session_state.get("qwen_final_audio"):
                st.audio(st.session_state["qwen_final_audio"], format="audio/mp3")
                with open(st.session_state["qwen_final_audio"], "rb") as f:
                     st.download_button("Download Script Audio", f, file_name="qwen_script_audio.mp3")
