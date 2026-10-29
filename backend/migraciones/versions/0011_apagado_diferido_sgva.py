"""Permite apagar el segundo navegador después de su consulta actual."""

import sqlalchemy as sa
from alembic import op

revision = "0011_apagado_diferido_sgva"
down_revision = "0010_segundo_navegador_sgva"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "navegador_sgva",
        sa.Column("apagado_pendiente", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("navegador_sgva", "apagado_pendiente")
