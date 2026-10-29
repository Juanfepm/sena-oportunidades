"""Datos persistentes mínimos y contenido temporal cifrado por campaña."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base_datos import Base
from .dominio.estados import EstadoCampana, EstadoPago, Plan


def ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


def nuevo_id() -> str:
    return str(uuid4())


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=nuevo_id)
    identificador_externo: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    correo_google: Mapped[str | None] = mapped_column(String(254))
    nombre_google: Mapped[str | None] = mapped_column(String(180))
    plan: Mapped[str] = mapped_column(String(12), default=Plan.GRATIS, nullable=False)
    premium_hasta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    es_administrador: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=ahora_utc, nullable=False
    )
    ultimo_acceso_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=ahora_utc, nullable=False
    )

    __table_args__ = (Index("ix_usuarios_correo_google_unico", "correo_google", unique=True),)


class Campana(Base):
    __tablename__ = "campanas"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=nuevo_id)
    usuario_id: Mapped[str] = mapped_column(ForeignKey("usuarios.id"), index=True, nullable=False)
    estado: Mapped[str] = mapped_column(
        String(30), default=EstadoCampana.BORRADOR, index=True, nullable=False
    )
    modo_consulta: Mapped[str] = mapped_column(String(12), default="demo", nullable=False)
    etapa: Mapped[str] = mapped_column(
        String(80), default="Preferencias guardadas", nullable=False
    )
    progreso: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    seleccion_guardada: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    plan_aplicado: Mapped[str] = mapped_column(String(12), nullable=False)
    limite_contactos: Mapped[int] = mapped_column(Integer, nullable=False)
    modalidad: Mapped[str] = mapped_column(String(12), nullable=False)
    departamento: Mapped[str] = mapped_column(String(80), nullable=False)
    ciudad: Mapped[str] = mapped_column(String(80), nullable=False)
    antiguedad_dias: Mapped[int] = mapped_column(Integer, nullable=False)
    permitir_recontacto: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=ahora_utc, nullable=False
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=ahora_utc, onupdate=ahora_utc, nullable=False
    )


class ContenidoTemporal(Base):
    __tablename__ = "contenidos_temporales"

    campana_id: Mapped[str] = mapped_column(ForeignKey("campanas.id"), primary_key=True)
    contenido_cifrado: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    vence_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=ahora_utc, nullable=False
    )


class AdjuntoTemporal(Base):
    __tablename__ = "adjuntos_temporales"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=nuevo_id)
    campana_id: Mapped[str] = mapped_column(
        ForeignKey("contenidos_temporales.campana_id"), index=True, nullable=False
    )
    metadatos_cifrados: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    tamano_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    contenido_cifrado: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)


class Destinatario(Base):
    __tablename__ = "destinatarios"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=nuevo_id)
    campana_id: Mapped[str] = mapped_column(ForeignKey("campanas.id"), index=True, nullable=False)
    nombre_empresa: Mapped[str] = mapped_column(String(180), nullable=False)
    correo: Mapped[str | None] = mapped_column(String(254))
    telefono_original: Mapped[str | None] = mapped_column(String(80))
    descripcion: Mapped[str | None] = mapped_column(Text)
    departamento: Mapped[str | None] = mapped_column(String(80))
    ciudad: Mapped[str | None] = mapped_column(String(80))
    dias_publicada: Mapped[int | None] = mapped_column(Integer)
    motivo: Mapped[str] = mapped_column(Text, nullable=False)
    puntuacion: Mapped[int | None] = mapped_column(Integer)
    estado: Mapped[str] = mapped_column(String(25), default="por_revisar", nullable=False)
    seleccionado: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (
        Index("ix_destinatarios_campana_correo", "campana_id", "correo", unique=True),
    )


class CorreoExcluido(Base):
    __tablename__ = "correos_excluidos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=nuevo_id)
    usuario_id: Mapped[str] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    correo: Mapped[str] = mapped_column(String(254), nullable=False)

    __table_args__ = (UniqueConstraint("usuario_id", "correo"),)


class HistorialEnvio(Base):
    __tablename__ = "historial_envios"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=nuevo_id)
    usuario_id: Mapped[str] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    campana_id: Mapped[str] = mapped_column(ForeignKey("campanas.id"), nullable=False)
    destinatario_id: Mapped[str | None] = mapped_column(ForeignKey("destinatarios.id"))
    correo: Mapped[str] = mapped_column(String(254), nullable=False)
    estado: Mapped[str] = mapped_column(String(20), default="enviado", nullable=False)
    mensaje_gmail_id: Mapped[str | None] = mapped_column(String(255))
    enviado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=ahora_utc, nullable=False
    )

    __table_args__ = (
        Index("ix_historial_usuario_correo_fecha", "usuario_id", "correo", "enviado_en"),
        Index("ix_historial_destinatario_id", "destinatario_id", unique=True),
    )


class ConexionGmail(Base):
    """Permiso de envío: el token se cifra antes de llegar a esta tabla."""

    __tablename__ = "conexiones_gmail"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=nuevo_id)
    usuario_id: Mapped[str] = mapped_column(ForeignKey("usuarios.id"), unique=True, nullable=False)
    correo_google: Mapped[str] = mapped_column(String(254), nullable=False)
    token_renovacion_cifrado: Mapped[str] = mapped_column(Text, nullable=False)
    permisos: Mapped[str] = mapped_column(String(500), nullable=False)
    conectado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=ahora_utc, nullable=False
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=ahora_utc, onupdate=ahora_utc, nullable=False
    )


class PagoPremium(Base):
    __tablename__ = "pagos_premium"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=nuevo_id)
    usuario_id: Mapped[str] = mapped_column(ForeignKey("usuarios.id"), index=True, nullable=False)
    estado: Mapped[str] = mapped_column(String(12), default=EstadoPago.PENDIENTE, nullable=False)
    referencia_comprobante: Mapped[str] = mapped_column(String(255), nullable=False)
    comprobante_cifrado: Mapped[bytes | None] = mapped_column(LargeBinary)
    comprobante_tipo: Mapped[str | None] = mapped_column(String(20))
    notificacion_estado: Mapped[str] = mapped_column(
        String(20), default="pendiente", nullable=False
    )
    verificado_por: Mapped[str | None] = mapped_column(ForeignKey("usuarios.id"))
    verificado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=ahora_utc, nullable=False
    )

    __table_args__ = (
        Index(
            "ix_pagos_pendiente_usuario_unico",
            "usuario_id",
            unique=True,
            postgresql_where=text("estado = 'pendiente'"),
            sqlite_where=text("estado = 'pendiente'"),
        ),
    )


class NavegadorSGVA(Base):
    __tablename__ = "navegador_sgva"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    habilitado: Mapped[bool] = mapped_column(default=True, nullable=False)
    campana_id: Mapped[str | None] = mapped_column(ForeignKey("campanas.id"))
    reserva_hasta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
