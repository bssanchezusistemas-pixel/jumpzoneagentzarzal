# agent/audio.py — Transcripción de notas de voz
# Generado por AgentKit

import os
import base64
import logging
import tempfile
import asyncio
import httpx
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("agentkit")

# Asegurar ffmpeg en PATH (winget lo instala pero el servidor puede no verlo)
_FFMPEG_BIN = os.path.join(
    os.environ.get("LOCALAPPDATA", ""),
    "Microsoft", "WinGet", "Packages",
    "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe",
    "ffmpeg-8.1.1-full_build", "bin",
)
if os.path.isdir(_FFMPEG_BIN) and _FFMPEG_BIN not in os.environ.get("PATH", ""):
    os.environ["PATH"] = _FFMPEG_BIN + os.pathsep + os.environ.get("PATH", "")

TRANSCRIPTION_MODEL = os.getenv("TRANSCRIPTION_MODEL", "openai/whisper-large-v3")
_whisper_model = None


def _api_key_openrouter() -> str | None:
    return os.getenv("OPENROUTER_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")


async def descargar_audio_twilio(media_url: str, account_sid: str, auth_token: str) -> tuple[bytes, str]:
    """Descarga el archivo de audio desde Twilio (sigue redirect a CDN)."""
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        response = await client.get(media_url, auth=(account_sid, auth_token))
        response.raise_for_status()
        content_type = response.headers.get("content-type", "audio/ogg")
        return response.content, content_type


def _formato_audio(content_type: str) -> str:
    mime = content_type.split(";")[0].strip().lower()
    if "ogg" in mime:
        return "ogg"
    if "mpeg" in mime or "mp3" in mime:
        return "mp3"
    if "mp4" in mime or "m4a" in mime:
        return "m4a"
    if "webm" in mime:
        return "webm"
    if "wav" in mime:
        return "wav"
    return "ogg"


async def _transcribir_groq(audio_bytes: bytes, content_type: str) -> str:
    """Transcribe con Groq Whisper (gratis con GROQ_API_KEY)."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY no configurada")

    ext = _formato_audio(content_type)
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (f"audio.{ext}", audio_bytes, content_type)},
            data={"model": "whisper-large-v3", "language": "es"},
        )
        response.raise_for_status()
        texto = response.json().get("text", "").strip()
        if not texto:
            raise ValueError("Transcripción vacía")
        return texto


async def _transcribir_openrouter_stt(audio_bytes: bytes, content_type: str) -> str:
    """Transcribe con endpoint STT de OpenRouter (requiere saldo >= $0.50)."""
    api_key = _api_key_openrouter()
    if not api_key:
        raise ValueError("Sin API key de OpenRouter")

    fmt = _formato_audio(content_type)
    b64 = base64.b64encode(audio_bytes).decode()

    async with httpx.AsyncClient(timeout=90.0) as client:
        response = await client.post(
            "https://openrouter.ai/api/v1/audio/transcriptions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://agentkit.local",
            },
            json={
                "model": TRANSCRIPTION_MODEL,
                "input_audio": {"data": b64, "format": fmt},
                "language": "es",
            },
        )
        response.raise_for_status()
        data = response.json()
        texto = (data.get("text") or data.get("transcription") or "").strip()
        if not texto and isinstance(data.get("choices"), list) and data["choices"]:
            texto = data["choices"][0].get("message", {}).get("content", "").strip()
        if not texto:
            raise ValueError("Transcripción vacía")
        return texto


def precargar_modelo_whisper():
    """Carga Whisper local en segundo plano al arrancar (evita espera en primer audio)."""
    import threading

    def _cargar():
        try:
            _get_whisper_model()
            logger.info("Modelo Whisper local listo")
        except Exception as e:
            logger.warning(f"Whisper local no disponible: {e}")

    threading.Thread(target=_cargar, daemon=True).start()


def _get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        logger.info("Cargando modelo Whisper local (tiny)...")
        _whisper_model = WhisperModel("tiny", device="cpu", compute_type="int8")
    return _whisper_model


def _transcribir_local(audio_bytes: bytes, content_type: str) -> str:
    """Transcribe en local con faster-whisper (sin API, requiere ffmpeg)."""
    model = _get_whisper_model()

    ext = _formato_audio(content_type)
    with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        segments, _ = model.transcribe(tmp_path, language="es", beam_size=1)
        texto = " ".join(seg.text.strip() for seg in segments).strip()
        if not texto:
            raise ValueError("Transcripción vacía")
        return texto
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


async def transcribir_audio(audio_bytes: bytes, content_type: str) -> str:
    """Transcribe audio: Groq → OpenRouter STT → Whisper local."""
    errores = []

    for nombre, fn in [
        ("Groq", _transcribir_groq),
        ("OpenRouter STT", _transcribir_openrouter_stt),
    ]:
        try:
            texto = await fn(audio_bytes, content_type)
            logger.info(f"Audio transcrito ({nombre}): {texto[:80]}...")
            return texto
        except Exception as e:
            errores.append(f"{nombre}: {e}")
            logger.warning(f"Transcripción {nombre} falló: {e}")

    try:
        texto = await asyncio.to_thread(_transcribir_local, audio_bytes, content_type)
        logger.info(f"Audio transcrito (local): {texto[:80]}...")
        return texto
    except Exception as e:
        errores.append(f"Local: {e}")
        logger.error(f"No se pudo transcribir audio: {'; '.join(errores)}")

    return ""
