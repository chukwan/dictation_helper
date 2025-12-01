# Dictation Buddy 🎧

Dictation Buddy is a Streamlit-based application designed to help students practice dictation. It converts photos of dictation sheets (vocabulary and passages) into practice audio files using Google Gemini for text extraction and Edge TTS for high-quality speech generation.

## Features

-   **Image-to-Text**: Upload a photo of your dictation sheet, and the app automatically extracts vocabulary and passage text using Google Gemini 2.0 Flash.
-   **Multi-language Support**: Automatically detects English and Traditional Chinese.
    -   **Voice Selection**: Choose from multiple high-quality neural voices (e.g., HsiaoChen, HsiaoYu for Mandarin; Aria, Guy for English).
    -   **Punctuation Reading**: Reads punctuation out loud (e.g., "comma", "period", "逗號", "句號") for effective dictation practice.
-   **Customizable Audio Generation**:
    -   **Vocabulary**: Configurable repeats and silence duration between words. Option to shuffle word order.
    -   **Passage**: Configurable sentence repeats and independent reading speed control.
-   **Instant Previews**: Listen to individual words or sentences immediately after upload.
-   **Recordings Library**: Save your generated practice sessions to a local library for later use.
-   **Downloadable Audio**: Download generated MP3 files for offline practice.

## Prerequisites

-   Python 3.10+
-   A Google Cloud API Key with access to Gemini models.

## Installation

1.  **Clone the repository** (if applicable) or download the source code.
2.  **Create a `.env` file**:
    -   Copy `.env.example` to `.env`.
    -   Add your Google API Key: `GOOGLE_API_KEY=your_api_key_here`.
    -   Alternatively, you can enter the key in the app's sidebar.

## Usage

### Quick Start (Windows)

Run the provided PowerShell script to automatically set up the virtual environment, install dependencies, and launch the app:

```powershell
.\run_app.ps1
```

To force a rebuild of the environment (e.g., after requirement changes):

```powershell
.\run_app.ps1 -Rebuild
```

### Manual Run

1.  Create and activate a virtual environment:
    ```bash
    python -m venv venv
    .\venv\Scripts\activate
    ```
2.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
3.  Run the application:
    ```bash
    streamlit run app.py
    ```

## Project Structure

-   `app.py`: Main Streamlit application and UI logic.
-   `logic.py`: Core logic for text processing, audio generation, and file management.
-   `run_app.ps1`: Helper script for easy setup and execution.
-   `requirements.txt`: Python dependencies.
-   `tests/`: Unit tests for the application logic.
-   `recordings/`: Directory where saved audio files are stored.

## Technologies Used

-   **Streamlit**: Web interface.
-   **Google Gemini API**: OCR and text extraction.
-   **edge-tts**: Text-to-Speech generation.
-   **Pydub**: Audio manipulation (stitching, silence).
-   **Pytest**: Testing framework.
