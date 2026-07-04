# agent/api_routes.py — API REST producción

import os
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends
from pydantic import BaseModel
from agent.auth import verificar_credenciales, crear_token, requiere_admin, TOKEN_TTL_SEC
from agent.booking_service import (
    listar_slots_publicos,
    listar_reservas_admin,
    confirmar_pago_reserva,
    consultar_disponibilidad,
)
from agent.package_service import (
    listar_planes,
    crear_reserva_web,
    confirmar_pago_package,
    listar_admin_pendientes,
    registrar_comprobante,
    reprogramar_clase_package,
)
from agent.receipt_vision import analizar_comprobante, descargar_imagen
from agent.providers import obtener_proveedor

router = APIRouter(prefix="/api", tags=["jumping"])
proveedor = obtener_proveedor()


class ReservaWebBody(BaseModel):
    nombre: str
    telefono: str
    plan_codigo: str
    slot_ids: list[int]
    metodo_pago: str


class ReprogramarBody(BaseModel):
    telefono: str
    session_id: int
    nuevo_slot_id: int


class LoginBody(BaseModel):
    usuario: str
    password: str


async def _notificar_confirmacion_package(result: dict):
    tel = result.get("telefono_cliente", "")
    if not tel:
        return
    clases = result.get("clases", [])
    if clases:
        resumen = ", ".join(f"{c['fecha']} {c['hora']}" for c in clases[:3])
        extra = f" (+{len(clases)-3} más)" if len(clases) > 3 else ""
    else:
        resumen = "tus clases"
        extra = ""
    msg = f"Pago confirmado. Tus clases quedaron agendadas: {resumen}{extra}. Te esperamos en Jumping Fit."
    await proveedor.enviar_mensaje(tel, msg)


@router.get("/planes")
async def api_planes():
    return await listar_planes()


@router.get("/slots")
async def api_slots(fecha: str = ""):
    return await listar_slots_publicos(fecha)


@router.get("/disponibilidad")
async def api_disponibilidad(fecha: str = "", dias: int = 7):
    return await consultar_disponibilidad(fecha, dias)


@router.post("/reservas/web")
async def api_reserva_web(body: ReservaWebBody):
    result = await crear_reserva_web(
        nombre=body.nombre,
        telefono=body.telefono,
        plan_codigo=body.plan_codigo,
        slot_ids=body.slot_ids,
        metodo_pago=body.metodo_pago,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/comprobantes")
async def api_comprobante(
    telefono: str = Form(...),
    package_id: int = Form(0),
    archivo: UploadFile = File(...),
):
    data = await archivo.read()
    ct = archivo.content_type or "image/jpeg"
    analisis = await analizar_comprobante(data, ct)
    # Guardar referencia (en prod: subir a Supabase Storage; aquí base64 ref corta)
    url_ref = f"upload:{telefono}:{package_id}"
    result = await registrar_comprobante(
        telefono=telefono,
        imagen_url=url_ref,
        package_id=package_id or None,
        monto_detectado=analisis.get("monto_detectado"),
        confianza=analisis.get("confianza"),
        ia_notas=analisis.get("notas", ""),
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return {**result, "analisis": analisis}


@router.post("/auth/login")
async def api_auth_login(body: LoginBody):
    if not verificar_credenciales(body.usuario, body.password):
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")
    return {
        "token": crear_token(body.usuario),
        "expira_en": TOKEN_TTL_SEC,
    }


@router.get("/admin/pendientes")
async def api_admin_pendientes(_admin: dict = Depends(requiere_admin)):
    return await listar_admin_pendientes()


@router.get("/reservas")
async def api_reservas(fecha: str = "", _admin: dict = Depends(requiere_admin)):
    return await listar_reservas_admin(fecha)


@router.post("/packages/{package_id}/confirmar-pago")
async def api_confirmar_package(package_id: int, _admin: dict = Depends(requiere_admin)):
    result = await confirmar_pago_package(package_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    await _notificar_confirmacion_package(result)
    return result


@router.post("/packages/{package_id}/reprogramar")
async def api_reprogramar_package(package_id: int, body: ReprogramarBody, _admin: dict = Depends(requiere_admin)):
    result = await reprogramar_clase_package(
        telefono=body.telefono,
        package_id=package_id,
        session_id=body.session_id,
        nuevo_slot_id=body.nuevo_slot_id,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/reservas/{reserva_id}/confirmar-pago")
async def api_confirmar_pago(reserva_id: int, _admin: dict = Depends(requiere_admin)):
    result = await confirmar_pago_reserva(reserva_id=reserva_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    await _notificar_confirmacion_package({
        "telefono_cliente": result.get("telefono_cliente"),
        "clases": [{"fecha": result["fecha"], "hora": result["hora"]}],
    })
    return result


@router.get("/config/public")
async def api_config_public():
    import yaml
    try:
        with open("config/business.yaml", "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    except FileNotFoundError:
        cfg = {}
    pagos = cfg.get("pagos", {})
    negocio = cfg.get("negocio", {})
    web = cfg.get("web", {})
    humanos = cfg.get("humanos", {})
    whatsapp = humanos.get("telefono_escalacion") or ""
    if not whatsapp and cfg.get("admin", {}).get("telefonos"):
        whatsapp = cfg["admin"]["telefonos"][0]
    return {
        "nombre": negocio.get("nombre", "Jumping Fit"),
        "slogan": negocio.get("slogan", "Salta, quema y transforma tu vida"),
        "ubicacion": negocio.get("ubicacion", ""),
        "horario": negocio.get("horario", ""),
        "web_url": os.getenv("WEB_PUBLIC_URL", web.get("url_publica", "/web/")),
        "instagram": web.get("instagram", ""),
        "whatsapp": whatsapp,
        "nequi": pagos.get("nequi", ""),
        "banco": pagos.get("banco", ""),
    }
