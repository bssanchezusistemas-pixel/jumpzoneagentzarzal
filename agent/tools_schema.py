# agent/tools_schema.py — Herramientas Claude para JumpBot

TOOLS = [
    {
        "name": "consultar_disponibilidad",
        "description": "Consulta cupos libres de clases de jumping. Usar cuando pregunten horarios, disponibilidad, qué hay libre.",
        "input_schema": {
            "type": "object",
            "properties": {
                "fecha": {
                    "type": "string",
                    "description": "Fecha YYYY-MM-DD. Vacío para próximos 7 días.",
                },
                "dias": {
                    "type": "integer",
                    "description": "Días a consultar si no hay fecha (default 7)",
                },
            },
            "required": [],
        },
    },
    {
        "name": "crear_reserva",
        "description": "Crea una reserva de cupos. La reserva queda pendiente de pago hasta que la dueña confirme.",
        "input_schema": {
            "type": "object",
            "properties": {
                "slot_id": {"type": "integer", "description": "ID del slot/horario"},
                "personas": {"type": "integer", "description": "Número de personas"},
                "nombre": {"type": "string", "description": "Nombre del cliente"},
            },
            "required": ["slot_id", "personas"],
        },
    },
    {
        "name": "reprogramar_reserva",
        "description": "Reprograma una reserva existente a otro horario. Requiere 24h de anticipación.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reserva_id": {"type": "integer"},
                "nuevo_slot_id": {"type": "integer"},
            },
            "required": ["reserva_id", "nuevo_slot_id"],
        },
    },
    {
        "name": "consultar_mis_reservas",
        "description": "Lista las reservas activas del cliente actual.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]


async def ejecutar_tool(nombre: str, args: dict, telefono: str) -> dict:
    from agent import booking_service as bs

    if nombre == "consultar_disponibilidad":
        return await bs.consultar_disponibilidad(
            fecha_str=args.get("fecha", ""),
            dias=args.get("dias", 7),
        )
    if nombre == "crear_reserva":
        return await bs.crear_reserva(
            telefono=telefono,
            slot_id=args["slot_id"],
            personas=args["personas"],
            nombre=args.get("nombre", ""),
        )
    if nombre == "reprogramar_reserva":
        return await bs.reprogramar_reserva(
            telefono=telefono,
            reserva_id=args["reserva_id"],
            nuevo_slot_id=args["nuevo_slot_id"],
        )
    if nombre == "consultar_mis_reservas":
        return await bs.consultar_mis_reservas(telefono)
    return {"error": f"Herramienta desconocida: {nombre}"}
