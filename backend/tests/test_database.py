from unittest.mock import MagicMock

from app.db import session


def test_database_connection_success(monkeypatch):
    mock_context = MagicMock()
    mock_connection = mock_context.__enter__.return_value

    monkeypatch.setattr(
        session.engine,
        "connect",
        lambda: mock_context,
    )

    result = session.check_database_connection()

    assert result is True
    mock_connection.execute.assert_called_once()


def test_database_connection_failure(monkeypatch):
    def fail_connect():
        raise RuntimeError("Simulated database failure")

    monkeypatch.setattr(
        session.engine,
        "connect",
        fail_connect,
    )

    result = session.check_database_connection()

    assert result is False