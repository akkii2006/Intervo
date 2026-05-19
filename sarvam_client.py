import httpx
import base64
import re

BASE_URL = "https://api.sarvam.ai"


def get_headers(api_key: str) -> dict:
    return {"api-subscription-key": api_key}


def get_chat_headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def clean_response(text: str) -> str:
    if not text:
        return ""
    if "</think>" in text:
        text = text.split("</think>")[-1].strip()
    lines = text.strip().splitlines()
    clean = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if re.match(r"^\d+\.\s+\*\*", line):
            continue
        if re.match(r"^\*+\s+\*\*", line):
            continue
        if re.match(r"^\*\*.*\*\*$", line):
            continue
        if line.startswith("*") or line.startswith("#"):
            continue
        clean.append(line)
    return " ".join(clean).strip()


def extract_question(text: str) -> str:
    if not text:
        return ""
    if "</think>" in text:
        text = text.split("</think>")[-1].strip()

    text = clean_response(text)
    if not text:
        return ""

    if "?" in text:
        last_q = text.rfind("?")
        chunk = text[:last_q+1]
        sentences = re.split(r'(?<=[.!?])\s+', chunk)
        for sentence in reversed(sentences):
            sentence = sentence.strip()
            if "?" in sentence and len(sentence) > 10:
                return sentence

    words = text.split()
    if len(words) > 60:
        text = " ".join(words[-60:])

    return text


async def speech_to_text(audio_bytes: bytes, language: str = "en-IN", api_key: str = "") -> str:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/speech-to-text",
            headers=get_headers(api_key),
            files={"file": ("audio.mp4", audio_bytes, "audio/mp4")},
            data={
                "model": "saaras:v3",
                "language_code": language,
                "mode": "transcribe",
            },
            timeout=30,
        )
        if response.status_code != 200:
            print("STT ERROR:", response.text)
            return ""
        return response.json().get("transcript", "")


async def text_to_speech(text: str, language: str = "en-IN", api_key: str = "") -> bytes:
    text = text[:2500]
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/text-to-speech",
            headers={**get_headers(api_key), "Content-Type": "application/json"},
            json={
                "text": text,
                "target_language_code": language,
                "speaker": "shubh",
                "model": "bulbul:v3",
                "output_audio_codec": "mp3",
            },
            timeout=30,
        )
        if response.status_code != 200:
            print("TTS ERROR:", response.text)
            response.raise_for_status()
        data = response.json()
        audio_b64 = data["audios"][0]
        return base64.b64decode(audio_b64)


async def chat(messages: list, system: str = "", api_key: str = "", evaluate: bool = False) -> str:
    all_messages = []
    if system:
        all_messages.append({"role": "system", "content": system[:4000]})
    all_messages.extend(messages)

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/v1/chat/completions",
            headers=get_chat_headers(api_key),
            json={
                "model": "sarvam-30b",
                "messages": all_messages,
                "max_tokens": 4096,
            },
            timeout=90,
        )
        if response.status_code != 200:
            print("CHAT ERROR:", response.text)
            return ""

        data = response.json()
        message = data["choices"][0]["message"]

        content = message.get("content") or ""
        reasoning = message.get("reasoning_content") or ""

        if evaluate:
            if content.strip():
                return content.strip()
            if reasoning.strip():
                if "</think>" in reasoning:
                    after = reasoning.split("</think>")[-1].strip()
                    if after:
                        return after
            return ""

        if content.strip():
            result = extract_question(content)
            if result:
                return result

        if reasoning.strip():
            result = extract_question(reasoning)
            if result:
                return result

        return ""