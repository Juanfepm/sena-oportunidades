"""Comprobantes privados cifrados y vigencia del plan premium."""

import sqlalchemy as sa
from alembic import op

revision = "0008_premium_revision"
down_revision = "0007_envios_confirmados"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "usuarios", sa.Column("premium_hasta", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "pagos_premium", sa.Column("comprobante_cifrado", sa.LargeBinary(), nullable=True)
    )
    op.add_column("pagos_premium", sa.Column("comprobante_tipo", sa.String(20), nullable=True))
    op.add_column(
        "pagos_premium",
        sa.Column(
            "notificacion_estado", sa.String(20), nullable=False, server_default="pendiente"
        ),
    )
    op.create_index(
        "ix_pagos_pendiente_usuario_unico",
        "pagos_premium",
        ["usuario_id"],
        unique=True,
        postgresql_where=sa.text("estado = 'pendiente'"),
        sqlite_where=sa.text("estado = 'pendiente'"),
    )


def downgrade() -> None:
    op.drop_index("ix_pagos_pendiente_usuario_unico", table_name="pagos_premium")
    op.drop_column("pagos_premium", "notificacion_estado")
    op.drop_column("pagos_premium", "comprobante_tipo")
    op.drop_column("pagos_premium", "comprobante_cifrado")
    op.drop_column("usuarios", "premium_hasta")
