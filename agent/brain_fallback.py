# agent/brain_fallback.py — Respuestas claras (público 30+)

import os
import re
import yaml
import logging
from agent import booking_service as bs
from agent.providers import obtener_proveedor

logger = logging.getLogger("agentkit")


def _web_url() -> str:
    return os.getenv("WEB_PUBLIC_URL", "http://localhost:8000/web/")


def _cfg():
    try:
        with open("config/business.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}


def _fmt_fecha(f: str) -> str:
    try:
        y, m, d = map(int, f.split("-"))
        from datetime import date
        return date(y, m, d).strftime("%a %d/%m")
    except Exception:
        return f


async def _escalar_humano(telefono: str, texto: str) -> str:
    cfg = _cfg()
    h = cfg.get("humanos", {})
    admin_tel = h.get("telefono_escalacion", "")
    if admin_tel:
        proveedor = obtener_proveedor()
        msg = h.get("mensaje_escalacion", "Cliente pide ayuda: {telefono}").format(
            telefono=telefono, texto=texto[:100]
        )
        await proveedor.enviar_mensaje(admin_tel.replace(" ", ""), msg)
    return "Te conecto con la dueña. Te escribirá pronto. Si prefieres, llama al centro."


async def respuesta_sin_ia(mensaje: str, telefono: str) -> str | None:
    t = mensaje.lower().strip()
    web = _web_url()
    pagos = _cfg().get("pagos", {})

    if re.search(r"\b(humano|persona|dueña|asesor|hablar con alguien)\b", t):
        return await _escalar_humano(telefono, mensaje)

    if re.search(r"\b(hola|buenas|hey|saludos|info)\b", t):
        web = _web_url()
        return (
            "¡Hola! Soy JumpBot de Jump Zone 👋\n\n"
            "Escribe *RESERVAR* y te ayudo paso a paso por aquí.\n"
            f"También puedes reservar en la web: {web}\n\n"
            "Si tienes dudas de horarios, pagos o quieres hablar con la dueña, pregúntame."
        )

    if re.search(r"\b(reservar|agendar|apartar|clase|inscribir)\b", t):
        return None  # lo maneja wa_reserva.py

    if re.search(r"\b(plan|semana|quincena|mes|precio|cuanto|cuesta|valor)\b", t):
        return (
            "Planes Jump Zone:\n"
            "• Día: 1 clase (precio por confirmar)\n"
            "• Semana: 3 clases a elegir\n"
            "• Quincena: 6 clases en 2 semanas\n"
            "• Mes: 12 clases a programar\n\n"
            f"Reserva en: {web}"
        )

    if re.search(r"\b(horario|disponib|libre|cupos?)\b", t):
        r = await bs.consultar_disponibilidad(dias=7)
        slots = r.get("disponibles", [])[:8]
        if not slots:
            return f"No hay cupos esta semana. Reserva en {web} o escribe otra fecha."
        lineas = [f"• {_fmt_fecha(s['fecha'])} {s['hora']}: {s['cupos_libres']} cupos"
                  for s in slots]
        return "Cupos disponibles:\n" + "\n".join(lineas) + "\n\nEscribe RESERVAR para apartar tu cupo."

    if re.search(r"\b(mis reservas|mi reserva)\b", t):
        r = await bs.consultar_mis_reservas(telefono)
        reservas = r.get("reservas", [])
        if not reservas:
            return f"No tienes reservas. Agenda en {web}"
        lineas = [f"• {_fmt_fecha(x['fecha'])} {x['hora']} ({x['estado']})" for x in reservas[:5]]
        return "Tus clases:\n" + "\n".join(lineas)

    if re.search(r"\b(reprogramar|cambiar horario|mover clase)\b", t):
        return (
            "Puedes cambiar 1 clase por plan, con mínimo 24 horas de anticipación.\n"
            "Escríbenos la fecha actual y la nueva que prefieres, o pide hablar con la dueña."
        )

    if re.search(r"\b(nequi|pago|pagar|transfer|comprobante|cuenta)\b", t):
        return (
            f"Datos de pago:\nNequi: {pagos.get('nequi', '')}\n"
            f"{pagos.get('banco', '')}\n\n"
            "Envía foto del comprobante por aquí. La dueña confirma tu cupo."
        )

    if re.search(r"\b(ubicacion|donde|direccion|llegar)\b", t):
        return "Jump Zone — centro de jumping. Escríbenos para la dirección exacta o pide hablar con la dueña."

    return None
