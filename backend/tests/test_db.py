import unittest
from unittest.mock import Mock, patch

import pyodbc

from app import db


class ReadOnlyDatabaseTests(unittest.TestCase):
    def test_read_only_rejects_write_before_connecting(self):
        with patch.object(db, "READ_ONLY", True), patch.object(db.pyodbc, "connect") as connect:
            with self.assertRaises(db.ReadOnlyDatabaseError):
                with db.write_connection():
                    self.fail("Se abrió una conexión de escritura en modo de solo lectura")
            connect.assert_not_called()

    def test_final_database_is_protected_even_in_registration_mode(self):
        conn = Mock()
        cursor = conn.cursor.return_value
        cursor.execute.return_value.fetchval.return_value = db.PROTECTED_DATABASE.lower()

        with patch.object(db, "READ_ONLY", False), patch.object(db.pyodbc, "connect", return_value=conn):
            with self.assertRaises(db.ReadOnlyDatabaseError):
                with db.write_connection():
                    self.fail("La base final permitió abrir una conexión de escritura")

        cursor.execute.assert_called_once_with("SELECT DB_NAME()")
        conn.commit.assert_not_called()
        conn.close.assert_called_once()

    def test_read_connection_retries_transient_connection_failure(self):
        conn = Mock()
        failure = pyodbc.OperationalError("08001", "timeout")
        with patch.object(db.pyodbc, "connect", side_effect=[failure, conn]) as connect:
            with db.connection() as opened:
                self.assertIs(opened, conn)
            self.assertEqual(connect.call_count, 2)
            self.assertTrue(connect.call_args.kwargs["autocommit"])
        conn.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
