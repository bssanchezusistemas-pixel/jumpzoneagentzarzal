# agent/providers/twilio.py — Adaptador para Twilio WhatsApp
# Generado por AgentKit

import os
import logging
import base64
import httpx
from fastapi import Request
from agent.providers.base import ProveedorWhatsApp, MensajeEntrante
from agent.audio import descargar_audio_twilio, transcribir_audio

logger = logging.getLogger("agentkit")


class ProveedorTwilio(ProveedorWhatsApp):
    """Proveedor de WhatsApp usando Twilio."""

    def __init__(self):
        self.account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        self.auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        self.phone_number = os.getenv("TWILIO_PHONE_NUMBER")

    async def parsear_webhook(self, request: Request) -> list[MensajeEntrante]:
        """Parsea texto y notas de voz del webhook de Twilio."""
        form = await request.form()
        texto = (form.get("Body") or "").strip()
        telefono = form.get("From", "").replace("whatsapp:", "")
        mensaje_id = form.get("MessageSid", "")
        num_media = int(form.get("NumMedia", 0) or 0)
        es_audio = False

        # Nota de voz: Body suele venir vacío y NumMedia >= 1
        if num_media > 0:
            media_type = (form.get("MediaContentType0") or "").lower()
            media_url = form.get("MediaUrl0")

            if media_url and "audio" in media_type:
                try:
                    audio_bytes, content_type = await descargar_audio_twilio(
                        media_url, self.account_sid, self.auth_token
                    )
                    transcrito = await transcribir_audio(audio_bytes, content_type)
                    if transcrito:
                        texto = transcrito
                        es_audio = True
                        logger.info(f"Nota de voz transcrita de {telefono}")
                    elif not texto:
                        texto = "[AUDIO_NO_TRANSCRITO]"
                except Exception as e:
                    logger.error(f"Error procesando audio: {e}")
                    if not texto:
                        texto = "[AUDIO_NO_TRANSCRITO]"

            elif media_url and "image" in media_type:
                return [MensajeEntrante(
                    telefono=telefono,
                    texto=texto or "[COMPROBANTE]",
                    mensaje_id=mensaje_id,
                    es_propio=False,
                    es_imagen=True,
                    media_url=media_url,
                )]

        if not texto:
            return []

        if texto == "[AUDIO_NO_TRANSCRITO]":
            return [MensajeEntrante(
                telefono=telefono,
                texto="",
                mensaje_id=mensaje_id,
                es_propio=False,
                es_audio=True,
                respuesta_directa="Recibí tu audio pero no pude transcribirlo. ¿Puedes escribir el mensaje o intentar de nuevo?",
            )]

        return [MensajeEntrante(
            telefono=telefono,
            texto=texto,
            mensaje_id=mensaje_id,
            es_propio=False,
            es_audio=es_audio,
        )]

    async def descargar_media(self, msg: MensajeEntrante) -> tuple[bytes, str]:
        if not msg.media_url:
            raise ValueError("Sin URL de media Twilio")
        return await descargar_audio_twilio(
            msg.media_url, self.account_sid, self.auth_token
        )

    async def enviar_mensaje(self, telefono: str, mensaje: str) -> bool:
        """Envía mensaje via Twilio API."""
        if not all([self.account_sid, self.auth_token, self.phone_number]):
            logger.warning("Variables de Twilio no configuradas")
            return False
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"
        auth = base64.b64encode(f"{self.account_sid}:{self.auth_token}".encode()).decode()
        headers = {"Authorization": f"Basic {auth}"}
        data = {
            "From": f"whatsapp:{self.phone_number}",
            "To": f"whatsapp:{telefono}",
            "Body": mensaje,
        }
        async with httpx.AsyncClient() as client:
            r = await client.post(url, data=data, headers=headers)
            if r.status_code != 201:
                logger.error(f"Error Twilio: {r.status_code} — {r.text}")
            else:
                body = r.json()
                logger.info(
                    "Mensaje enviado a %s — sid=%s status=%s",
                    telefono, body.get("sid"), body.get("status"),
                )
            return r.status_code == 201
