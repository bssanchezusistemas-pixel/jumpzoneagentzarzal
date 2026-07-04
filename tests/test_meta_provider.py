"""Tests mínimos del proveedor Meta (sin llamadas a Graph API)."""

import asyncio
import hashlib
import hmac
import json
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from agent.providers.meta import ProveedorMeta


def _request(method: str, path: str, headers: dict | None = None, body: bytes = b"") -> Request:
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "query_string": b"",
    }

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(scope, receive)


@pytest.mark.asyncio
async def test_validar_webhook_challenge():
    p = ProveedorMeta()
    p.verify_token = "test-token"
    req = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/webhook",
            "headers": [],
            "query_string": b"hub.mode=subscribe&hub.verify_token=test-token&hub.challenge=12345",
        },
        lambda: asyncio.sleep(0),
    )
    result = await p.validar_webhook(req)
    assert result == 12345


@pytest.mark.asyncio
async def test_parsear_mensaje_texto():
    p = ProveedorMeta()
    payload = {
        "entry": [{
            "changes": [{
                "field": "messages",
                "value": {
                    "messages": [{
                        "from": "573001234567",
                        "id": "wamid.abc",
                        "type": "text",
                        "text": {"body": "Hola"},
                    }],
                },
            }],
        }],
    }
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    req = _request("POST", "/webhook", {"X-Hub-Signature-256": sig}, body)

    with patch.dict("os.environ", {"META_APP_SECRET": "secret", "ENVIRONMENT": "production"}):
        p = ProveedorMeta()
        msgs = await p.parsear_webhook(req)

    assert len(msgs) == 1
    assert msgs[0].telefono == "573001234567"
    assert msgs[0].texto == "Hola"
    assert not msgs[0].es_propio


@pytest.mark.asyncio
async def test_ignora_smb_message_echoes_como_propio():
    p = ProveedorMeta()
    payload = {
        "entry": [{
            "changes": [{
                "field": "smb_message_echoes",
                "value": {
                    "smb_message_echoes": [{
                        "from": "573001234567",
                        "id": "wamid.echo",
                        "type": "text",
                        "text": {"body": "Respuesta dueña"},
                    }],
                },
            }],
        }],
    }
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    req = _request("POST", "/webhook", {"X-Hub-Signature-256": sig}, body)

    with patch.dict("os.environ", {"META_APP_SECRET": "secret", "ENVIRONMENT": "production"}):
        p = ProveedorMeta()
        msgs = await p.parsear_webhook(req)

    assert len(msgs) == 1
    assert msgs[0].es_propio is True


@pytest.mark.asyncio
async def test_firma_invalida_403():
    body = b'{"entry":[]}'
    req = _request("POST", "/webhook", {"X-Hub-Signature-256": "sha256=bad"}, body)

    with patch.dict("os.environ", {"META_APP_SECRET": "secret", "ENVIRONMENT": "production"}):
        p = ProveedorMeta()
        with pytest.raises(HTTPException) as exc:
            await p.parsear_webhook(req)
        assert exc.value.status_code == 403
