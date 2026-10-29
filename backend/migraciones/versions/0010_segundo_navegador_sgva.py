"""Prepara un segundo navegador SGVA, desactivado por defecto."""

import sqlalchemy as sa
from alembic import op

revision = "0010_segundo_navegador_sgva"
down_revision = "0009_rls_datos_privados"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "navegador_sgva",
        sa.Column("habilitado", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.bulk_insert(
        sa.table(
            "navegador_sgva",
            sa.column("id", sa.Integer()),
            sa.column("habilitado", sa.Boolean()),
        ),
        [{"id": 2, "habilitado": False}],
    )


def downgrade() -> None:
    op.execute("DELETE FROM navegador_sgva WHERE id = 2")
    op.drop_column("navegador_sgva", "habilitado")
