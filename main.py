import os
import io
import base64
from pathlib import Path

import requests
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, FileResponse
from groq import Groq
from pydub import AudioSegment
from dotenv import load_dotenv


load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
RIME_API_KEY = os.getenv("RIME_API_KEY")

if not GROQ_API_KEY or not RIME_API_KEY:
    raise RuntimeError("Missing API keys! Make sure you created a .env file.")

client = Groq(api_key=GROQ_API_KEY)

BASE_DIR = Path(__file__).parent


BGM_TRACKS = {
    "low-tide": BASE_DIR / "BGM2.mp3",
    "night-drive": BASE_DIR / "BGM.mpeg",
}


VOICE_MAP = {
    "cove": "cove",
    "astra": "astra",
    "luna": "luna",
    "spore": "spore",
}

PREVIEW_TEXT = "Hey — this is what I sound like. Let's make something together."

app = FastAPI(title="melodi.ai backend")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)



def generate_lyrics(mood: str, genre: str, topic: str) -> str:
    prompt = f"""Write a rhythmic, emotional spoken-word poem with these details:
Mood: {mood}
Genre/Vibe: {genre}
Topic: {topic}

Keep the lines short and punchy so they have a natural rhythm when spoken over a beat. Do not write a traditional song with verses or choruses.
IMPORTANT: Reply ONLY with the spoken-word lyrics. Do not include any introductory filler, conversational text, explanations, or titles."""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content


def clean_lyrics_for_speech(lyrics: str) -> str:
    cleaned_lines = []
    for line in lyrics.splitlines():
        stripped = line.replace("*", "").replace("#", "").strip()
        if not stripped or len(stripped) <= 2:
            continue
        stripped = (
            stripped.replace("-", "")
            .replace("\u2022", "")
            .replace("[", "")
            .replace("]", "")
            .replace("(", "")
            .replace(")", "")
            .strip()
        )
        cleaned_lines.append(stripped)

    speech_text = "\n".join(cleaned_lines).strip()
    if len(speech_text) > 800:
        speech_text = speech_text[:800].rsplit("\n", 1)[0]
    return speech_text.replace("\n", " ... \n").strip()


def rime_tts(text: str, speaker: str) -> bytes:
    """Call Rime TTS and return raw audio bytes (mp3)."""
    url = "https://users.rime.ai/v1/rime-tts"
    headers = {"Authorization": f"Bearer {RIME_API_KEY}", "Content-Type": "application/json"}
    payload = {"speaker": speaker, "text": text, "modelId": "mist"}

    response = requests.post(url, json=payload, headers=headers, timeout=60)
    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Rime TTS error ({response.status_code}): {response.text}",
        )

    if "application/json" in response.headers.get("Content-Type", ""):
        return base64.b64decode(response.json()["audioContent"])
    return response.content


def mix_with_backdrop(voice_bytes: bytes, backdrop_id: str, custom_file_bytes):
    """Mix the spoken voice track over the chosen backdrop and return mp3 bytes.
    If backdrop_id is 'none' (or unrecognized with no custom file), the voice
    track is returned as-is."""
    voice = AudioSegment.from_file(io.BytesIO(voice_bytes))

    music = None
    if backdrop_id == "custom" and custom_file_bytes:
        music = AudioSegment.from_file(io.BytesIO(custom_file_bytes))
    elif backdrop_id in BGM_TRACKS:
        track_path = BGM_TRACKS[backdrop_id]
        if track_path.exists():
            music = AudioSegment.from_file(track_path)

    if music is None:
        out = io.BytesIO()
        voice.export(out, format="mp3")
        return out.getvalue()

    delay = AudioSegment.silent(duration=5000)
    voice_with_delay_and_tail = delay + voice + AudioSegment.silent(duration=3000)

    target_length = len(voice_with_delay_and_tail)
    if len(music) < target_length:
        music = music * (target_length // len(music) + 1)
    music = music[:target_length].fade_out(3000)

    mixed = music.apply_gain(-8).overlay(voice_with_delay_and_tail)
    out = io.BytesIO()
    mixed.export(out, format="mp3")
    return out.getvalue()


@app.get("/")
async def serve_frontend():
    return FileResponse(BASE_DIR / "index.html")
@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/preview-voice")
async def preview_voice(payload: dict):
    voice_id = payload.get("voice")
    speaker = VOICE_MAP.get(voice_id, voice_id)
    if not speaker:
        raise HTTPException(status_code=400, detail="Missing 'voice' field")

    audio_bytes = rime_tts(PREVIEW_TEXT, speaker)
    return Response(content=audio_bytes, media_type="audio/mpeg")


@app.post("/api/generate")
async def generate(
    mood: str = Form(...),
    genre: str = Form(...),
    topic: str = Form(...),
    voice: str = Form(...),
    backgroundMusicId: str = Form(...),
    backgroundMusicFile: UploadFile = File(None),
):
    speaker = VOICE_MAP.get(voice, voice)

    raw_lyrics = generate_lyrics(mood, genre, topic)
    speech_text = clean_lyrics_for_speech(raw_lyrics) or raw_lyrics

    voice_bytes = rime_tts(speech_text, speaker)

    custom_bytes = None
    if backgroundMusicId == "custom" and backgroundMusicFile is not None:
        custom_bytes = await backgroundMusicFile.read()

    final_audio = mix_with_backdrop(voice_bytes, backgroundMusicId, custom_bytes)

    return JSONResponse(
        {
            "lyrics": raw_lyrics,
            "audio": base64.b64encode(final_audio).decode("ascii"),
            "mimeType": "audio/mpeg",
        }
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
