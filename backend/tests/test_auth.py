import unittest
from contextlib import nullcontext
from unittest.mock import Mock, patch

import pyodbc
from fastapi import HTTPException

from app import auth


class MemorySessionTests(unittest.TestCase):
    def test_reuses_recent_profile_when_moving_between_pages(self):
        profile = Mock()
        session = auth.MemorySession(profile, expires_at=1000, refresh_at=120)
        with patch.dict(auth.memory_sessions, {"token": session}, clear=True), patch.object(auth, "monotonic", return_value=60):
            with patch.object(auth, "load_profile") as load_profile:
                self.assertIs(auth.current_memory_profile("token"), profile)
                self.assertIs(auth.current_memory_profile("token"), profile)
                load_profile.assert_not_called()

    def test_revokes_cached_session_when_account_is_no_longer_active(self):
        profile = Mock(id_usuario_sistema=42)
        session = auth.MemorySession(profile, expires_at=1000, refresh_at=120)
        with patch.dict(auth.memory_sessions, {"token": session}, clear=True), patch.object(auth, "monotonic", return_value=121):
            with patch.object(auth, "load_profile", return_value=None) as load_profile:
                with self.assertRaises(HTTPException) as error:
                    auth.current_memory_profile("token")
                self.assertEqual(error.exception.status_code, 401)
                self.assertNotIn("token", auth.memory_sessions)
                self.assertEqual(load_profile.call_args.args[1], 42)

    def test_retries_a_transient_profile_error_once(self):
        with patch.object(auth, "connection", side_effect=lambda: nullcontext(Mock())), \
                patch.object(auth, "fetch_all", side_effect=[pyodbc.Error("HYT00", "timeout"), []]) as read:
            self.assertIsNone(auth.load_profile(auth.ACTIVE_PROFILE, 42))
            self.assertEqual(read.call_count, 2)
