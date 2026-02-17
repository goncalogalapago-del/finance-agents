from __future__ import annotations

from typing import cast

import pytest

import app.db.session as db_session_module


class _FakeSession:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_get_db_session_yields_and_closes_session(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_session = _FakeSession()
    monkeypatch.setattr(db_session_module, "SessionLocal", lambda: fake_session)

    generator = db_session_module.get_db_session()
    yielded = cast(object, next(generator))
    assert yielded is fake_session
    assert fake_session.closed is False

    with pytest.raises(StopIteration):
        next(generator)

    assert fake_session.closed is True
