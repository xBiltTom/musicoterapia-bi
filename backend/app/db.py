"""Conexiones transaccional y dimensional de SQL Server."""

import logging
import os
from contextlib import closing, contextmanager
from pathlib import Path
from urllib.parse import unquote, urlsplit

from dotenv import load_dotenv

try:
    import pyodbc
except ImportError:
    pyodbc = None


ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
AZURE_OLTP = "AZURE_SQL_OLTP_URL"
AZURE_DATAMART = "AZURE_SQL_DATAMART_URL"
USE_AZURE = os.getenv("VERCEL") == "1" or bool(os.getenv(AZURE_OLTP))
READ_ONLY = USE_AZURE or os.getenv("APP_SOLO_LECTURA", "true").strip().lower() != "false"
PROTECTED_DATABASE = "BD_Musicoterapia_Alzheimer"
TRANSACTIONAL_DATABASE = "BD_Musicoterapia_Alzheimer_20261127"
DATAMART_DATABASE = "Datamart_Musicoterapia_Alzheimer"
PROTECTED_DATABASES = {name.casefold() for name in (PROTECTED_DATABASE, TRANSACTIONAL_DATABASE, DATAMART_DATABASE)}
TRANSIENT_SQL_STATES = {"08001", "08003", "08S01", "HYT00", "HYT01"}
logger = logging.getLogger(__name__)

def local_connection_string(database):
    return (
        "DRIVER={ODBC Driver 17 for SQL Server};"
        f"SERVER=tcp:127.0.0.1,1433;DATABASE={database};"
        "Trusted_Connection=yes;Encrypt=yes;TrustServerCertificate=yes"
    )


DEFAULT_CONNECTION = local_connection_string(TRANSACTIONAL_DATABASE)
DEFAULT_DATAMART_CONNECTION = local_connection_string(DATAMART_DATABASE)


class ReadOnlyDatabaseError(PermissionError):
    pass


class DatabaseConnectionError(RuntimeError):
    pass


DB_ERRORS = (DatabaseConnectionError,)
if pyodbc is not None:
    DB_ERRORS += (pyodbc.Error,)
if USE_AZURE:
    import pytds

    DB_ERRORS += (pytds.Error, OSError)


def sqlstate(error):
    if isinstance(error, TimeoutError):
        return "HYT00"
    if isinstance(error, OSError):
        return "08001"
    state = error.args[0] if error.args else None
    return state if isinstance(state, str) and len(state) == 5 and state.isalnum() else "desconocido"


def connect_azure(variable, *, autocommit, query_timeout):
    import certifi

    try:
        url = urlsplit(os.getenv(variable, ""))
        port = url.port or 1433
    except ValueError:
        raise DatabaseConnectionError("08001") from None
    database = unquote(url.path.removeprefix("/"))
    if url.scheme != "mssql" or not all((url.hostname, url.username, url.password, database)) or url.query or url.fragment:
        raise DatabaseConnectionError("08001")
    return pytds.connect(
        server=url.hostname, port=port, database=database,
        user=unquote(url.username), password=unquote(url.password),
        cafile=certifi.where(), validate_host=True,
        login_timeout=5, timeout=query_timeout, autocommit=autocommit,
    )


def open_read_connection(connection_string=None, *, query_timeout=30, azure_variable=AZURE_OLTP):
    if connection_string is None:
        connection_string = os.getenv("SQLSERVER_CONNECTION_STRING", DEFAULT_CONNECTION)
    for attempt in range(2):
        try:
            if USE_AZURE:
                return connect_azure(azure_variable, autocommit=True, query_timeout=query_timeout)
            if pyodbc is None:
                raise DatabaseConnectionError("08001")
            return pyodbc.connect(connection_string, timeout=4, autocommit=True)
        except DatabaseConnectionError:
            raise
        except DB_ERRORS as exc:
            state = sqlstate(exc)
            if attempt == 0 and state in TRANSIENT_SQL_STATES:
                continue
            logger.warning("No se pudo abrir una conexión de lectura a SQL Server (SQLSTATE %s)", state)
            raise DatabaseConnectionError(state) from exc


@contextmanager
def connection(connection_string=None, *, query_timeout=30, azure_variable=AZURE_OLTP):
    conn = open_read_connection(connection_string, query_timeout=query_timeout, azure_variable=azure_variable)
    try:
        if not USE_AZURE:
            conn.timeout = query_timeout
        yield conn
    finally:
        conn.close()


def datamart_connection():
    return connection(os.getenv("SQLSERVER_DATAMART_CONNECTION_STRING", DEFAULT_DATAMART_CONNECTION),
                      azure_variable=AZURE_DATAMART)


@contextmanager
def transaction(conn):
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
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
    with transaction(conn):
        with closing(conn.cursor()) as cursor:
            database = cursor.execute("SELECT DB_NAME()").fetchval()
        if database.casefold() in PROTECTED_DATABASES:
            raise ReadOnlyDatabaseError("La base final solo admite consultas desde la aplicación")
        yield conn


def session_write_connection():
    if USE_AZURE:
        return transaction(connect_azure(AZURE_OLTP, autocommit=False, query_timeout=8))
    return write_connection()


def execute_query(cursor, sql, params=()):
    if USE_AZURE:
        if params:
            sql = sql.replace("%", "%%").replace("?", "%s")
        cursor.execute(sql, params or None)
    else:
        cursor.execute(sql, *params)


def fetch_one(conn, sql: str, params=()):
    cursor = conn.cursor()
    try:
        execute_query(cursor, sql, params)
        names = [column[0] for column in cursor.description]
        row = cursor.fetchone()
        return dict(zip(names, row)) if row else None
    finally:
        cursor.close()


def fetch_all(conn, sql: str, params=()):
    cursor = conn.cursor()
    try:
        execute_query(cursor, sql, params)
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
