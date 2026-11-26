"""Acceso a la base transaccional de SQL Server."""

import logging
import os
from contextlib import closing, contextmanager
from pathlib import Path

import pyodbc
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
READ_ONLY = os.getenv("APP_SOLO_LECTURA", "true").strip().lower() != "false"
PROTECTED_DATABASE = "BD_Musicoterapia_Alzheimer"
TRANSIENT_SQL_STATES = {"08001", "08003", "08S01", "HYT00", "HYT01"}
logger = logging.getLogger(__name__)

DEFAULT_CONNECTION = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    f"SERVER=tcp:127.0.0.1,1433;DATABASE={PROTECTED_DATABASE};"
    "Trusted_Connection=yes;Encrypt=yes;TrustServerCertificate=yes"
)


class ReadOnlyDatabaseError(PermissionError):
    pass


class DatabaseConnectionError(pyodbc.OperationalError):
    pass


def sqlstate(error):
    return error.args[0] if error.args else "desconocido"


def open_read_connection():
    for attempt in range(2):
        try:
            return pyodbc.connect(
                os.getenv("SQLSERVER_CONNECTION_STRING", DEFAULT_CONNECTION), timeout=4, autocommit=True,
            )
        except pyodbc.Error as exc:
            state = sqlstate(exc)
            if attempt == 0 and state in TRANSIENT_SQL_STATES:
                continue
            logger.warning("No se pudo abrir una conexión de lectura a SQL Server (SQLSTATE %s)", state)
            raise DatabaseConnectionError(*exc.args) from exc


@contextmanager
def connection():
    conn = open_read_connection()
    try:
        conn.timeout = 30
        yield conn
    finally:
        conn.close()


@contextmanager
def write_connection():
    """Abre una transacción que confirma el registro completo o lo revierte."""
    if READ_ONLY:
        raise ReadOnlyDatabaseError("La aplicación está en modo de solo lectura")
    conn = pyodbc.connect(
        os.getenv("SQLSERVER_CONNECTION_STRING", DEFAULT_CONNECTION),
        timeout=8,
        autocommit=False,
    )
    try:
        with closing(conn.cursor()) as cursor:
            database = cursor.execute("SELECT DB_NAME()").fetchval()
        if database.casefold() == PROTECTED_DATABASE.casefold():
            raise ReadOnlyDatabaseError("La base final solo admite consultas desde la aplicación")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def fetch_one(conn, sql: str, params=()):
    cursor = conn.cursor()
    try:
        cursor.execute(sql, *params)
        names = [column[0] for column in cursor.description]
        row = cursor.fetchone()
        return dict(zip(names, row)) if row else None
    finally:
        cursor.close()


def fetch_all(conn, sql: str, params=()):
    cursor = conn.cursor()
    try:
        cursor.execute(sql, *params)
        names = [column[0] for column in cursor.description]
        return [dict(zip(names, row)) for row in cursor.fetchall()]
    finally:
        cursor.close()


def has_table(conn, table: str) -> bool:
    return fetch_one(conn, "SELECT OBJECT_ID(?, N'U') AS id", (table,))["id"] is not None


def has_column(conn, table: str, column: str) -> bool:
    return fetch_one(conn, "SELECT COL_LENGTH(?, ?) AS longitud", (table, column))["longitud"] is not None


def table_columns(conn, table: str) -> set[str]:
    return {row["name"] for row in fetch_all(conn, "SELECT name FROM sys.columns WHERE object_id = OBJECT_ID(?, N'U')", (table,))}
