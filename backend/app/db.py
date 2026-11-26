"""Acceso de solo lectura a la base transaccional de SQL Server."""

import os
from contextlib import contextmanager
from pathlib import Path

import pyodbc
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

DEFAULT_CONNECTION = (
    "DRIVER={ODBC Driver 18 for SQL Server};"
    "SERVER=localhost;DATABASE=BD_Musicoterapia_Alzheimer;"
    "Trusted_Connection=yes;Encrypt=yes;TrustServerCertificate=yes"
)


@contextmanager
def connection():
    conn = pyodbc.connect(
        os.getenv("SQLSERVER_CONNECTION_STRING", DEFAULT_CONNECTION),
        timeout=8,
        autocommit=True,
    )
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def write_connection():
    """Transaccion explicita para el registro FR04."""
    conn = pyodbc.connect(
        os.getenv("SQLSERVER_CONNECTION_STRING", DEFAULT_CONNECTION),
        timeout=8,
        autocommit=False,
    )
    try:
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
