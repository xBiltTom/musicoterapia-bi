"""Resultados agregados por escenario y periodo, conservados en memoria."""

from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from threading import Lock
from time import monotonic

from fastapi import HTTPException


DashboardKey = tuple[str, date, date]
REFRESH_SECONDS = 300
RETRY_SECONDS = 10
MAX_PERIODS = 12


@dataclass(frozen=True)
class DashboardSnapshot:
    result: dict
    loaded_at: datetime
    refresh_at: float

    def response(self):
        return {**self.result, "consultado_utc": self.loaded_at,
                "datos_desactualizados": monotonic() >= self.refresh_at}


class DashboardCache:
    def __init__(self):
        self._entries: OrderedDict[DashboardKey, DashboardSnapshot] = OrderedDict()
        self._entries_lock = Lock()
        self._load_lock = Lock()
        self._retry_at = 0.0

    def size(self):
        with self._entries_lock:
            return len(self._entries)

    def _find(self, key):
        with self._entries_lock:
            snapshot = self._entries.get(key)
            if snapshot is not None:
                self._entries.move_to_end(key)
            return snapshot

    def _reload(self, key, read):
        try:
            result = read(*key)
        except HTTPException as exc:
            if exc.status_code == 503:
                self._retry_at = monotonic() + RETRY_SECONDS
            raise

        snapshot = DashboardSnapshot(result, datetime.now(timezone.utc), monotonic() + REFRESH_SECONDS)
        with self._entries_lock:
            self._entries[key] = snapshot
            self._entries.move_to_end(key)
            if len(self._entries) > MAX_PERIODS:
                self._entries.popitem(last=False)
        self._retry_at = 0.0
        return snapshot

    def get_or_load(self, key, read):
        snapshot = self._find(key)
        if snapshot is not None:
            return snapshot

        if not self._load_lock.acquire(timeout=8):
            snapshot = self._find(key)
            if snapshot is not None:
                return snapshot
            raise HTTPException(status_code=503, detail="Hay una consulta del tablero en curso. Inténtalo en unos segundos.")
        try:
            snapshot = self._find(key)
            if snapshot is not None:
                return snapshot
            if monotonic() < self._retry_at:
                raise HTTPException(status_code=503, detail="SQL Server no respondió. Inténtalo en unos segundos.")
            return self._reload(key, read)
        finally:
            self._load_lock.release()

    def needs_refresh(self, snapshot):
        return monotonic() >= max(snapshot.refresh_at, self._retry_at) and not self._load_lock.locked()

    def refresh(self, key, read):
        if not self._load_lock.acquire(blocking=False):
            return
        try:
            snapshot = self._find(key)
            if snapshot is None or monotonic() < max(snapshot.refresh_at, self._retry_at):
                return
            try:
                self._reload(key, read)
            except HTTPException as exc:
                if exc.status_code != 503:
                    with self._entries_lock:
                        self._entries.pop(key, None)
        finally:
            self._load_lock.release()


dashboard_cache = DashboardCache()
