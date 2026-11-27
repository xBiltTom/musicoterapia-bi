import unittest
from contextlib import nullcontext
from datetime import date
from decimal import Decimal
from unittest.mock import Mock, patch

from app import indicadores, queries


class DimensionalDashboardTests(unittest.TestCase):
    def test_response_uses_distinct_bases_for_experience_and_latency(self):
        monthly = [{"mes": "2024-01", "positivas": 3, "neutras": 1, "negativas": 1,
                    "minutos_respuesta": Decimal("8.5"), "con_respuesta": 2,
                    "respuestas_observadas": 3, "sin_respuesta": 2}]
        result = indicadores.response_metrics(monthly)
        self.assertEqual(result["k1"]["tasa_positiva"], 60)
        self.assertEqual(result["k1"]["participaciones_validas"], 5)
        self.assertEqual(result["k1"]["estado"], "ambar")
        self.assertEqual(result["k6"]["tiempo_promedio_minutos"], 4.25)
        self.assertEqual(result["k6"]["tasa_sin_respuesta"], 40)
        self.assertEqual(result["k6"]["estado"], "ambar")

    def test_scope_is_passed_to_the_datamart_and_excludes_other_reports(self):
        start, end = date(2024, 1, 1), date(2024, 1, 31)
        conn = Mock()
        with patch.object(indicadores, "datamart_connection", return_value=nullcontext(conn)), \
                patch.object(indicadores, "fetch_all", return_value=[]) as fetch, \
                patch.object(indicadores, "fetch_one") as other:
            dashboard = indicadores.read_dashboard("HIBRIDO", start, end, "incluidos", ("RP01",), 42)
        fetch.assert_called_once_with(conn, queries.MONTHLY_RESPONSE, ("HIBRIDO", True, start, end, 42, 42))
        other.assert_not_called()
        self.assertEqual(dashboard["filtros"]["alcance"], "propios")
        self.assertEqual(dashboard["k1"]["estado"], "sin_datos")
        self.assertIsNone(dashboard["k1"]["tasa_positiva"])
        self.assertNotIn("k2", dashboard)

    def test_adherence_includes_full_iso_weeks_overlapping_the_range(self):
        conn = Mock()
        with patch.object(indicadores, "fetch_one", return_value={"cumplen": 2, "paciente_semanas": 4}) as fetch:
            result = indicadores.read_adherence(conn, "HIBRIDO", "todos", date(2024, 1, 3), date(2024, 1, 10))
        fetch.assert_called_once_with(conn, queries.ADHERENCE, ("HIBRIDO", False, date(2024, 1, 1), date(2024, 1, 8)))
        self.assertEqual(result["tasa_adherencia"], 50)
        self.assertEqual(result["estado"], "rojo")

    def test_semaphore_uses_unrounded_value_and_correct_direction(self):
        self.assertEqual(indicadores.status("k1", Decimal("69.999")), "ambar")
        self.assertEqual(indicadores.status("k6", Decimal("3")), "verde")
        self.assertEqual(indicadores.status("k6", Decimal("5.001")), "rojo")
        self.assertEqual(indicadores.status("k7", None), "sin_datos")
