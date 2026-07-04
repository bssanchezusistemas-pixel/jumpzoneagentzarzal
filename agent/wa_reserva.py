# agent/wa_reserva.py — Reserva por WhatsApp (tono humano, selección gradual)

import json
import re
import logging
from datetime import date, datetime
from collections import defaultdict

from sqlalchemy import select

from agent.memory import async_session
from agent.booking_models import WaSession, Client
from agent.booking_service import consultar_disponibilidad
from agent.package_service import listar_planes, crear_reserva_web, _normalizar_tel, _cargar_config

logger = logging.getLogger("agentkit")

INICIO = re.compile(r"\b(reservar|agendar|apartar|quiero\s+clase|inscribir)\b", re.I)
CANCELAR = re.compile(r"\b(cancelar|salir|detener|stop)\b", re.I)
MAS_DIAS = re.compile(
    r"\b(m[aá]s\s+d[ií]as|otros?\s+d[ií]as|diferentes|distintos|otra\s+fecha|"
    r"solo\s+hay|pocos\s+d[ií]as|no\s+alcanza|ver\s+m[aá]s)\b",
    re.I,
)
LISTO = re.compile(r"\b(listo|ya\s+est[aá]|siguiente|continuar|ok)\b", re.I)

PLAN_MAP = {
    "1": "dia", "dia": "dia", "día": "dia",
    "2": "semana", "semana": "semana",
    "3": "quincena", "quincena": "quincena",
    "4": "mes", "mes": "mes",
}

DIAS_ES = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]


def _fmt_fecha(f: str) -> str:
    try:
        y, m, d = map(int, f.split("-"))
        dt = date(y, m, d)
        return f"{DIAS_ES[dt.weekday()]} {d:02d}/{m:02d}"
    except Exception:
        return f


async def _save_session(telefono: str, etapa: str, datos: dict):
    tel = _normalizar_tel(telefono)
    async with async_session() as session:
        r = await session.execute(select(WaSession).where(WaSession.telefono == tel))
        ws = r.scalar_one_or_none()
        if not ws:
            ws = WaSession(telefono=tel)
            session.add(ws)
        ws.etapa = etapa
        ws.datos = json.dumps(datos, ensure_ascii=False)
        ws.actualizado = datetime.utcnow()
        await session.commit()


async def _clear_session(telefono: str):
    await _save_session(telefono, "idle", {})


async def _nombre_cliente(telefono: str) -> str:
    tel = _normalizar_tel(telefono)
    async with async_session() as session:
        r = await session.execute(select(Client).where(Client.telefono == tel))
        c = r.scalar_one_or_none()
        return (c.nombre or "").strip() if c else ""


def _parse_numeros(texto: str) -> list[int]:
    return [int(x) for x in re.findall(r"\d+", texto)]


def _resumen_elegidos(elegidos: list[dict]) -> str:
    if not elegidos:
        return ""
    lineas = [f"  • {_fmt_fecha(e['fecha'])} {e['hora']}" for e in elegidos]
    return "Ya tienes:\n" + "\n".join(lineas)


async def _cargar_opciones(dias: int = 14, excluir_ids: set | None = None) -> list[dict]:
    r = await consultar_disponibilidad(dias=dias)
    slots = r.get("disponibles", [])
    excluir = excluir_ids or set()
    out = []
    for s in slots:
        if s["slot_id"] in excluir:
            continue
        out.append({
            "slot_id": s["slot_id"],
            "fecha": s["fecha"],
            "hora": s["hora"],
            "cupos": s["cupos_libres"],
        })
    return out[:50]


def _texto_horarios_agrupado(opciones: list[dict], n: int, elegidos: list[dict]) -> str:
    faltan = n - len(elegidos)
    por_fecha = defaultdict(list)
    for i, s in enumerate(opciones, 1):
        por_fecha[s["fecha"]].append((i, s))

    partes = []
    if elegidos:
        partes.append(_resumen_elegidos(elegidos))
        partes.append(f"\nTe faltan {faltan} horario(s). Elige más (manda los números):\n")

    if faltan == n:
        partes.append(
            f"Tu plan pide {n} clase(s). Puedes elegir de a pocos — no tienes que mandar todos juntos.\n"
            "Si necesitas más días distintos, escribe *más días*.\n"
        )
    else:
        partes.append("Puedes seguir eligiendo números, o escribe *listo* cuando termines.\n")

    dias_mostrados = 0
    for fecha in sorted(por_fecha.keys()):
        if dias_mostrados >= 10:
            partes.append("\n… Hay más fechas. Escribe *más días* para verlas.")
            break
        partes.append(f"\n📅 {_fmt_fecha(fecha)}")
        for num, s in por_fecha[fecha][:6]:
            partes.append(f"  {num}. {s['hora']} ({s['cupos']} cupos)")
        dias_mostrados += 1

    return "\n".join(partes)


async def _mostrar_horarios(telefono: str, datos: dict, dias: int = 14) -> str:
    elegidos = datos.get("elegidos", [])
    excluir = {e["slot_id"] for e in elegidos}
    opciones = await _cargar_opciones(dias=dias, excluir_ids=excluir)
    if not opciones:
        return (
            "Por ahora no veo más cupos libres en esas fechas. "
            "Prueba en un rato o escribe CANCELAR."
        )
    datos["opciones"] = opciones
    datos["dias_vista"] = dias
    await _save_session(telefono, "horarios", datos)
    n = datos.get("clases_necesarias", 1)
    intro = f"Perfecto, plan *{datos.get('plan_nombre', '')}*.\n\n"
    return intro + _texto_horarios_agrupado(opciones, n, elegidos)


async def _iniciar(telefono: str) -> str:
    data = await listar_planes()
    lineas = []
    for i, p in enumerate(data.get("planes", []), 1):
        precio = f"${p['precio']:,.0f}" if p["precio"] > 0 else "según el horario"
        lineas.append(f"{i}. {p['nombre']} — {p['clases']} clase(s) — {precio}")

    await _save_session(telefono, "plan", {})
    return (
        "¡Claro! Te ayudo a reservar 😊\n\n"
        "Estos son los planes:\n"
        + "\n".join(lineas)
        + "\n\n¿Cuál te interesa? (ej: *semana* o *3*)\n"
        "Si cambias de idea, escribe *cancelar*."
    )


async def _etapa_plan(telefono: str, texto: str, datos: dict) -> str:
    clave = texto.lower().strip()
    codigo = PLAN_MAP.get(clave)
    if not codigo:
        return (
            "No alcancé a entender cuál plan quieres 🤔\n"
            "Puedes decirme: *día*, *semana*, *quincena* o *mes* (también 1, 2, 3 o 4)."
        )

    planes = {p["codigo"]: p for p in (await listar_planes()).get("planes", [])}
    plan = planes.get(codigo)
    if not plan:
        return "Ese plan no está disponible ahora. ¿Probamos con otro?"

    datos.update({
        "plan_codigo": codigo,
        "plan_nombre": plan["nombre"],
        "clases_necesarias": plan["clases"],
        "elegidos": [],
    })
    return await _mostrar_horarios(telefono, datos, dias=14)


def _agregar_horarios(datos: dict, nums: list[int]) -> tuple[str | None, bool]:
    """Agrega horarios. Retorna (error, completado)."""
    opciones = datos.get("opciones", [])
    n = datos.get("clases_necesarias", 1)
    elegidos = datos.get("elegidos", [])
    ids_ya = {e["slot_id"] for e in elegidos}

    for num in nums:
        if num < 1 or num > len(opciones):
            return f"El *{num}* no está en la lista (usa 1 a {len(opciones)}).", False
        slot = opciones[num - 1]
        if slot["slot_id"] in ids_ya:
            return f"Ya habías elegido el horario *{num}* ({_fmt_fecha(slot['fecha'])} {slot['hora']}).", False
        elegidos.append(slot)
        ids_ya.add(slot["slot_id"])

    datos["elegidos"] = elegidos
    if len(elegidos) >= n:
        datos["slot_ids"] = [e["slot_id"] for e in elegidos[:n]]
        return None, True

    faltan = n - len(elegidos)
    resumen = _resumen_elegidos(elegidos)
    return (
        f"{resumen}\n\n"
        f"Listo, van {len(elegidos)} de {n}. "
        f"{'Solo falta 1' if faltan == 1 else 'Te faltan ' + str(faltan)}. "
        "Manda otro número, o *más días* si quieres otras fechas."
    ), False


async def _pasar_a_pago_o_nombre(telefono: str, datos: dict) -> str:
    nombre = await _nombre_cliente(telefono)
    if nombre:
        datos["nombre"] = nombre
        await _save_session(telefono, "pago", datos)
        return (
            f"Genial, {nombre} 👍\n\n"
            "¿Cómo vas a pagar?\n"
            "• *efectivo* — pagas al llegar\n"
            "• *transferencia* — Nequi o banco"
        )
    await _save_session(telefono, "nombre", datos)
    return "¿A nombre de quién dejamos la reserva?"


async def _etapa_horarios(telefono: str, texto: str, datos: dict) -> str:
    t = texto.strip()

    if MAS_DIAS.search(t):
        dias = max(datos.get("dias_vista", 14), 21)
        if dias < 28:
            dias = 28
        msg = (
            "Entiendo, quieres ver más fechas para repartir tus clases. "
            "Aquí van más días:\n"
        )
        return msg + await _mostrar_horarios(telefono, datos, dias=dias)

    nums = _parse_numeros(t)
    if not nums and LISTO.search(t):
        n = datos.get("clases_necesarias", 1)
        elegidos = datos.get("elegidos", [])
        if len(elegidos) >= n:
            return await _pasar_a_pago_o_nombre(telefono, datos)
        faltan = n - len(elegidos)
        return (
            f"Todavía faltan {faltan} horario(s) por elegir. "
            "Manda los números de la lista, o *más días* si necesitas otras fechas."
        )

    if not nums:
        if MAS_DIAS.search(t) or len(t) > 15:
            return (
                "Te entiendo. Para ir eligiendo, manda los *números* de la lista "
                "(puedes de a uno o varios, ej: 4 16 35).\n"
                "Si quieres ver fechas más lejanas, escribe *más días*."
            )
        return (
            "Dime los números de los horarios que te sirven "
            "(ej: 4 o 4, 16, 35). Puedes ir de a pocos, sin afán."
        )

    err, completo = _agregar_horarios(datos, nums)
    if err:
        await _save_session(telefono, "horarios", datos)
        return err

    if completo:
        return await _pasar_a_pago_o_nombre(telefono, datos)

    await _save_session(telefono, "horarios", datos)
    return err or "Seguimos."


async def _etapa_nombre(telefono: str, texto: str, datos: dict) -> str:
    nombre = texto.strip()
    if len(nombre) < 2 or nombre.isdigit():
        return "¿Me dices tu nombre, por favor? Así lo dejamos en la reserva."
    datos["nombre"] = nombre
    await _save_session(telefono, "pago", datos)
    return (
        f"Gracias, {nombre}.\n\n"
        "¿Pagas en *efectivo* al llegar o por *transferencia*?"
    )


async def _etapa_pago(telefono: str, texto: str, datos: dict) -> str:
    t = texto.lower().strip()
    if any(w in t for w in ("efectivo", "cash", "efectivo en el centro", "1")):
        metodo = "efectivo"
    elif any(w in t for w in ("transfer", "nequi", "banco", "2")):
        metodo = "transferencia"
    else:
        return "¿*Efectivo* en el centro o *transferencia*? Como te quede más fácil."

    result = await crear_reserva_web(
        nombre=datos["nombre"],
        telefono=telefono,
        plan_codigo=datos["plan_codigo"],
        slot_ids=datos["slot_ids"],
        metodo_pago=metodo,
    )
    await _clear_session(telefono)

    if "error" in result:
        return (
            f"Uy, algo no salió bien: {result['error']}\n"
            "Escribe *reservar* y lo intentamos otra vez."
        )

    clases = result.get("clases", [])
    resumen = "\n".join(
        f"  • {_fmt_fecha(c['fecha'])} {c['hora']}" for c in clases[:6]
    )
    if len(clases) > 6:
        resumen += f"\n  • … y {len(clases) - 6} más"

    cfg = _cargar_config()
    pagos = cfg.get("pagos", {})
    msg = (
        f"¡Listo, {datos['nombre']}! Quedó tu reserva 🎉\n\n"
        f"Plan: {result['plan']}\n"
        f"Clases:\n{resumen}\n\n"
        f"Total: ${result['total_pagar']:,.0f}\n"
    )
    if metodo == "efectivo":
        msg += "Pagas en efectivo cuando llegues al centro."
    else:
        msg += (
            f"Transfiere y mándame la foto del comprobante por aquí.\n"
            f"Nequi: {pagos.get('nequi', '')}\n"
            f"{pagos.get('banco', '')}"
        )
    msg += "\n\nLa dueña confirma el pago y te avisamos. ¡Nos vemos en Jump Zone!"
    return msg


async def procesar_reserva_wa(telefono: str, texto: str) -> str | None:
    if not texto or not texto.strip():
        return None

    tel = _normalizar_tel(telefono)
    async with async_session() as session:
        r = await session.execute(select(WaSession).where(WaSession.telefono == tel))
        ws = r.scalar_one_or_none()

    etapa = ws.etapa if ws else "idle"
    datos = json.loads(ws.datos) if ws and ws.datos else {}

    if CANCELAR.search(texto) and etapa != "idle":
        await _clear_session(telefono)
        return "Sin problema, cancelamos. Cuando quieras reservar, escríbeme *reservar*."

    if etapa == "idle":
        if not INICIO.search(texto):
            return None
        return await _iniciar(telefono)

    if etapa == "plan":
        return await _etapa_plan(telefono, texto, datos)
    if etapa == "horarios":
        if "elegidos" not in datos:
            datos["elegidos"] = []
        return await _etapa_horarios(telefono, texto, datos)
    if etapa == "nombre":
        return await _etapa_nombre(telefono, texto, datos)
    if etapa == "pago":
        return await _etapa_pago(telefono, texto, datos)

    await _clear_session(telefono)
    return None
