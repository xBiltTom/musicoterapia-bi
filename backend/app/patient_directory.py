"""Directorio de pacientes de solo lectura con una copia temporal en memoria."""

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from time import monotonic

import pyodbc

from .db import connection, fetch_all, sqlstate


PATIENT_FIELDS = "id_paciente, codigo_paciente, escenario, sexo, fecha_ingreso_programa, fecha_salida_programa"
REFRESH_SECONDS = 300
RETRY_SECONDS = 30
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DirectorySnapshot:
    patients: dict[str, tuple[dict, ...]]
    loaded_at: datetime
    refresh_at: float

    def matching(self, scenario, prefix):
        rows = self.patients.get(scenario, ())
        if not prefix:
            return rows
        prefix = prefix.casefold()
        return [row for row in rows if row["codigo_paciente"].casefold().startswith(prefix)]


class PatientDirectory:
    def __init__(self):
        self.snapshot: DirectorySnapshot | None = None
        self.retry_at = 0.0
        self._refresh_lock = Lock()

    def get(self) -> DirectorySnapshot | None:
        if self.snapshot is None:
            with self._refresh_lock:
                if self.snapshot is None and monotonic() >= self.retry_at:
                    self._reload()
        return self.snapshot

    def needs_refresh(self) -> bool:
        snapshot = self.snapshot
        return bool(snapshot and monotonic() >= max(snapshot.refresh_at, self.retry_at) and not self._refresh_lock.locked())

    def refresh(self):
        if not self._refresh_lock.acquire(blocking=False):
            return
        try:
            snapshot = self.snapshot
            if snapshot and monotonic() >= max(snapshot.refresh_at, self.retry_at):
                self._reload()
        finally:
            self._refresh_lock.release()

    def _reload(self):
        try:
            with connection() as conn:
                conn.timeout = 20
                rows = fetch_all(conn, f"SELECT {PATIENT_FIELDS} FROM dbo.paciente")
        except pyodbc.Error as exc:
            self.retry_at = monotonic() + RETRY_SECONDS
            logger.warning("No se pudo actualizar el directorio de pacientes (SQLSTATE %s)", sqlstate(exc))
            return

        grouped = defaultdict(list)
        for row in rows:
            grouped[row["escenario"]].append(row)

        self.snapshot = DirectorySnapshot(
            patients={scenario: tuple(sorted(items, key=lambda row: (row["codigo_paciente"].casefold(), row["id_paciente"])))
                      for scenario, items in grouped.items()},
            loaded_at=datetime.now(timezone.utc),
            refresh_at=monotonic() + REFRESH_SECONDS,
        )
        self.retry_at = 0.0


patient_directory = PatientDirectory()
