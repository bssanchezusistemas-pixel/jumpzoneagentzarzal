# agent/booking_service.py — Lógica de reservas Jump Zone

import os
import yaml
import logging
from datetime import datetime, date, time, timedelta
from sqlalchemy import select, and_
from agent.memory import async_session, engine
from agent.booking_models import ClassType, Slot, Client, Booking, Base

logger = logging.getLogger("agentkit")

ANTICIPACION_HORAS = 24
CUPO_MAX = 15


def _cargar_config() -> dict:
    try:
        with open("config/business.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}


async def inicializar_booking_db():
    from agent import booking_models  # noqa: F401 — registra tablas en Base.metadata
    from sqlalchemy import text

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        def _migrar_columnas(sync_conn):
            if sync_conn.dialect.name != "sqlite":
                return
            rows = sync_conn.execute(text("PRAGMA table_info(bookings)")).fetchall()
            if not rows:
                return
            cols = {r[1] for r in rows}
            if "package_id" not in cols:
                sync_conn.execute(text(
                    "ALTER TABLE bookings ADD COLUMN package_id INTEGER"
                ))
                logger.info("Migración: columna bookings.package_id añadida")

        await conn.run_sync(_migrar_columnas)


async def seed_datos_iniciales():
    """Crea tipos de clase y slots para los próximos 14 días si no existen."""
    async with async_session() as session:
        result = await session.execute(select(ClassType).limit(1))
        if result.scalar_one_or_none():
            return

        tipos = [
            ClassType(nombre="Jump Básico", duracion_minutos=60, precio=35000),
            ClassType(nombre="Jump Intermedio", duracion_minutos=60, precio=40000),
            ClassType(nombre="Jump Avanzado", duracion_minutos=60, precio=45000),
            ClassType(nombre="Open Jump", duracion_minutos=60, precio=30000),
        ]
        session.add_all(tipos)
        await session.flush()

        tipo_basico = tipos[0]
        hoy = date.today()
        horas = list(range(5, 22))

        for dias in range(14):
            d = hoy + timedelta(days=dias)
            if d.weekday() == 6:
                continue
            for h in horas:
                booked = 0
                if dias == 1 and h == 11:
                    booked = 15
                elif dias == 0 and h == 10:
                    booked = 8
                session.add(Slot(
                    class_type_id=tipo_basico.id,
                    fecha=d,
                    hora_inicio=time(h, 0),
                    capacity_max=CUPO_MAX,
                    capacity_booked=booked,
                    estado="activo",
                ))
        await session.commit()
        logger.info("Datos iniciales de jumping creados (14 días de slots)")


async def _obtener_o_crear_cliente(telefono: str, nombre: str = "") -> Client:
    async with async_session() as session:
        result = await session.execute(select(Client).where(Client.telefono == telefono))
        client = result.scalar_one_or_none()
        if not client:
            client = Client(telefono=telefono, nombre=nombre or "")
            session.add(client)
            await session.commit()
            await session.refresh(client)
        elif nombre and not client.nombre:
            client.nombre = nombre
            await session.commit()
        return client


def _slot_a_dict(slot: Slot, class_type: ClassType | None = None) -> dict:
    libres = slot.capacity_max - slot.capacity_booked
    return {
        "slot_id": slot.id,
        "fecha": slot.fecha.isoformat(),
        "hora": slot.hora_inicio.strftime("%H:%M"),
        "cupos_libres": libres,
        "cupos_max": slot.capacity_max,
        "ocupados": slot.capacity_booked,
        "lleno": libres <= 0,
        "clase": class_type.nombre if class_type else "Jump",
        "precio": float(class_type.precio) if class_type else 35000,
    }


async def consultar_disponibilidad(fecha_str: str = "", dias: int = 7) -> dict:
    """Consulta cupos. fecha_str: YYYY-MM-DD o vacío para próximos N días."""
    async with async_session() as session:
        query = (
            select(Slot, ClassType)
            .join(ClassType, Slot.class_type_id == ClassType.id, isouter=True)
            .where(Slot.estado == "activo")
        )

        if fecha_str:
            try:
                f = date.fromisoformat(fecha_str)
                query = query.where(Slot.fecha == f)
            except ValueError:
                return {"error": "Fecha inválida. Usa formato YYYY-MM-DD"}
        else:
            fin = date.today() + timedelta(days=dias)
            query = query.where(and_(Slot.fecha >= date.today(), Slot.fecha <= fin))

        query = query.order_by(Slot.fecha, Slot.hora_inicio)
        result = await session.execute(query)
        rows = result.all()

        slots = [_slot_a_dict(s, ct) for s, ct in rows if s.capacity_booked < s.capacity_max]
        return {"disponibles": slots, "total": len(slots)}


async def crear_reserva(telefono: str, slot_id: int, personas: int, nombre: str = "") -> dict:
    if personas < 1:
        return {"error": "Mínimo 1 persona"}

    await _obtener_o_crear_cliente(telefono, nombre)

    async with async_session() as session:
        result = await session.execute(
            select(Slot, ClassType)
            .join(ClassType, Slot.class_type_id == ClassType.id, isouter=True)
            .where(Slot.id == slot_id)
        )
        row = result.first()
        if not row:
            return {"error": "Horario no encontrado"}

        slot, class_type = row
        libres = slot.capacity_max - slot.capacity_booked
        if personas > libres:
            return {"error": f"Solo hay {libres} cupos libres en ese horario"}

        c_result = await session.execute(select(Client).where(Client.telefono == telefono))
        c = c_result.scalar_one()
        if nombre:
            c.nombre = nombre

        booking = Booking(
            slot_id=slot.id,
            client_id=c.id,
            personas=personas,
            estado="pendiente_pago",
            pago_estado="pendiente",
        )
        slot.capacity_booked += personas
        session.add(booking)
        await session.commit()
        await session.refresh(booking)

        precio = float(class_type.precio) if class_type else 35000
        total = precio * personas
        cfg = _cargar_config()
        pagos = cfg.get("pagos", {})

        return {
            "reserva_id": booking.id,
            "fecha": slot.fecha.isoformat(),
            "hora": slot.hora_inicio.strftime("%H:%M"),
            "personas": personas,
            "total_pagar": total,
            "estado": "pendiente_pago",
            "nequi": pagos.get("nequi", ""),
            "banco": pagos.get("banco", ""),
            "mensaje": "La dueña confirmará tu pago manualmente.",
        }


async def reprogramar_reserva(telefono: str, reserva_id: int, nuevo_slot_id: int) -> dict:
    async with async_session() as session:
        result = await session.execute(
            select(Booking, Slot, Client)
            .join(Slot, Booking.slot_id == Slot.id)
            .join(Client, Booking.client_id == Client.id)
            .where(Booking.id == reserva_id, Client.telefono == telefono)
        )
        row = result.first()
        if not row:
            return {"error": "Reserva no encontrada"}

        booking, slot_viejo, _ = row
        if booking.estado == "cancelada":
            return {"error": "Esta reserva está cancelada"}

        inicio_viejo = datetime.combine(slot_viejo.fecha, slot_viejo.hora_inicio)
        if datetime.now() > inicio_viejo - timedelta(hours=ANTICIPACION_HORAS):
            return {"error": f"Solo puedes reprogramar con al menos {ANTICIPACION_HORAS} horas de anticipación"}

        result2 = await session.execute(select(Slot).where(Slot.id == nuevo_slot_id))
        slot_nuevo = result2.scalar_one_or_none()
        if not slot_nuevo:
            return {"error": "Nuevo horario no encontrado"}

        libres = slot_nuevo.capacity_max - slot_nuevo.capacity_booked
        if booking.personas > libres:
            return {"error": f"Solo hay {libres} cupos en el nuevo horario"}

        slot_viejo.capacity_booked -= booking.personas
        slot_nuevo.capacity_booked += booking.personas
        booking.slot_id = slot_nuevo.id
        booking.reprogramado_de = slot_viejo.id
        booking.estado = "pendiente_pago" if booking.pago_estado != "confirmado" else "confirmada"

        await session.commit()
        return {
            "reserva_id": booking.id,
            "nueva_fecha": slot_nuevo.fecha.isoformat(),
            "nueva_hora": slot_nuevo.hora_inicio.strftime("%H:%M"),
            "estado": booking.estado,
        }


async def consultar_mis_reservas(telefono: str) -> dict:
    async with async_session() as session:
        result = await session.execute(
            select(Booking, Slot, ClassType)
            .join(Slot, Booking.slot_id == Slot.id)
            .join(Client, Booking.client_id == Client.id)
            .join(ClassType, Slot.class_type_id == ClassType.id, isouter=True)
            .where(Client.telefono == telefono, Booking.estado != "cancelada")
            .order_by(Slot.fecha.desc())
        )
        reservas = []
        for b, s, ct in result.all():
            reservas.append({
                "id": b.id,
                "fecha": s.fecha.isoformat(),
                "hora": s.hora_inicio.strftime("%H:%M"),
                "personas": b.personas,
                "estado": b.estado,
                "pago": b.pago_estado,
                "clase": ct.nombre if ct else "Jump",
            })
        return {"reservas": reservas}


async def confirmar_pago_reserva(reserva_id: int | None = None, telefono: str = "") -> dict:
    """Dueña confirma pago. Por id de reserva o teléfono del cliente."""
    async with async_session() as session:
        if reserva_id:
            booking = await session.get(Booking, reserva_id)
        elif telefono:
            result = await session.execute(
                select(Booking)
                .join(Client, Booking.client_id == Client.id)
                .where(
                    Client.telefono.contains(telefono.replace("whatsapp:", "").replace("+", "")),
                    Booking.estado == "pendiente_pago",
                )
                .order_by(Booking.creado.desc())
            )
            booking = result.scalars().first()
        else:
            return {"error": "Indica reserva_id o teléfono"}

        if not booking:
            return {"error": "Reserva pendiente no encontrada"}

        booking.estado = "confirmada"
        booking.pago_estado = "confirmado"
        await session.commit()

        result = await session.execute(
            select(Booking, Slot, Client)
            .join(Slot, Booking.slot_id == Slot.id)
            .join(Client, Booking.client_id == Client.id)
            .where(Booking.id == booking.id)
        )
        b, s, c = result.one()
        return {
            "reserva_id": b.id,
            "telefono_cliente": c.telefono,
            "nombre": c.nombre,
            "fecha": s.fecha.isoformat(),
            "hora": s.hora_inicio.strftime("%H:%M"),
            "personas": b.personas,
            "estado": "confirmada",
        }


async def listar_reservas_admin(fecha_str: str = "") -> dict:
    async with async_session() as session:
        query = (
            select(Booking, Slot, Client, ClassType)
            .join(Slot, Booking.slot_id == Slot.id)
            .join(Client, Booking.client_id == Client.id)
            .join(ClassType, Slot.class_type_id == ClassType.id, isouter=True)
            .where(Booking.estado != "cancelada")
        )
        if fecha_str:
            try:
                f = date.fromisoformat(fecha_str)
                query = query.where(Slot.fecha == f)
            except ValueError:
                pass
        query = query.order_by(Slot.fecha, Slot.hora_inicio)
        result = await session.execute(query)

        items = []
        for b, s, c, ct in result.all():
            items.append({
                "id": b.id,
                "cliente": c.nombre or c.telefono,
                "telefono": c.telefono,
                "fecha": s.fecha.isoformat(),
                "hora": s.hora_inicio.strftime("%H:%M"),
                "personas": b.personas,
                "estado": b.estado,
                "pago": b.pago_estado,
                "clase": ct.nombre if ct else "Jump",
            })
        return {"reservas": items}


async def listar_slots_publicos(fecha_str: str = "") -> dict:
    async with async_session() as session:
        query = (
            select(Slot, ClassType)
            .join(ClassType, Slot.class_type_id == ClassType.id, isouter=True)
            .where(Slot.estado == "activo", Slot.fecha >= date.today())
        )
        if fecha_str:
            try:
                query = query.where(Slot.fecha == date.fromisoformat(fecha_str))
            except ValueError:
                pass
        query = query.order_by(Slot.fecha, Slot.hora_inicio).limit(200)
        result = await session.execute(query)
        return {"slots": [_slot_a_dict(s, ct) for s, ct in result.all()]}


async def reservas_para_recordatorio() -> list[dict]:
    """Reservas confirmadas mañana sin recordatorio enviado."""
    manana = date.today() + timedelta(days=1)
    async with async_session() as session:
        result = await session.execute(
            select(Booking, Slot, Client)
            .join(Slot, Booking.slot_id == Slot.id)
            .join(Client, Booking.client_id == Client.id)
            .where(
                Slot.fecha == manana,
                Booking.estado == "confirmada",
                Booking.recordatorio_enviado == 0,
            )
        )
        out = []
        for b, s, c in result.all():
            out.append({
                "booking_id": b.id,
                "telefono": c.telefono,
                "nombre": c.nombre,
                "fecha": s.fecha.isoformat(),
                "hora": s.hora_inicio.strftime("%H:%M"),
            })
        return out


async def marcar_recordatorio_enviado(booking_id: int):
    async with async_session() as session:
        b = await session.get(Booking, booking_id)
        if b:
            b.recordatorio_enviado = 1
            await session.commit()
