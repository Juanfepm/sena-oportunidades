"""Crea las tablas iniciales y reserva el único navegador SGVA."""

import sqlalchemy as sa
from alembic import op

revision = "0001_esquema_inicial"
down_revision = None
branch_labels = None
depends_on = None

TABLAS_PRIVADAS = (
    "usuarios",
    "campanas",
    "correos_excluidos",
    "destinatarios",
    "historial_envios",
    "pagos_premium",
    "navegador_sgva",
    "alembic_version",
)


def upgrade() -> None:
    op.create_table(
        "usuarios",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("identificador_externo", sa.String(255), nullable=False),
        sa.Column("plan", sa.String(12), nullable=False),
        sa.Column("es_administrador", sa.Boolean(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("identificador_externo"),
    )
    op.create_table(
        "campanas",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("usuario_id", sa.String(36), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("estado", sa.String(30), nullable=False),
        sa.Column("etapa", sa.String(80), nullable=False),
        sa.Column("progreso", sa.Integer(), nullable=False),
        sa.Column("plan_aplicado", sa.String(12), nullable=False),
        sa.Column("limite_contactos", sa.Integer(), nullable=False),
        sa.Column("modalidad", sa.String(12), nullable=False),
        sa.Column("departamento", sa.String(80), nullable=False),
        sa.Column("ciudad", sa.String(80), nullable=False),
        sa.Column("antiguedad_dias", sa.Integer(), nullable=False),
        sa.Column("permitir_recontacto", sa.Boolean(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_campanas_estado", "campanas", ["estado"])
    op.create_index("ix_campanas_usuario_id", "campanas", ["usuario_id"])
    op.create_table(
        "correos_excluidos",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("usuario_id", sa.String(36), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("correo", sa.String(254), nullable=False),
        sa.UniqueConstraint("usuario_id", "correo"),
    )
    op.create_table(
        "destinatarios",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("campana_id", sa.String(36), sa.ForeignKey("campanas.id"), nullable=False),
        sa.Column("nombre_empresa", sa.String(180), nullable=False),
        sa.Column("correo", sa.String(254), nullable=False),
        sa.Column("telefono_original", sa.String(80), nullable=True),
        sa.Column("motivo", sa.Text(), nullable=False),
        sa.Column("puntuacion", sa.Integer(), nullable=False),
        sa.Column("estado", sa.String(25), nullable=False),
    )
    op.create_index("ix_destinatarios_campana_id", "destinatarios", ["campana_id"])
    op.create_index(
        "ix_destinatarios_campana_correo", "destinatarios", ["campana_id", "correo"], unique=True
    )
    op.create_table(
        "historial_envios",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("usuario_id", sa.String(36), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("campana_id", sa.String(36), sa.ForeignKey("campanas.id"), nullable=False),
        sa.Column("correo", sa.String(254), nullable=False),
        sa.Column("enviado_en", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_historial_usuario_correo_fecha",
        "historial_envios",
        ["usuario_id", "correo", "enviado_en"],
    )
    op.create_table(
        "pagos_premium",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("usuario_id", sa.String(36), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("estado", sa.String(12), nullable=False),
        sa.Column("referencia_comprobante", sa.String(255), nullable=False),
        sa.Column("verificado_por", sa.String(36), sa.ForeignKey("usuarios.id"), nullable=True),
        sa.Column("verificado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_pagos_premium_usuario_id", "pagos_premium", ["usuario_id"])
    op.create_table(
        "navegador_sgva",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("campana_id", sa.String(36), sa.ForeignKey("campanas.id"), nullable=True),
        sa.Column("reserva_hasta", sa.DateTime(timezone=True), nullable=True),
    )
    op.bulk_insert(sa.table("navegador_sgva", sa.column("id", sa.Integer())), [{"id": 1}])
    if op.get_bind().dialect.name == "postgresql":
        for tabla in TABLAS_PRIVADAS:
            op.execute(f"ALTER TABLE {tabla} ENABLE ROW LEVEL SECURITY")
            op.execute(f"REVOKE ALL ON TABLE {tabla} FROM PUBLIC")
            for rol in ("anon", "authenticated"):
                op.execute(
                    f"DO $debupa$ BEGIN "
                    f"IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{rol}') THEN "
                    f"EXECUTE 'REVOKE ALL ON TABLE {tabla} FROM {rol}'; "
                    f"END IF; END $debupa$"
                )


def downgrade() -> None:
    op.drop_table("navegador_sgva")
    op.drop_index("ix_pagos_premium_usuario_id", table_name="pagos_premium")
    op.drop_table("pagos_premium")
    op.drop_index("ix_historial_usuario_correo_fecha", table_name="historial_envios")
    op.drop_table("historial_envios")
    op.drop_index("ix_destinatarios_campana_correo", table_name="destinatarios")
    op.drop_index("ix_destinatarios_campana_id", table_name="destinatarios")
    op.drop_table("destinatarios")
    op.drop_table("correos_excluidos")
    op.drop_index("ix_campanas_usuario_id", table_name="campanas")
    op.drop_index("ix_campanas_estado", table_name="campanas")
    op.drop_table("campanas")
    op.drop_table("usuarios")
