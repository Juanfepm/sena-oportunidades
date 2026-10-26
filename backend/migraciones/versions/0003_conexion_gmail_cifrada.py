"""Guarda de forma cifrada el permiso de envío de Gmail."""

import sqlalchemy as sa
from alembic import op

revision = "0003_conexion_gmail_cifrada"
down_revision = "0002_identidad_google"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conexiones_gmail",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("usuario_id", sa.String(length=36), nullable=False),
        sa.Column("correo_google", sa.String(length=254), nullable=False),
        sa.Column("token_renovacion_cifrado", sa.Text(), nullable=False),
        sa.Column("permisos", sa.String(length=500), nullable=False),
        sa.Column("conectado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("usuario_id"),
    )


def downgrade() -> None:
    op.drop_table("conexiones_gmail")
