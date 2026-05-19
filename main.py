from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from resume_parser import extract_text
from interview_engine import create_session, get_session, get_opening_question, process_turn, evaluate, set_api_key
from sarvam_client import speech_to_text, text_to_speech
import json

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

LANGUAGE_MAP = {
    "english": "en-IN", "hindi": "hi-IN", "tamil": "ta-IN", "telugu": "te-IN",
    "kannada": "kn-IN", "malayalam": "ml-IN", "bengali": "bn-IN", "marathi": "mr-IN",
    "gujarati": "gu-IN", "punjabi": "pa-IN", "odia": "od-IN", "urdu": "ur-IN",
    "en": "en-IN", "hi": "hi-IN", "ta": "ta-IN", "te": "te-IN",
}

def resolve_language(raw: str) -> str:
    clean = raw.lower().strip().rstrip(".").split()[0]
    return LANGUAGE_MAP.get(clean, "en-IN")

def get_api_key(request: Request) -> str:
    return request.headers.get("X-Sarvam-Key", "")


@app.get("/")
async def root():
    return FileResponse("static/index.html")


@app.get("/interview")
async def interview_page():
    return FileResponse("static/interview.html")


@app.get("/feedback")
async def feedback_page():
    return FileResponse("static/feedback.html")


@app.post("/api/start")
async def start(
    request: Request,
    resume: UploadFile = File(...),
    jd: UploadFile = File(...),
):
    api_key = get_api_key(request)
    if not api_key:
        raise HTTPException(status_code=401, detail="API key required")

    resume_bytes = await resume.read()
    jd_bytes = await jd.read()

    resume_text = extract_text(resume_bytes)
    jd_text = extract_text(jd_bytes)

    session_id = create_session(resume_text, jd_text)
    set_api_key(session_id, api_key)
    opening_text = await get_opening_question(session_id)

    return Response(
        content=json.dumps({"session_id": session_id, "text": opening_text}),
        media_type="application/json",
    )


@app.get("/api/opening-audio/{session_id}")
async def opening_audio(request: Request, session_id: str):
    api_key = get_api_key(request)
    from prompts import LANGUAGE_QUESTION
    audio = await text_to_speech(LANGUAGE_QUESTION, "en-IN", api_key)
    return Response(content=audio, media_type="audio/mpeg")


@app.post("/api/turn")
async def turn(
    request: Request,
    session_id: str = Form(...),
    audio: UploadFile = File(...),
):
    api_key = get_api_key(request)
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    audio_bytes = await audio.read()

    raw_language = session.get("language")
    stt_language = resolve_language(raw_language) if raw_language else "unknown"

    user_text = await speech_to_text(audio_bytes, stt_language, api_key)
    result = await process_turn(session_id, user_text)

    if session.get("language") and not session.get("language_code"):
        session["language_code"] = resolve_language(session["language"])

    return Response(
        content=json.dumps({
            "user_text": user_text,
            "ai_text": result["text"],
            "done": result["done"],
        }),
        media_type="application/json",
    )


@app.get("/api/turn-audio/{session_id}")
async def turn_audio(request: Request, session_id: str, text: str):
    api_key = get_api_key(request)
    session = get_session(session_id)
    lang_code = "en-IN"
    if session and session.get("language"):
        lang_code = resolve_language(session["language"])
    audio = await text_to_speech(text, lang_code, api_key)
    return Response(content=audio, media_type="audio/mpeg")


@app.post("/api/evaluate")
async def evaluate_session(request: Request, session_id: str = Form(...)):
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    result = await evaluate(session_id)
    return result
