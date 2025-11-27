import sys
import os
import importlib.util

def check_import(module_name):
    if importlib.util.find_spec(module_name) is None:
        print(f"❌ {module_name} not found")
    else:
        print(f"✅ {module_name} found")

print("--- Environment Check ---")
print(f"Python: {sys.version}")

modules = ["streamlit", "google.generativeai", "edge_tts", "pydub", "dotenv", "PIL"]
for m in modules:
    check_import(m)

print("\n--- FFmpeg Check ---")
from pydub import AudioSegment
try:
    # Try to create a silent segment, which doesn't strictly need ffmpeg, 
    # but exporting it or other ops might.
    # To check ffmpeg, pydub usually looks in PATH.
    from pydub.utils import which
    ffmpeg_path = which("ffmpeg")
    if ffmpeg_path:
        print(f"✅ FFmpeg found at: {ffmpeg_path}")
    else:
        print("❌ FFmpeg NOT found in PATH")
except Exception as e:
    print(f"❌ Error checking FFmpeg: {e}")

print("\n--- Done ---")
