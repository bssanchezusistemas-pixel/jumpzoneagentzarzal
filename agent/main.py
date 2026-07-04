# agent/main.py — Servidor FastAPI Jump Zone

import os
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from agent.brain import generar_respuesta
from agent.memory import inicializar_db, guardar_mensaje, obtener_historial
from agent.providers import obtener_proveedor
from agent.audio import precargar_modelo_whisper
from agent.booking_service import inicializar_booking_db, seed_datos_iniciales, confirmar_pago_reserva
from agent.package_service import seed_planes, asegurar_slots_futuros, registrar_comprobante
from agent.receipt_vision import analizar_comprobante
from agent.admin import es_admin, procesar_comando_admin
from agent.api_routes import router as api_router
from agent.reminders import iniciar_recordatorios
from agent.wa_reserva import procesar_reserva_wa

load_dotenv()

ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
log_level = logging.DEBUG if ENVIRONMENT == "development" else logging.INFO
logging.basicConfig(level=log_level)
logger = logging.getLogger("agentkit")

proveedor = obtener_proveedor()
PORT = int(os.getenv("PORT", 8000))
WEB_DIR = Path(__file__).resolve().parent.parent / "web"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await inicializar_db()
    await inicializar_booking_db()
    await seed_datos_iniciales()
    await seed_planes()
    await asegurar_slots_futuros(30)
    precargar_modelo_whisper()
    iniciar_recordatorios(proveedor)
    logger.info("Jump Zone — servidor listo en puerto %s", PORT)
    yield


app = FastAPI(
    title="Jump Zone — Reservas WhatsApp",
    version="2.0.0",
    lifespan=lifespan,
)

app.include_router(api_router)

if WEB_DIR.is_dir():
    app.mount("/web", StaticFiles(directory=str(WEB_DIR), html=True), name="web")


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "jump-zone", "agente": "JumpBot"}


@app.get("/")
async def publico():
    if WEB_DIR.is_dir():
        return RedirectResponse(url="/web/index.html")
    return {"status": "ok", "service": "jump-zone"}


@app.get("/admin")
async def admin_redirect():
    return RedirectResponse(url="/web/admin.html")


@app.get("/webhook")
async def webhook_verificacion(request: Request):
    resultado = await proveedor.validar_webhook(request)
    if resultado is not None:
        return PlainTextResponse(str(resultado))
    return {"status": "ok"}


async def _notificar_cliente_confirmacion(result: dict):
    tel = result.get("telefono_cliente", "")
    if not tel:
        return
    msg = (
        f"Listo, tu clase quedó confirmada: {result['fecha']} a las {result['hora']}. "
        f"Cupos: {result['personas']} persona(s). Te esperamos en Jump Zone."
    )
    await proveedor.enviar_mensaje(tel, msg)


async def _procesar_comprobante_wa(msg):
    """Imagen de comprobante por WhatsApp → IA sugiere → dueña confirma."""
    try:
        img_bytes, ct = await proveedor.descargar_media(msg)
        analisis = await analizar_comprobante(img_bytes, ct)
        imagen_ref = msg.media_url or (f"meta:{msg.media_id}" if msg.media_id else "upload:wa")
        reg = await registrar_comprobante(
            telefono=msg.telefono,
            imagen_url=imagen_ref,
            monto_detectado=analisis.get("monto_detectado"),
            confianza=analisis.get("confianza"),
            ia_notas=analisis.get("notas", ""),
        )
        monto = analisis.get("monto_detectado")
        if monto:
            resp = (
                f"Recibí tu comprobante. Detectamos ${monto:,.0f} COP. "
                "La dueña lo revisará y te confirmará en breve."
            )
        else:
            resp = "Recibí tu comprobante. La dueña lo revisará y te confirmará en breve."
        await guardar_mensaje(msg.telefono, "user", "[Comprobante enviado]")
        await guardar_mensaje(msg.telefono, "assistant", resp)
        await proveedor.enviar_mensaje(msg.telefono, resp)
        logger.info("Comprobante registrado #%s", reg.get("receipt_id"))
    except Exception as e:
        logger.error("Error comprobante WA: %s", e)
        await proveedor.enviar_mensaje(
            msg.telefono,
            "Recibí tu imagen. La dueña lo revisará manualmente y te confirmará pronto.",
        )


async def _procesar_mensaje(msg):
    """Procesa un mensaje en segundo plano (IA puede tardar; Twilio ya recibió 200)."""
    try:
        if msg.es_imagen and msg.media_url:
            await _procesar_comprobante_wa(msg)
            return

        if msg.respuesta_directa:
            await proveedor.enviar_mensaje(msg.telefono, msg.respuesta_directa)
            if msg.es_imagen:
                await guardar_mensaje(msg.telefono, "user", "[Comprobante enviado]")
                await guardar_mensaje(msg.telefono, "assistant", msg.respuesta_directa)
            return

        if not msg.texto:
            return

        if es_admin(msg.telefono):
            cmd = await procesar_comando_admin(msg.texto)
            if cmd and cmd.get("accion") == "confirmar_pago":
                result = await confirmar_pago_reserva(
                    reserva_id=cmd.get("reserva_id"),
                    telefono=cmd.get("telefono", ""),
                )
                if "error" in result:
                    respuesta = f"No pude confirmar: {result['error']}"
                else:
                    await _notificar_cliente_confirmacion(result)
                    respuesta = (
                        f"Pago confirmado. Reserva #{result['reserva_id']} — "
                        f"{result['fecha']} {result['hora']}. Cliente notificado."
                    )
                await proveedor.enviar_mensaje(msg.telefono, respuesta)
                return

        # Flujo guiado de reserva por WhatsApp
        reserva_wa = await procesar_reserva_wa(msg.telefono, msg.texto)
        if reserva_wa is not None:
            await guardar_mensaje(msg.telefono, "user", msg.texto)
            await guardar_mensaje(msg.telefono, "assistant", reserva_wa)
            await proveedor.enviar_mensaje(msg.telefono, reserva_wa)
            return

        tipo = "audio" if msg.es_audio else "texto"
        logger.info("Mensaje (%s) de %s: %s", tipo, msg.telefono, msg.texto[:80])

        historial = await obtener_historial(msg.telefono)
        respuesta = await generar_respuesta(msg.texto, historial, telefono=msg.telefono)

        contenido = f"[Audio] {msg.texto}" if msg.es_audio else msg.texto
        await guardar_mensaje(msg.telefono, "user", contenido)
        await guardar_mensaje(msg.telefono, "assistant", respuesta)
        ok = await proveedor.enviar_mensaje(msg.telefono, respuesta)
        if not ok:
            logger.error("No se pudo enviar respuesta a %s", msg.telefono)
    except Exception as e:
        logger.error("Error procesando mensaje de %s: %s", msg.telefono, e)


@app.post("/webhook")
async def webhook_handler(request: Request, background_tasks: BackgroundTasks):
    try:
        mensajes = await proveedor.parsear_webhook(request)

        for msg in mensajes:
            if msg.es_propio:
                continue
            background_tasks.add_task(_procesar_mensaje, msg)

        return PlainTextResponse("")

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error en webhook: %s", e)
        return PlainTextResponse("")
