import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GOOGLE_API_KEY")

if not api_key:
    print("Error: GOOGLE_API_KEY not found in .env")
    exit(1)

url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={api_key}"

data = {
    "input": {"text": "你好，这是一个测试。"},
    "voice": {"languageCode": "cmn-CN", "name": "cmn-CN-Standard-A"},
    "audioConfig": {"audioEncoding": "MP3"}
}

response = requests.post(url, headers={"Content-Type": "application/json"}, data=json.dumps(data))

if response.status_code == 200:
    print("Success! Google Cloud TTS API is accessible.")
    with open("test_google_tts.mp3", "wb") as f:
        f.write(response.content) # Note: Response content is JSON with base64 audio
    # Actually need to decode base64
    import base64
    json_response = response.json()
    audio_content = base64.b64decode(json_response["audioContent"])
    with open("test_google_tts.mp3", "wb") as f:
        f.write(audio_content)
    print("Saved test_google_tts.mp3")
else:
    print(f"Failed. Status Code: {response.status_code}")
    print(f"Response: {response.text}")
