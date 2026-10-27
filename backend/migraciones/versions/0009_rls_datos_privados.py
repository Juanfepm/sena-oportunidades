"""Cierra el acceso directo a conexiones_gmail, omitido en su migración inicial."""

from alembic import op

revision = "0009_rls_datos_privados"
down_revision = "0008_premium_revision"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("ALTER TABLE conexiones_gmail ENABLE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL ON TABLE conexiones_gmail FROM PUBLIC")
    for rol in ("anon", "authenticated"):
        op.execute(
            "DO $debupa$ BEGIN "
            f"IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{rol}') THEN "
            f"EXECUTE 'REVOKE ALL ON TABLE conexiones_gmail FROM {rol}'; "
            "END IF; END $debupa$"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("ALTER TABLE conexiones_gmail DISABLE ROW LEVEL SECURITY")
