"""Cifra el contenido de campañas y adjuntos durante 24 horas."""

import sqlalchemy as sa
from alembic import op

revision = "0004_contenido_temporal"
down_revision = "0003_conexion_gmail_cifrada"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contenidos_temporales",
        sa.Column(
            "campana_id", sa.String(length=36), sa.ForeignKey("campanas.id"), primary_key=True
        ),
        sa.Column("contenido_cifrado", sa.LargeBinary(), nullable=False),
        sa.Column("vence_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_contenidos_temporales_vence_en", "contenidos_temporales", ["vence_en"])
    op.create_table(
        "adjuntos_temporales",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "campana_id",
            sa.String(length=36),
            sa.ForeignKey("contenidos_temporales.campana_id"),
            nullable=False,
        ),
        sa.Column("metadatos_cifrados", sa.LargeBinary(), nullable=False),
        sa.Column("tamano_bytes", sa.Integer(), nullable=False),
        sa.Column("contenido_cifrado", sa.LargeBinary(), nullable=False),
    )
    op.create_index("ix_adjuntos_temporales_campana_id", "adjuntos_temporales", ["campana_id"])
    if op.get_bind().dialect.name == "postgresql":
        for tabla in ("contenidos_temporales", "adjuntos_temporales"):
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
    op.drop_index("ix_adjuntos_temporales_campana_id", table_name="adjuntos_temporales")
    op.drop_table("adjuntos_temporales")
    op.drop_index("ix_contenidos_temporales_vence_en", table_name="contenidos_temporales")
    op.drop_table("contenidos_temporales")
