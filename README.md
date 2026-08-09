# melodi.ai — frontend

A single self-contained `index.html` (fonts + both backdrop tracks are embedded — no build step, no dependencies). This is **frontend only**, wired to call a backend you already have — nothing here runs a server.

## Running it
Just open `index.html` in a browser, or serve it statically. Click the gear icon top-right to point it at your backend (defaults to `http://localhost:8000`).

## What the frontend expects from your backend
Your existing `main.py` logic (Groq lyrics → Rime TTS → pydub mix) needs to sit behind three HTTP routes. CORS must be enabled for whatever origin serves the frontend.

### `GET /health`
Any `200` response. Only used to drive the "backend connected" indicator — the app still lets you try to generate even if this fails or is missing.

### `POST /api/generate`
Request is `multipart/form-data`:
| field | value |
|---|---|
| `mood` | string |
| `genre` | string |
| `topic` | string |
| `voice` | one of `cove`, `astra`, `luna`, `spore` |
| `backgroundMusicId` | `low-tide` \| `night-drive` \| `none` \| `custom` |
| `backgroundMusicFile` | audio file, only present when `backgroundMusicId` is `custom` |

Respond with `Content-Type: application/json`:
```json
{ "lyrics": "generated lyrics text", "audio": "<base64 mp3 bytes>", "mimeType": "audio/mpeg" }
```
This is what `generate_lyrics()` + `clean_lyrics_for_speech()` + `text_to_speech()` in `main.py` already produce — just base64-encode `final_song.mp3` and return both pieces together instead of writing to disk. (A raw audio response also works as a fallback, but you lose the lyrics — the JSON shape above is what the UI is built for.)

### `POST /api/preview-voice`
JSON body `{ "voice": "cove" }` → raw audio bytes (any audio `Content-Type`) of a short line spoken in that voice. Used by the ▶ button on each voice card. If you don't implement this, the button shows a "connect a backend to preview voices" hint instead of failing silently.

## Notes
- `Low Tide` and `Night Drive` in the backdrop picker are your two bundled tracks (`BGM2.mp3` and `BGM.mpeg`) — already embedded and playable client-side with no backend needed. Your `/api/generate` handler should mix in the matching file server-side based on `backgroundMusicId`.
- "Your own beat" lets a user upload a track; it's sent as `backgroundMusicFile` — mix that in instead when `backgroundMusicId === "custom"`.
- `main.py` currently hardcodes the speaker to `"cove"` — swap that for the `voice` field coming from the form.
