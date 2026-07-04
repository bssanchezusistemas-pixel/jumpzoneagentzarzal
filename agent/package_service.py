# agent/package_service.py — Planes y reservas web

import os
import yaml
import logging
from datetime import datetime, date, time, timedelta
from sqlalchemy import select, and_
from agent.memory import async_session
from agent.booking_models import (
    Plan, Slot, Client, Booking, ClientPackage, PackageSession, PaymentReceipt, ClassType,
)

logger = logging.getLogger("agentkit")

CUPO_MAX = 15
HORA_APERTURA = 5
HORA_CIERRE = 21
ANTICIPACION_HORAS = 24
MAX_REPROGRAMACIONES = 1


def _cargar_config() -> dict:
    try:
        with open("config/business.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}


def _normalizar_tel(t: str) -> str:
    t = t.strip().replace(" ", "").replace("-", "")
    if not t.startswith("+"):
        if t.startswith("57"):
            t = "+" + t
        elif len(t) == 10:
            t = "+57" + t
    return t


async def seed_planes():
    cfg = _cargar_config()
    planes_cfg = cfg.get("planes", {})
    defaults = [
        ("dia", "Día suelto", 1, 7, planes_cfg.get("dia", 0)),
        ("semana", "Plan semana (3 clases)", 3, 14, planes_cfg.get("semana", 90000)),
        ("quincena", "Plan quincena (6 clases)", 6, 21, planes_cfg.get("quincena", 160000)),
        ("mes", "Plan mes (12 clases)", 12, 45, planes_cfg.get("mes", 280000)),
    ]
    async with async_session() as session:
        for codigo, nombre, clases, vigencia, precio in defaults:
            r = await session.execute(select(Plan).where(Plan.codigo == codigo))
            if r.scalar_one_or_none():
                continue
            session.add(Plan(
                codigo=codigo,
                nombre=nombre,
                clases_incluidas=clases,
                vigencia_dias=vigencia,
                precio=precio,
                descripcion=f"{clases} clase(s) a elegir",
            ))
        await session.commit()


async def asegurar_slots_futuros(dias: int = 30):
    """Genera slots 5am-9pm si faltan fechas."""
    async with async_session() as session:
        r = await session.execute(select(ClassType).limit(1))
        tipo = r.scalar_one_or_none()
        if not tipo:
            return

        hoy = date.today()
        fin = hoy + timedelta(days=dias)
        r2 = await session.execute(
            select(Slot.fecha).where(Slot.fecha >= hoy, Slot.fecha <= fin).distinct()
        )
        fechas_existentes = {row[0] for row in r2.all()}

        for d in range(dias + 1):
            f = hoy + timedelta(days=d)
            if f.weekday() == 6 or f in fechas_existentes:
                continue
            for h in range(HORA_APERTURA, HORA_CIERRE + 1):
                session.add(Slot(
                    class_type_id=tipo.id,
                    fecha=f,
                    hora_inicio=time(h, 0),
                    capacity_max=CUPO_MAX,
                    capacity_booked=0,
                    estado="activo",
                ))
        await session.commit()


async def listar_planes() -> dict:
    async with async_session() as session:
        r = await session.execute(select(Plan).where(Plan.activo == 1))
        planes = []
        for p in r.scalars().all():
            planes.append({
                "codigo": p.codigo,
                "nombre": p.nombre,
                "clases": p.clases_incluidas,
                "vigencia_dias": p.vigencia_dias,
                "precio": float(p.precio),
                "descripcion": p.descripcion or f"Elige {p.clases_incluidas} clase(s)",
            })
        return {"planes": planes}


async def crear_reserva_web(
    nombre: str,
    telefono: str,
    plan_codigo: str,
    slot_ids: list[int],
    metodo_pago: str,
) -> dict:
    telefono = _normalizar_tel(telefono)
    if not nombre.strip():
        return {"error": "Nombre requerido"}
    if metodo_pago not in ("efectivo", "transferencia"):
        return {"error": "Método de pago inválido"}

    async with async_session() as session:
        r = await session.execute(select(Plan).where(Plan.codigo == plan_codigo, Plan.activo == 1))
        plan = r.scalar_one_or_none()
        if not plan:
            return {"error": "Plan no encontrado"}

        if len(slot_ids) != plan.clases_incluidas:
            return {
                "error": f"Debes elegir {plan.clases_incluidas} horario(s) para este plan",
            }

        if len(set(slot_ids)) != len(slot_ids):
            return {"error": "No puedes repetir el mismo horario"}

        precio = float(plan.precio)
        if plan_codigo == "dia" and precio <= 0:
            rslot = await session.execute(select(Slot).where(Slot.id == slot_ids[0]))
            s0 = rslot.scalar_one_or_none()
            if s0:
                rct = await session.execute(select(ClassType).where(ClassType.id == s0.class_type_id))
                ct = rct.scalar_one_or_none()
                precio = float(ct.precio) if ct else 35000

        r_c = await session.execute(select(Client).where(Client.telefono == telefono))
        client = r_c.scalar_one_or_none()
        if not client:
            client = Client(telefono=telefono, nombre=nombre.strip())
            session.add(client)
            await session.flush()
        else:
            client.nombre = nombre.strip()

        vence = date.today() + timedelta(days=plan.vigencia_dias)
        pkg = ClientPackage(
            client_id=client.id,
            plan_id=plan.id,
            clases_totales=plan.clases_incluidas,
            clases_restantes=0,
            estado="pendiente_pago",
            pago_metodo=metodo_pago,
            pago_estado="pendiente",
            total_pagar=precio,
            vence=vence,
        )
        session.add(pkg)
        await session.flush()

        clases_agendadas = []
        for sid in slot_ids:
            rsl = await session.execute(
                select(Slot, ClassType)
                .join(ClassType, Slot.class_type_id == ClassType.id, isouter=True)
                .where(Slot.id == sid, Slot.estado == "activo")
            )
            row = rsl.first()
            if not row:
                await session.rollback()
                return {"error": f"Horario {sid} no encontrado"}

            slot, _ = row
            libres = slot.capacity_max - slot.capacity_booked
            if libres < 1:
                await session.rollback()
                return {"error": f"Sin cupo en {slot.fecha} {slot.hora_inicio.strftime('%H:%M')}"}

            booking = Booking(
                slot_id=slot.id,
                client_id=client.id,
                package_id=pkg.id,
                personas=1,
                estado="pendiente_pago",
                pago_estado="pendiente",
            )
            slot.capacity_booked += 1
            session.add(booking)
            await session.flush()

            session.add(PackageSession(
                package_id=pkg.id,
                slot_id=slot.id,
                booking_id=booking.id,
                estado="programada",
            ))
            clases_agendadas.append({
                "fecha": slot.fecha.isoformat(),
                "hora": slot.hora_inicio.strftime("%H:%M"),
            })

        await session.commit()

        cfg = _cargar_config()
        pagos = cfg.get("pagos", {})
        web_url = os.getenv("WEB_PUBLIC_URL", "http://localhost:8000/web/")

        return {
            "package_id": pkg.id,
            "plan": plan.nombre,
            "total_pagar": precio,
            "metodo_pago": metodo_pago,
            "clases": clases_agendadas,
            "estado": "pendiente_pago",
            "nequi": pagos.get("nequi", ""),
            "banco": pagos.get("banco", ""),
            "mensaje": (
                "Reserva registrada. "
                + ("Paga en efectivo al llegar." if metodo_pago == "efectivo"
                   else "Transfiere y envía comprobante por WhatsApp o en la web.")
            ),
            "web_url": web_url,
        }


async def registrar_comprobante(
    telefono: str,
    imagen_url: str,
    package_id: int | None = None,
    monto_detectado: float | None = None,
    confianza: float | None = None,
    ia_notas: str = "",
) -> dict:
    telefono = _normalizar_tel(telefono)
    async with async_session() as session:
        r = await session.execute(select(Client).where(Client.telefono == telefono))
        client = r.scalar_one_or_none()
        if not client:
            return {"error": "Cliente no encontrado"}

        if not package_id:
            r2 = await session.execute(
                select(ClientPackage)
                .where(
                    ClientPackage.client_id == client.id,
                    ClientPackage.pago_estado == "pendiente",
                )
                .order_by(ClientPackage.creado.desc())
            )
            pkg = r2.scalars().first()
            package_id = pkg.id if pkg else None

        receipt = PaymentReceipt(
            package_id=package_id,
            client_id=client.id,
            imagen_url=imagen_url,
            monto_detectado=monto_detectado,
            confianza=confianza,
            ia_notas=ia_notas,
            estado="sugerido" if monto_detectado else "pendiente",
        )
        session.add(receipt)
        await session.commit()
        await session.refresh(receipt)
        return {
            "receipt_id": receipt.id,
            "package_id": package_id,
            "monto_detectado": monto_detectado,
            "estado": receipt.estado,
        }


async def confirmar_pago_package(package_id: int) -> dict:
    async with async_session() as session:
        pkg = await session.get(ClientPackage, package_id)
        if not pkg:
            return {"error": "Paquete no encontrado"}
        if pkg.pago_estado == "confirmado":
            return {"error": "Ya estaba confirmado"}

        pkg.estado = "activo"
        pkg.pago_estado = "confirmado"

        r = await session.execute(
            select(Booking).where(Booking.package_id == package_id)
        )
        for b in r.scalars().all():
            b.estado = "confirmada"
            b.pago_estado = "confirmado"

        r2 = await session.execute(select(Client).where(Client.id == pkg.client_id))
        client = r2.scalar_one()

        r3 = await session.execute(
            select(Booking, Slot)
            .join(Slot, Booking.slot_id == Slot.id)
            .where(Booking.package_id == package_id)
            .order_by(Slot.fecha)
        )
        clases = [
            {"fecha": s.fecha.isoformat(), "hora": s.hora_inicio.strftime("%H:%M")}
            for _, s in r3.all()
        ]

        await session.commit()
        return {
            "package_id": pkg.id,
            "telefono_cliente": client.telefono,
            "nombre": client.nombre,
            "clases": clases,
            "estado": "confirmada",
        }


async def listar_admin_pendientes() -> dict:
    async with async_session() as session:
        r = await session.execute(
            select(ClientPackage, Client, Plan)
            .join(Client, ClientPackage.client_id == Client.id)
            .join(Plan, ClientPackage.plan_id == Plan.id)
            .where(ClientPackage.pago_estado != "confirmado")
            .order_by(ClientPackage.creado.desc())
        )
        items = []
        for pkg, c, p in r.all():
            r2 = await session.execute(
                select(PaymentReceipt)
                .where(PaymentReceipt.package_id == pkg.id)
                .order_by(PaymentReceipt.creado.desc())
            )
            rec = r2.scalars().first()
            r3 = await session.execute(
                select(Booking, Slot)
                .join(Slot, Booking.slot_id == Slot.id)
                .where(Booking.package_id == pkg.id)
                .order_by(Slot.fecha)
            )
            clases = [
                f"{s.fecha.isoformat()} {s.hora_inicio.strftime('%H:%M')}"
                for _, s in r3.all()
            ]
            items.append({
                "package_id": pkg.id,
                "cliente": c.nombre or c.telefono,
                "telefono": c.telefono,
                "plan": p.nombre,
                "total": float(pkg.total_pagar),
                "metodo": pkg.pago_metodo,
                "pago": pkg.pago_estado,
                "clases": clases,
                "comprobante": {
                    "id": rec.id if rec else None,
                    "monto_ia": float(rec.monto_detectado) if rec and rec.monto_detectado else None,
                    "notas_ia": rec.ia_notas if rec else "",
                    "url": rec.imagen_url if rec else "",
                } if rec else None,
            })
        return {"pendientes": items}


async def reprogramar_clase_package(
    telefono: str,
    package_id: int,
    session_id: int,
    nuevo_slot_id: int,
) -> dict:
    """Un cambio por plan, mínimo 24h antes de la clase actual."""
    telefono = _normalizar_tel(telefono)
    async with async_session() as session:
        r = await session.execute(
            select(ClientPackage, Client)
            .join(Client, ClientPackage.client_id == Client.id)
            .where(ClientPackage.id == package_id, Client.telefono == telefono)
        )
        row = r.first()
        if not row:
            return {"error": "Plan no encontrado para este teléfono"}

        pkg, _ = row
        if pkg.pago_estado != "confirmado":
            return {"error": "Solo puedes reprogramar después de confirmar el pago"}
        if pkg.reprogramaciones_usadas >= MAX_REPROGRAMACIONES:
            return {"error": "Ya usaste el único cambio permitido en este plan"}

        r2 = await session.execute(
            select(PackageSession, Slot, Booking)
            .join(Slot, PackageSession.slot_id == Slot.id)
            .join(Booking, PackageSession.booking_id == Booking.id, isouter=True)
            .where(PackageSession.id == session_id, PackageSession.package_id == package_id)
        )
        row2 = r2.first()
        if not row2:
            return {"error": "Clase no encontrada en tu plan"}

        ps, slot_viejo, booking = row2
        if ps.estado == "cancelada":
            return {"error": "Esta clase ya fue cancelada"}

        inicio_viejo = datetime.combine(slot_viejo.fecha, slot_viejo.hora_inicio)
        if datetime.now() > inicio_viejo - timedelta(hours=ANTICIPACION_HORAS):
            return {
                "error": f"Solo puedes cambiar con al menos {ANTICIPACION_HORAS} horas de anticipación",
            }

        r3 = await session.execute(
            select(Slot).where(Slot.id == nuevo_slot_id, Slot.estado == "activo")
        )
        slot_nuevo = r3.scalar_one_or_none()
        if not slot_nuevo:
            return {"error": "Nuevo horario no disponible"}
        if slot_nuevo.id == slot_viejo.id:
            return {"error": "Elige un horario diferente"}

        libres = slot_nuevo.capacity_max - slot_nuevo.capacity_booked
        if libres < 1:
            return {"error": "Sin cupo en el nuevo horario"}

        slot_viejo.capacity_booked = max(0, slot_viejo.capacity_booked - 1)
        slot_nuevo.capacity_booked += 1

        if booking:
            booking.slot_id = slot_nuevo.id
            booking.reprogramado_de = slot_viejo.id
            if booking.estado != "cancelada":
                booking.estado = "confirmada"

        ps.slot_id = slot_nuevo.id
        pkg.reprogramaciones_usadas += 1

        await session.commit()
        return {
            "package_id": package_id,
            "session_id": session_id,
            "nueva_fecha": slot_nuevo.fecha.isoformat(),
            "nueva_hora": slot_nuevo.hora_inicio.strftime("%H:%M"),
            "cambios_restantes": max(0, MAX_REPROGRAMACIONES - pkg.reprogramaciones_usadas),
        }
