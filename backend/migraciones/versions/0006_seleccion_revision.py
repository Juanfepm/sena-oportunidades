"""Conserva la selección humana para una futura confirmación de envío."""

from alembic import op
import sqlalchemy as sa


revision = "0006_seleccion_revision"
down_revision = "0005_consulta_sgva"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("campanas", sa.Column("seleccion_guardada", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("destinatarios", sa.Column("seleccionado", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("destinatarios", "seleccionado")
    op.drop_column("campanas", "seleccion_guardada")
