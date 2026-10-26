"""Agrega los datos mínimos de identidad de Google, sin tokens."""

import sqlalchemy as sa
from alembic import op

revision = "0002_identidad_google"
down_revision = "0001_esquema_inicial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("usuarios", sa.Column("correo_google", sa.String(length=254), nullable=True))
    op.add_column("usuarios", sa.Column("nombre_google", sa.String(length=180), nullable=True))
    op.add_column(
        "usuarios",
        sa.Column(
            "ultimo_acceso_en",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("ix_usuarios_correo_google_unico", "usuarios", ["correo_google"], unique=True)
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("usuarios", recreate="always") as batch:
            batch.alter_column("ultimo_acceso_en", nullable=False, server_default=None)
    else:
        op.alter_column("usuarios", "ultimo_acceso_en", nullable=False, server_default=None)


def downgrade() -> None:
    op.drop_index("ix_usuarios_correo_google_unico", table_name="usuarios")
    op.drop_column("usuarios", "ultimo_acceso_en")
    op.drop_column("usuarios", "nombre_google")
    op.drop_column("usuarios", "correo_google")
