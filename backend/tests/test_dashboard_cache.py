import unittest
from datetime import date
from unittest.mock import Mock, patch

from fastapi import HTTPException

from app import dashboard_cache as cache


HIBRIDO = ("HIBRIDO", date(2022, 1, 1), date(2024, 12, 31))
SINTETICO = ("SINTETICO_IA", *HIBRIDO[1:])


class DashboardCacheTests(unittest.TestCase):
    def test_reuses_fresh_results_only_for_the_same_filter(self):
        store = cache.DashboardCache()
        read = Mock(side_effect=lambda scenario, *_: {"escenario": scenario})
        first = store.get_or_load(HIBRIDO, read)
        self.assertIs(store.get_or_load(HIBRIDO, read), first)
        self.assertFalse(first.response()["datos_desactualizados"])
        read.assert_called_once_with(*HIBRIDO)

        other = store.get_or_load(SINTETICO, read)
        self.assertEqual(other.response()["escenario"], "SINTETICO_IA")
        self.assertEqual(store.size(), 2)

    def test_serves_previous_result_after_timeout_and_refreshes_after_recovery(self):
        store = cache.DashboardCache()
        read = Mock(return_value={"k1": 36.81})
        with patch.object(cache, "monotonic", return_value=1):
            original = store.get_or_load(HIBRIDO, read)

        expired_at = 1 + cache.REFRESH_SECONDS
        failed = Mock(side_effect=HTTPException(status_code=503, detail="SQL Server no respondió"))
        with patch.object(cache, "monotonic", return_value=expired_at):
            self.assertTrue(store.needs_refresh(original))
            store.refresh(HIBRIDO, failed)
            fallback = store.get_or_load(HIBRIDO, failed).response()
            self.assertTrue(fallback["datos_desactualizados"])
            self.assertEqual(fallback["k1"], 36.81)
            self.assertEqual(fallback["consultado_utc"], original.loaded_at)
            self.assertFalse(store.needs_refresh(original))
            store.refresh(HIBRIDO, failed)
            with self.assertRaises(HTTPException) as error:
                store.get_or_load(SINTETICO, failed)
            self.assertEqual(error.exception.status_code, 503)
            failed.assert_called_once_with(*HIBRIDO)

        updated = Mock(return_value={"k1": 37.21})
        with patch.object(cache, "monotonic", return_value=expired_at + cache.RETRY_SECONDS):
            self.assertTrue(store.needs_refresh(original))
            store.refresh(HIBRIDO, updated)
            result = store.get_or_load(HIBRIDO, updated).response()
            self.assertFalse(result["datos_desactualizados"])
            self.assertEqual(result["k1"], 37.21)
            updated.assert_called_once_with(*HIBRIDO)
