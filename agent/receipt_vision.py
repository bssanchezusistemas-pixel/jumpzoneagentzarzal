# agent/receipt_vision.py — Lectura de comprobantes (sugerencia para dueña)

import os
import base64
import logging
import httpx
from anthropic import AsyncAnthropic
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("agentkit")


def _cliente():
    key = os.getenv("OPENROUTER_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN") or os.getenv("ANTHROPIC_API_KEY")
    base = "https://openrouter.ai/api" if os.getenv("OPENROUTER_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN") else "https://api.anthropic.com"
    model = os.getenv("OPENROUTER_MODEL", "anthropic/claude-sonnet-4")
    return AsyncAnthropic(api_key=key, base_url=base), model


async def descargar_imagen(url: str, auth: tuple[str, str] | None = None) -> tuple[bytes, str]:
    headers = {}
    if auth:
        import base64 as b64
        token = b64.b64encode(f"{auth[0]}:{auth[1]}".encode()).decode()
        headers["Authorization"] = f"Basic {token}"
    async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
        r = await client.get(url, headers=headers)
        r.raise_for_status()
        ct = r.headers.get("content-type", "image/jpeg")
        return r.content, ct


async def analizar_comprobante(imagen_bytes: bytes, media_type: str, monto_esperado: float | None = None) -> dict:
    """Extrae monto del comprobante. Retorna sugerencia, no confirma pago."""
    try:
        cli, model = _cliente()
        b64 = base64.standard_b64encode(imagen_bytes).decode()
        if "png" in media_type:
            mt = "image/png"
        elif "webp" in media_type:
            mt = "image/webp"
        else:
            mt = "image/jpeg"

        prompt = (
            "Analiza este comprobante de pago colombiano (Nequi, Bancolombia, etc.). "
            "Responde SOLO en JSON: {\"monto\": numero o null, \"confianza\": 0-1, \"notas\": \"breve\"}. "
            "Si no ves monto claro, monto=null."
        )
        if monto_esperado:
            prompt += f" Monto esperado aprox: {monto_esperado} COP."

        r = await cli.messages.create(
            model=model,
            max_tokens=200,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": mt, "data": b64}},
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        texto = ""
        for block in r.content:
            if hasattr(block, "text"):
                texto = block.text
                break

        import json
        texto = texto.strip().replace("```json", "").replace("```", "")
        data = json.loads(texto)
        return {
            "monto_detectado": data.get("monto"),
            "confianza": data.get("confianza", 0.5),
            "notas": data.get("notas", ""),
        }
    except Exception as e:
        logger.error("Error visión comprobante: %s", e)
        return {"monto_detectado": None, "confianza": 0, "notas": "No se pudo leer automáticamente"}
