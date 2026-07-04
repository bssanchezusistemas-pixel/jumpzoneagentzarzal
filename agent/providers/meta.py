# agent/providers/meta.py — Adaptador Meta WhatsApp Cloud API (coexistence)

import hashlib
import hmac
import json
import logging
import os

import httpx
from fastapi import HTTPException, Request

from agent.audio import transcribir_audio
from agent.providers.base import MensajeEntrante, ProveedorWhatsApp

logger = logging.getLogger("agentkit")


class ProveedorMeta(ProveedorWhatsApp):
    """Proveedor WhatsApp vía Meta Cloud API con soporte coexistence."""

    def __init__(self):
        self.access_token = os.getenv("META_ACCESS_TOKEN", "")
        self.phone_number_id = os.getenv("META_PHONE_NUMBER_ID", "")
        self.verify_token = os.getenv("META_VERIFY_TOKEN", "agentkit-verify")
        self.app_secret = os.getenv("META_APP_SECRET", "")
        self.api_version = os.getenv("META_API_VERSION", "v21.0")
        self.require_signature = os.getenv("ENVIRONMENT", "development") == "production"

    async def validar_webhook(self, request: Request) -> dict | int | None:
        params = request.query_params
        mode = params.get("hub.mode")
        token = params.get("hub.verify_token")
        challenge = params.get("hub.challenge")
        if mode == "subscribe" and token == self.verify_token:
            return int(challenge)
        return None

    def _validar_firma(self, signature: str | None, body: bytes) -> bool:
        if not self.app_secret:
            if self.require_signature:
                logger.error("META_APP_SECRET requerido en producción")
                return False
            logger.warning("META_APP_SECRET no configurado — firma omitida (dev)")
            return True
        if not signature or not signature.startswith("sha256="):
            return False
        expected = hmac.new(
            self.app_secret.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(signature[7:], expected)

    async def _leer_body(self, request: Request) -> bytes:
        body = await request.body()
        signature = request.headers.get("X-Hub-Signature-256")
        if not self._validar_firma(signature, body):
            raise HTTPException(status_code=403, detail="Firma webhook inválida")
        return body

    async def _descargar_media(self, media_id: str) -> tuple[bytes, str]:
        if not self.access_token:
            raise ValueError("META_ACCESS_TOKEN no configurado")
        meta_url = f"https://graph.facebook.com/{self.api_version}/{media_id}"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        async with httpx.AsyncClient(timeout=60.0) as client:
            meta_resp = await client.get(meta_url, headers=headers)
            meta_resp.raise_for_status()
            download_url = meta_resp.json().get("url")
            if not download_url:
                raise ValueError("Meta no devolvió URL de media")
            media_resp = await client.get(download_url, headers=headers)
            media_resp.raise_for_status()
            content_type = media_resp.headers.get("content-type", "application/octet-stream")
            return media_resp.content, content_type

    async def descargar_media(self, msg: MensajeEntrante) -> tuple[bytes, str]:
        if msg.media_id:
            return await self._descargar_media(msg.media_id)
        if msg.media_url:
            headers = {"Authorization": f"Bearer {self.access_token}"}
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                resp = await client.get(msg.media_url, headers=headers)
                resp.raise_for_status()
                ct = resp.headers.get("content-type", "application/octet-stream")
                return resp.content, ct
        raise ValueError("Mensaje sin media_id ni media_url")

    def _parsear_mensaje(self, msg: dict, es_propio: bool) -> MensajeEntrante | None:
        telefono = msg.get("from", "")
        mensaje_id = msg.get("id", "")
        msg_type = msg.get("type", "")

        if msg_type == "text":
            texto = (msg.get("text") or {}).get("body", "").strip()
            if not texto:
                return None
            return MensajeEntrante(
                telefono=telefono,
                texto=texto,
                mensaje_id=mensaje_id,
                es_propio=es_propio,
            )

        if msg_type == "image":
            image = msg.get("image") or {}
            caption = (image.get("caption") or "").strip()
            return MensajeEntrante(
                telefono=telefono,
                texto=caption or "[COMPROBANTE]",
                mensaje_id=mensaje_id,
                es_propio=es_propio,
                es_imagen=True,
                media_id=image.get("id"),
            )

        if msg_type == "audio":
            audio = msg.get("audio") or {}
            return MensajeEntrante(
                telefono=telefono,
                texto="",
                mensaje_id=mensaje_id,
                es_propio=es_propio,
                es_audio=True,
                media_id=audio.get("id"),
            )

        if msg_type in ("video", "document", "sticker", "location", "contacts"):
            logger.debug("Tipo Meta ignorado: %s de %s", msg_type, telefono)
            return None

        logger.debug("Tipo Meta no soportado: %s", msg_type)
        return None

    async def _procesar_audio(self, base: MensajeEntrante) -> MensajeEntrante:
        try:
            audio_bytes, content_type = await self.descargar_media(base)
            transcrito = await transcribir_audio(audio_bytes, content_type)
            if transcrito:
                base.texto = transcrito
                logger.info("Nota de voz Meta transcrita de %s", base.telefono)
                return base
            base.respuesta_directa = (
                "Recibí tu audio pero no pude transcribirlo. "
                "¿Puedes escribir el mensaje o intentar de nuevo?"
            )
            return base
        except Exception as e:
            logger.error("Error procesando audio Meta: %s", e)
            base.respuesta_directa = (
                "Recibí tu audio pero no pude procesarlo. "
                "¿Puedes escribir el mensaje?"
            )
            return base

    async def parsear_webhook(self, request: Request) -> list[MensajeEntrante]:
        body_bytes = await self._leer_body(request)
        if not body_bytes:
            return []

        try:
            body = json.loads(body_bytes)
        except json.JSONDecodeError:
            logger.error("Webhook Meta con JSON inválido")
            return []

        mensajes: list[MensajeEntrante] = []
        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                field = change.get("field", "")

                # Mensajes entrantes de clientes
                for msg in value.get("messages", []):
                    parsed = self._parsear_mensaje(msg, es_propio=False)
                    if parsed:
                        if parsed.es_audio:
                            parsed = await self._procesar_audio(parsed)
                        mensajes.append(parsed)

                # Coexistence: ecos enviados desde WhatsApp Business app (dueña)
                echo_keys = ("smb_message_echoes", "message_echoes")
                if field in echo_keys or any(value.get(k) for k in echo_keys):
                    for key in echo_keys:
                        for msg in value.get(key, []):
                            parsed = self._parsear_mensaje(msg, es_propio=True)
                            if parsed:
                                mensajes.append(parsed)

        return mensajes

    async def enviar_mensaje(self, telefono: str, mensaje: str) -> bool:
        if not self.access_token or not self.phone_number_id:
            logger.warning("META_ACCESS_TOKEN o META_PHONE_NUMBER_ID no configurados")
            return False

        url = (
            f"https://graph.facebook.com/{self.api_version}/"
            f"{self.phone_number_id}/messages"
        )
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": telefono,
            "type": "text",
            "text": {"body": mensaje},
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            if response.status_code != 200:
                logger.error("Error Meta API: %s — %s", response.status_code, response.text)
                return False
            data = response.json()
            msg_id = (data.get("messages") or [{}])[0].get("id", "")
            logger.info("Mensaje Meta enviado a %s — id=%s", telefono, msg_id)
            return True
