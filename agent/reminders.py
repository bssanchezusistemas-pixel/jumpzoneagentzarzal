# agent/reminders.py — Recordatorios WhatsApp programados

import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from agent.booking_service import reservas_para_recordatorio, marcar_recordatorio_enviado

logger = logging.getLogger("agentkit")
scheduler = AsyncIOScheduler()


def iniciar_recordatorios(proveedor):
    """Programa revisión cada hora de recordatorios 24h antes."""

    async def enviar_recordatorios():
        try:
            pendientes = await reservas_para_recordatorio()
            for r in pendientes:
                msg = (
                    f"Recordatorio Jump Zone: mañana {r['fecha']} a las {r['hora']} "
                    f"tienes clase de jumping. Te esperamos."
                )
                ok = await proveedor.enviar_mensaje(r["telefono"], msg)
                if ok:
                    await marcar_recordatorio_enviado(r["booking_id"])
                    logger.info(f"Recordatorio enviado a {r['telefono']}")
        except Exception as e:
            logger.error(f"Error recordatorios: {e}")

    scheduler.add_job(enviar_recordatorios, "cron", hour="*", minute=0, id="recordatorios_24h")
    scheduler.start()
    logger.info("Scheduler de recordatorios iniciado")
