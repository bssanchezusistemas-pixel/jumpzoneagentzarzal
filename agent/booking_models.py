# agent/booking_models.py — Modelos Jump Zone producción

from datetime import datetime, date, time
from sqlalchemy import String, Text, DateTime, Date, Time, Integer, ForeignKey, Numeric, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from agent.memory import Base


class ClassType(Base):
    __tablename__ = "class_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(100))
    duracion_minutos: Mapped[int] = mapped_column(Integer, default=60)
    precio: Mapped[float] = mapped_column(Numeric(10, 2))

    slots: Mapped[list["Slot"]] = relationship(back_populates="class_type")


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(String(30), unique=True)
    nombre: Mapped[str] = mapped_column(String(100))
    clases_incluidas: Mapped[int] = mapped_column(Integer)
    vigencia_dias: Mapped[int] = mapped_column(Integer, default=30)
    precio: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    descripcion: Mapped[str] = mapped_column(Text, default="")
    activo: Mapped[int] = mapped_column(Integer, default=1)


class Slot(Base):
    __tablename__ = "slots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    class_type_id: Mapped[int] = mapped_column(ForeignKey("class_types.id"), nullable=True)
    fecha: Mapped[date] = mapped_column(Date, index=True)
    hora_inicio: Mapped[time] = mapped_column(Time)
    capacity_max: Mapped[int] = mapped_column(Integer, default=15)
    capacity_booked: Mapped[int] = mapped_column(Integer, default=0)
    estado: Mapped[str] = mapped_column(String(20), default="activo")

    class_type: Mapped["ClassType"] = relationship(back_populates="slots")
    bookings: Mapped[list["Booking"]] = relationship(back_populates="slot")


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telefono: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    nombre: Mapped[str] = mapped_column(String(100), default="")

    bookings: Mapped[list["Booking"]] = relationship(back_populates="client")
    packages: Mapped[list["ClientPackage"]] = relationship(back_populates="client")


class ClientPackage(Base):
    __tablename__ = "client_packages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"))
    clases_totales: Mapped[int] = mapped_column(Integer)
    clases_restantes: Mapped[int] = mapped_column(Integer)
    reprogramaciones_usadas: Mapped[int] = mapped_column(Integer, default=0)
    estado: Mapped[str] = mapped_column(String(30), default="pendiente_pago")
    pago_metodo: Mapped[str] = mapped_column(String(30), default="")
    pago_estado: Mapped[str] = mapped_column(String(30), default="pendiente")
    total_pagar: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    creado: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    vence: Mapped[date | None] = mapped_column(Date, nullable=True)

    client: Mapped["Client"] = relationship(back_populates="packages")
    plan: Mapped["Plan"] = relationship()
    sessions: Mapped[list["PackageSession"]] = relationship(back_populates="package")
    receipts: Mapped[list["PaymentReceipt"]] = relationship(back_populates="package")


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slot_id: Mapped[int] = mapped_column(ForeignKey("slots.id"), index=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)
    package_id: Mapped[int | None] = mapped_column(ForeignKey("client_packages.id"), nullable=True)
    personas: Mapped[int] = mapped_column(Integer, default=1)
    estado: Mapped[str] = mapped_column(String(30), default="pendiente_pago")
    pago_estado: Mapped[str] = mapped_column(String(30), default="pendiente")
    notas: Mapped[str] = mapped_column(Text, default="")
    creado: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    reprogramado_de: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recordatorio_enviado: Mapped[bool] = mapped_column(Integer, default=0)

    slot: Mapped["Slot"] = relationship(back_populates="bookings")
    client: Mapped["Client"] = relationship(back_populates="bookings")
    package: Mapped["ClientPackage | None"] = relationship()


class PackageSession(Base):
    __tablename__ = "package_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("client_packages.id"), index=True)
    slot_id: Mapped[int] = mapped_column(ForeignKey("slots.id"))
    booking_id: Mapped[int | None] = mapped_column(ForeignKey("bookings.id"), nullable=True)
    estado: Mapped[str] = mapped_column(String(30), default="programada")

    package: Mapped["ClientPackage"] = relationship(back_populates="sessions")
    slot: Mapped["Slot"] = relationship()


class PaymentReceipt(Base):
    __tablename__ = "payment_receipts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    package_id: Mapped[int | None] = mapped_column(ForeignKey("client_packages.id"), nullable=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    imagen_url: Mapped[str] = mapped_column(Text, default="")
    monto_detectado: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    confianza: Mapped[float | None] = mapped_column(Float, nullable=True)
    ia_notas: Mapped[str] = mapped_column(Text, default="")
    estado: Mapped[str] = mapped_column(String(30), default="pendiente")
    creado: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    package: Mapped["ClientPackage | None"] = relationship(back_populates="receipts")


class WaSession(Base):
    """Estado del flujo de reserva por WhatsApp."""
    __tablename__ = "wa_sessions"

    telefono: Mapped[str] = mapped_column(String(50), primary_key=True)
    etapa: Mapped[str] = mapped_column(String(30), default="idle")
    datos: Mapped[str] = mapped_column(Text, default="{}")
    actualizado: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
