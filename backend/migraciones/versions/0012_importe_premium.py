"""Conserva el precio ofrecido en cada solicitud Premium."""

import sqlalchemy as sa
from alembic import op

revision = "0012_importe_premium"
down_revision = "0011_apagado_diferido_sgva"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pagos_premium",
        sa.Column("importe_cop", sa.Integer(), server_default="8000", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("pagos_premium", "importe_cop")
