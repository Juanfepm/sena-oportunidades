"""Conserva ofertas reales sin atribuirles una puntuación de IA."""

from alembic import op
import sqlalchemy as sa


revision = "0005_consulta_sgva"
down_revision = "0004_contenido_temporal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("campanas", sa.Column("modo_consulta", sa.String(12), server_default="demo", nullable=False))
    with op.batch_alter_table("destinatarios") as lote:
        for nombre, tipo in (
            ("descripcion", sa.Text()),
            ("departamento", sa.String(80)),
            ("ciudad", sa.String(80)),
            ("dias_publicada", sa.Integer()),
        ):
            lote.add_column(sa.Column(nombre, tipo, nullable=True))
        lote.alter_column("correo", existing_type=sa.String(254), nullable=True)
        lote.alter_column("puntuacion", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    op.execute("DELETE FROM destinatarios WHERE estado = 'pendiente_ia'")
    with op.batch_alter_table("destinatarios") as lote:
        lote.alter_column("puntuacion", existing_type=sa.Integer(), nullable=False)
        lote.alter_column("correo", existing_type=sa.String(254), nullable=False)
        for nombre in ("dias_publicada", "ciudad", "departamento", "descripcion"):
            lote.drop_column(nombre)
    op.drop_column("campanas", "modo_consulta")
