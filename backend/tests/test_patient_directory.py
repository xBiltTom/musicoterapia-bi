import unittest
from contextlib import nullcontext
from unittest.mock import Mock, patch

import pyodbc

from app import patient_directory as directory


class PatientDirectoryTests(unittest.TestCase):
    def test_loads_once_and_filters_codes_within_the_selected_scenario(self):
        store = directory.PatientDirectory()
        rows = [
            {"escenario": "HIBRIDO", "codigo_paciente": "H-002", "id_paciente": 2},
            {"escenario": "HIBRIDO", "codigo_paciente": "h-001", "id_paciente": 1},
            {"escenario": "SINTETICO_IA", "codigo_paciente": "H-003", "id_paciente": 3},
        ]
        with patch.object(directory, "connection", side_effect=lambda **_: nullcontext(Mock())), \
                patch.object(directory, "fetch_all", return_value=rows) as read:
            result = store.get()
            self.assertEqual([row["id_paciente"] for row in result.matching("HIBRIDO", "h-")], [1, 2])
            self.assertEqual(result.matching("HIBRIDO", "%"), [])
            self.assertIs(store.get(), result)
            read.assert_called_once()

    def test_retains_last_snapshot_and_limits_refresh_after_sql_timeout(self):
        store = directory.PatientDirectory()
        initial = [{"escenario": "HIBRIDO", "codigo_paciente": "H-001", "id_paciente": 1}]
        conn = Mock()
        with patch.object(directory, "monotonic", return_value=1), \
                patch.object(directory, "connection", return_value=nullcontext(conn)), \
                patch.object(directory, "fetch_all", return_value=initial):
            original = store.get()

        with patch.object(directory, "monotonic", return_value=302), \
                patch.object(directory, "connection", side_effect=pyodbc.OperationalError("HYT00", "timeout")) as read, \
                self.assertLogs(directory.logger, level="WARNING"):
            self.assertTrue(store.needs_refresh())
            store.refresh()
            self.assertIs(store.get(), original)
            self.assertFalse(store.needs_refresh())
            store.refresh()
            read.assert_called_once()
