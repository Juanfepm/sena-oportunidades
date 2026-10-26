"""Registra cada intento antes de llamar a Gmail para evitar duplicados."""

import sqlalchemy as sa
from alembic import op

revision = "0007_envios_confirmados"
down_revision = "0006_seleccion_revision"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("historial_envios") as tabla:
        tabla.add_column(sa.Column("destinatario_id", sa.String(36), nullable=True))
        tabla.add_column(
            sa.Column("estado", sa.String(20), nullable=False, server_default="enviado")
        )
        tabla.add_column(sa.Column("mensaje_gmail_id", sa.String(255), nullable=True))
        tabla.create_foreign_key(
            "fk_historial_destinatario", "destinatarios", ["destinatario_id"], ["id"]
        )
        tabla.create_index("ix_historial_destinatario_id", ["destinatario_id"], unique=True)


def downgrade() -> None:
    with op.batch_alter_table("historial_envios") as tabla:
        tabla.drop_index("ix_historial_destinatario_id")
        tabla.drop_constraint("fk_historial_destinatario", type_="foreignkey")
        tabla.drop_column("mensaje_gmail_id")
        tabla.drop_column("estado")
        tabla.drop_column("destinatario_id")
