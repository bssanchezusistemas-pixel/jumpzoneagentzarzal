# agent/auth.py — Autenticación simple para panel admin

import os
import hmac
import hashlib
import base64
import json
import time
from fastapi import Request, HTTPException

TOKEN_TTL_SEC = 7 * 24 * 3600  # 7 días


def _secret() -> bytes:
    key = os.getenv("SECRET_KEY", "").strip()
    if not key:
        key = os.getenv("TWILIO_AUTH_TOKEN", "dev-insecure-change-me")
    return key.encode("utf-8")


def _admin_user() -> str:
    return os.getenv("ADMIN_USER", "admin").strip()


def _admin_password() -> str:
    return os.getenv("ADMIN_PASSWORD", "").strip()


def verificar_credenciales(usuario: str, password: str) -> bool:
    expected_user = _admin_user()
    expected_pass = _admin_password()
    if not expected_pass:
        return False
    return (
        hmac.compare_digest(usuario.strip(), expected_user)
        and hmac.compare_digest(password, expected_pass)
    )


def crear_token(usuario: str) -> str:
    payload = {
        "sub": usuario,
        "exp": int(time.time()) + TOKEN_TTL_SEC,
    }
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    sig = hmac.new(_secret(), body.encode(), hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).decode().rstrip("=")
    return f"{body}.{sig_b64}"


def validar_token(token: str) -> dict | None:
    if not token or "." not in token:
        return None
    body, sig_b64 = token.split(".", 1)
    pad = "=" * (-len(sig_b64) % 4)
    try:
        expected_sig = hmac.new(_secret(), body.encode(), hashlib.sha256).digest()
        got_sig = base64.urlsafe_b64decode(sig_b64 + pad)
        if not hmac.compare_digest(expected_sig, got_sig):
            return None
        pad_body = "=" * (-len(body) % 4)
        payload = json.loads(base64.urlsafe_b64decode(body + pad_body))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except (ValueError, json.JSONDecodeError):
        return None


def extraer_bearer(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


async def requiere_admin(request: Request) -> dict:
    token = extraer_bearer(request)
    if not token:
        raise HTTPException(status_code=401, detail="No autorizado")
    payload = validar_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Sesión expirada o inválida")
    return payload
