# agent/tools.py — Herramientas del agente
# Generado por AgentKit

import os
import yaml
import logging
import json
from datetime import datetime

logger = logging.getLogger("agentkit")

RESERVAS_FILE = "config/reservas.json"
PEDIDOS_FILE = "config/pedidos.json"
LEADS_FILE = "config/leads.json"


def _cargar_json(ruta: str) -> list:
    if not os.path.exists(ruta):
        return []
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def _guardar_json(ruta: str, datos: list):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)


def cargar_info_negocio() -> dict:
    try:
        with open("config/business.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        return {}


def obtener_horario() -> dict:
    info = cargar_info_negocio()
    return {
        "horario": info.get("negocio", {}).get("horario", "No disponible"),
        "reservas_siempre": info.get("negocio", {}).get("reservas_siempre", True),
    }


def buscar_en_knowledge(consulta: str) -> str:
    """Busca información relevante en los archivos de /knowledge."""
    resultados = []
    knowledge_dir = "knowledge"

    if not os.path.exists(knowledge_dir):
        return "No hay archivos de conocimiento disponibles."

    for archivo in os.listdir(knowledge_dir):
        ruta = os.path.join(knowledge_dir, archivo)
        if archivo.startswith(".") or not os.path.isfile(ruta):
            continue
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                contenido = f.read()
                if consulta.lower() in contenido.lower():
                    resultados.append(f"[{archivo}]: {contenido[:500]}")
        except (UnicodeDecodeError, IOError):
            continue

    if resultados:
        return "\n---\n".join(resultados)
    return "No encontré información específica sobre eso en mis archivos."


def reservar_evento(telefono: str, fecha: str, hora: str, invitados: int,
                    tipo_evento: str, productos: str) -> dict:
    """Registra una reserva para evento."""
    reservas = _cargar_json(RESERVAS_FILE)
    reserva = {
        "id": len(reservas) + 1,
        "telefono": telefono,
        "fecha": fecha,
        "hora": hora,
        "invitados": invitados,
        "tipo_evento": tipo_evento,
        "productos": productos,
        "estado": "pendiente_confirmacion",
        "creado": datetime.utcnow().isoformat(),
    }
    reservas.append(reserva)
    _guardar_json(RESERVAS_FILE, reservas)
    logger.info(f"Reserva creada: #{reserva['id']} para {telefono}")
    return reserva


def registrar_lead(telefono: str, nombre: str, interes: str, presupuesto: str = "") -> dict:
    """Registra un lead de ventas."""
    leads = _cargar_json(LEADS_FILE)
    lead = {
        "id": len(leads) + 1,
        "telefono": telefono,
        "nombre": nombre,
        "interes": interes,
        "presupuesto": presupuesto,
        "estado": "nuevo",
        "creado": datetime.utcnow().isoformat(),
    }
    leads.append(lead)
    _guardar_json(LEADS_FILE, leads)
    return lead


def agregar_al_pedido(telefono: str, producto: str, cantidad: int = 1) -> dict:
    """Agrega un producto al pedido del cliente."""
    pedidos = _cargar_json(PEDIDOS_FILE)
    pedido = next((p for p in pedidos if p["telefono"] == telefono and p["estado"] == "abierto"), None)

    if not pedido:
        pedido = {
            "id": len(pedidos) + 1,
            "telefono": telefono,
            "items": [],
            "estado": "abierto",
            "creado": datetime.utcnow().isoformat(),
        }
        pedidos.append(pedido)

    pedido["items"].append({"producto": producto, "cantidad": cantidad})
    _guardar_json(PEDIDOS_FILE, pedidos)
    return pedido


def confirmar_pedido(telefono: str) -> dict:
    """Confirma el pedido abierto del cliente."""
    pedidos = _cargar_json(PEDIDOS_FILE)
    for pedido in pedidos:
        if pedido["telefono"] == telefono and pedido["estado"] == "abierto":
            pedido["estado"] = "confirmado"
            pedido["confirmado"] = datetime.utcnow().isoformat()
            _guardar_json(PEDIDOS_FILE, pedidos)
            return pedido
    return {"error": "No hay pedido abierto"}
