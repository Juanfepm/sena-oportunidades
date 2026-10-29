"""La migración inicial crea el esquema sin depender de una base remota."""

from io import StringIO
from pathlib import Path

from alembic import command
from alembic.config import Config
from pytest import MonkeyPatch
from sqlalchemy import create_engine, inspect, select

from backend.aplicacion.base_datos import Base
from backend.aplicacion.modelos import NavegadorSGVA


def test_migracion_inicial_coincide_con_modelos() -> None:
    ruta_configuracion = Path(__file__).resolve().parents[1] / "alembic.ini"
    configuracion = Config(str(ruta_configuracion))
    motor = create_engine("sqlite+pysqlite:///:memory:")
    try:
        with motor.begin() as conexion:
            configuracion.attributes["connection"] = conexion
            command.upgrade(configuracion, "head")
            assert set(inspect(conexion).get_table_names()) == {
                *Base.metadata.tables,
                "alembic_version",
            }
            assert conexion.execute(
                select(
                    NavegadorSGVA.id,
                    NavegadorSGVA.habilitado,
                    NavegadorSGVA.apagado_pendiente,
                ).order_by(NavegadorSGVA.id)
            ).all() == [(1, True, False), (2, False, False)]
            command.check(configuracion)
    finally:
        motor.dispose()


def test_migracion_genera_sql_postgresql_sin_conectarse(monkeypatch: MonkeyPatch) -> None:
    ruta_configuracion = Path(__file__).resolve().parents[1] / "alembic.ini"
    salida = StringIO()
    configuracion = Config(str(ruta_configuracion), output_buffer=salida)
    monkeypatch.setenv("DEBUPA_ENTORNO", "produccion")
    monkeypatch.setenv(
        "DEBUPA_BASE_DATOS",
        "postgresql+psycopg://usuario:clave-ficticia@ejemplo.invalid:5432/postgres?sslmode=require",
    )
    command.upgrade(configuracion, "head", sql=True)
    sentencia = salida.getvalue()
    assert "CREATE TABLE usuarios" in sentencia
    assert "CREATE TABLE navegador_sgva" in sentencia
    assert "INSERT INTO navegador_sgva" in sentencia
    assert "ALTER TABLE usuarios ENABLE ROW LEVEL SECURITY" in sentencia
    assert "ALTER TABLE contenidos_temporales ENABLE ROW LEVEL SECURITY" in sentencia
    assert "ALTER TABLE adjuntos_temporales ENABLE ROW LEVEL SECURITY" in sentencia
    assert "ALTER TABLE conexiones_gmail ENABLE ROW LEVEL SECURITY" in sentencia
    assert "REVOKE ALL ON TABLE usuarios FROM PUBLIC" in sentencia
    assert "clave-ficticia" not in sentencia
