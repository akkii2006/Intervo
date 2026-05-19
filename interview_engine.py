from prompts import system_prompt, evaluation_prompt, LANGUAGE_QUESTION, VIBE_QUESTION
from sarvam_client import chat
import json
import uuid

sessions = {}


def create_session(resume: str, jd: str) -> str:
    session_id = str(uuid.uuid4())
    sessions[session_id] = {
        "resume": resume,
        "jd": jd,
        "language": None,
        "vibe": None,
        "stage": "language",
        "messages": [],
        "transcript": [],
        "done": False,
        "api_key": "",
    }
    return session_id


def get_session(session_id: str) -> dict:
    return sessions.get(session_id)


def set_api_key(session_id: str, api_key: str):
    if session_id in sessions:
        sessions[session_id]["api_key"] = api_key


async def get_opening_question(session_id: str) -> str:
    return LANGUAGE_QUESTION


async def process_turn(session_id: str, user_input: str) -> dict:
    session = sessions[session_id]
    api_key = session.get("api_key", "")

    if not user_input or not user_input.strip():
        return {"text": "Sorry, I didn't catch that. Could you please repeat?", "done": False}

    if session["stage"] == "language":
        session["language"] = user_input.strip()
        session["stage"] = "vibe"
        return {"text": VIBE_QUESTION, "done": False}

    if session["stage"] == "vibe":
        session["vibe"] = user_input.strip()
        session["stage"] = "interview"
        system = system_prompt(
            session["resume"],
            session["jd"],
            session["language"],
            session["vibe"],
        )
        session["system"] = system
        session["messages"] = []
        opening = await chat(
            [{"role": "user", "content": "Please begin the interview."}],
            system=system,
            api_key=api_key,
        )
        if not opening or not opening.strip():
            opening = "Let's begin. Can you start by telling me a little about yourself and your background?"
        session["messages"].append({"role": "user", "content": "Please begin the interview."})
        session["messages"].append({"role": "assistant", "content": opening})
        session["transcript"].append({"role": "interviewer", "content": opening})
        return {"text": opening, "done": False}

    if session["stage"] == "interview":
        session["messages"].append({"role": "user", "content": user_input.strip()})
        session["transcript"].append({"role": "candidate", "content": user_input.strip()})

        response = await chat(session["messages"], system=session["system"], api_key=api_key)

        if not response or not response.strip():
            return {"text": "Sorry, could you repeat that?", "done": False}

        session["messages"].append({"role": "assistant", "content": response})
        session["transcript"].append({"role": "interviewer", "content": response})

        done_signals = [
            "interview is now complete",
            "interview is complete",
            "that concludes",
            "thank you for your time",
            "wish you all the best",
            "good luck",
        ]
        is_done = any(signal in response.lower() for signal in done_signals)

        if is_done:
            session["stage"] = "done"
            session["done"] = True

        return {"text": response, "done": is_done}

    return {"text": "Thank you for the interview. Please wait for your feedback.", "done": True}


async def evaluate(session_id: str) -> dict:
    session = sessions[session_id]
    api_key = session.get("api_key", "")
    prompt = evaluation_prompt(session["resume"], session["jd"], session["transcript"])
    result = await chat([{"role": "user", "content": prompt}], api_key=api_key, evaluate=True)

    if not result or not result.strip():
        return {
            "hire_likelihood": 50,
            "verdict": "Insufficient Data",
            "summary": "The interview was too short to generate a full evaluation.",
            "strengths": ["Unable to evaluate"],
            "weaknesses": ["Unable to evaluate"],
            "improvements": ["Complete a full interview for accurate feedback"],
            "technical_score": 50,
            "communication_score": 50,
            "confidence_score": 50,
        }

    try:
        return json.loads(result)
    except Exception:
        try:
            start = result.find("{")
            end = result.rfind("}") + 1
            if start != -1 and end > start:
                return json.loads(result[start:end])
        except Exception:
            pass

    return {
        "hire_likelihood": 50,
        "verdict": "Evaluation Error",
        "summary": "Could not parse the evaluation. Please try again with a complete interview.",
        "strengths": ["Unable to evaluate"],
        "weaknesses": ["Unable to evaluate"],
        "improvements": ["Complete a full interview for accurate feedback"],
        "technical_score": 50,
        "communication_score": 50,
        "confidence_score": 50,
    }
