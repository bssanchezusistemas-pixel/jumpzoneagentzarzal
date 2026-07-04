# agent/admin.py — Comandos admin para la dueña

import os
import re
import yaml
import logging

logger = logging.getLogger("agentkit")


def _normalizar_tel(t: str) -> str:
    return re.sub(r"\D", "", t.replace("whatsapp:", ""))


def cargar_telefonos_admin() -> set[str]:
    phones = set()
    env = os.getenv("ADMIN_PHONES", "")
    if env:
        for p in env.split(","):
            phones.add(_normalizar_tel(p.strip()))
    try:
        with open("config/business.yaml", "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        for p in cfg.get("admin", {}).get("telefonos", []):
            phones.add(_normalizar_tel(p))
    except FileNotFoundError:
        pass
    return phones


def es_admin(telefono: str) -> bool:
    t = _normalizar_tel(telefono)
    admins = cargar_telefonos_admin()
    return any(t.endswith(a) or a.endswith(t) for a in admins)


async def procesar_comando_admin(texto: str) -> dict | None:
    """
    Comandos: confirmar reserva 12 | confirmar +573013892917
    Retorna dict con acción o None si no es comando admin.
    """
    if not texto:
        return None
    t = texto.strip().lower()
    if not t.startswith("confirmar"):
        return None

    m = re.search(r"confirmar\s+reserva\s+(\d+)", t)
    if m:
        return {"accion": "confirmar_pago", "reserva_id": int(m.group(1))}

    m = re.search(r"confirmar\s+(\+?\d{10,15})", t)
    if m:
        return {"accion": "confirmar_pago", "telefono": m.group(1)}

    return None
