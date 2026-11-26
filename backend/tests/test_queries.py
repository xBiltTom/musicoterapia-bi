import unittest
from datetime import date, datetime
from unittest.mock import Mock

from app.queries import monthly_experience, summarize_scores


class MonthlyExperienceTests(unittest.TestCase):
    def test_counts_only_selected_patients_and_sessions_in_the_period(self):
        conn = Mock()
        cursor = conn.cursor.return_value
        cursor.fetchall.return_value = [(10, "2024-02"), (20, "2024-01")]
        cursor.fetchmany.side_effect = [
            [(10, 1, "Positiva"), (10, 2, "NEGATIVA"), (20, 1, "NEUTRA"),
             (10, 3, "POSITIVA"), (30, 1, "POSITIVA")],
            [],
        ]

        monthly = monthly_experience(conn, {1, 2}, date(2024, 1, 1), date(2024, 2, 29))

        self.assertEqual(monthly, [
            {"mes": "2024-01", "positivas": 0, "neutras": 1, "negativas": 0, "participaciones_validas": 1},
            {"mes": "2024-02", "positivas": 1, "neutras": 0, "negativas": 1, "participaciones_validas": 2},
        ])
        cursor.close.assert_called_once()


class PairedScoresTests(unittest.TestCase):
    def test_follows_chronology_and_counts_crossings_only_with_valid_baseline(self):
        early = datetime(2024, 1, 1)
        late = datetime(2024, 4, 1)
        initial = {1: ((early, 10, 1), 17), 2: ((early, 20, 2), 9), 3: ((late, 30, 3), 20)}
        followup = {1: ((late, 11, -4), 10), 2: ((late, 21, -5), 4), 3: ((late, 31, -6), 10)}

        summary = summarize_scores(initial, followup)

        self.assertEqual(summary, {"pacientes_con_par": 2, "reduccion_promedio": 6.0,
                                   "respondedores": 1, "basales_sobre_corte": 1, "cruces_corte": 1})
