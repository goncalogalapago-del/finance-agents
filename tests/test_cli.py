from __future__ import annotations

import io
from argparse import Namespace
from email.message import Message
from typing import Any
from urllib.error import HTTPError, URLError

import pytest
from _pytest.capture import CaptureFixture
from _pytest.monkeypatch import MonkeyPatch

import app.cli as cli


class _FakeResponse:
    def __init__(self, payload: Any) -> None:
        self._payload = payload

    def read(self) -> bytes:
        import json

        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


def test_cmd_ask_json_output(monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]) -> None:
    expected = {
        "answer_text": "ok",
        "agent": "risk",
        "intent": "risk_summary",
        "interaction_id": "abc",
    }

    def _fake_urlopen(req: object, timeout: float) -> _FakeResponse:
        return _FakeResponse(expected)

    monkeypatch.setattr(cli, "urlopen", _fake_urlopen)

    args = Namespace(
        api_url="http://127.0.0.1:8000",
        timeout=2.0,
        actor_id="cli-user",
        conversation_id="cli-session",
        message="risk",
        agent=None,
        as_json=True,
    )

    rc = cli._cmd_ask(args)

    assert rc == 0
    output = capsys.readouterr().out
    assert '"interaction_id": "abc"' in output


def test_cmd_personas_plain_output(
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    personas = [
        {
            "key": "risk",
            "name": "Risk Agent",
            "description": "Risk text",
        }
    ]

    def _fake_urlopen(req: object, timeout: float) -> _FakeResponse:
        return _FakeResponse(personas)

    monkeypatch.setattr(cli, "urlopen", _fake_urlopen)

    args = Namespace(api_url="http://127.0.0.1:8000", timeout=2.0, as_json=False)
    rc = cli._cmd_personas(args)

    assert rc == 0
    output = capsys.readouterr().out
    assert "risk: Risk Agent" in output


def test_cmd_ask_plain_output(monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]) -> None:
    expected: dict[str, object] = {
        "answer_text": "hello",
        "agent": "audit",
        "intent": "audit_trace",
        "interaction_id": "xyz",
    }

    def _fake_request_json(
        url: str, payload: dict[str, object], timeout: float
    ) -> dict[str, object]:
        del url, payload, timeout
        return expected

    monkeypatch.setattr(cli, "_request_json", _fake_request_json)

    args = Namespace(
        api_url="http://127.0.0.1:8000",
        timeout=2.0,
        actor_id="cli-user",
        conversation_id="cli-session",
        message="audit",
        agent=None,
        as_json=False,
    )

    rc = cli._cmd_ask(args)

    assert rc == 0
    output = capsys.readouterr().out
    assert "hello" in output
    assert "agent=audit intent=audit_trace" in output
    assert "interaction_id=xyz" in output


def test_cmd_personas_json_output(monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]) -> None:
    personas = [{"key": "risk", "name": "Risk Agent", "description": "Risk text"}]

    def _fake_urlopen(req: object, timeout: float) -> _FakeResponse:
        del req, timeout
        return _FakeResponse(personas)

    monkeypatch.setattr(cli, "urlopen", _fake_urlopen)
    args = Namespace(api_url="http://127.0.0.1:8000", timeout=2.0, as_json=True)

    rc = cli._cmd_personas(args)

    assert rc == 0
    output = capsys.readouterr().out
    assert '"key": "risk"' in output


def test_request_json_wraps_http_and_url_errors(monkeypatch: MonkeyPatch) -> None:
    http_error = HTTPError(
        url="http://127.0.0.1:8000/agents/interactions",
        code=400,
        msg="bad request",
        hdrs=Message(),
        fp=io.BytesIO(b"invalid request"),
    )

    def _raise_http_error(req: object, timeout: float) -> _FakeResponse:
        del req, timeout
        raise http_error

    monkeypatch.setattr(cli, "urlopen", _raise_http_error)
    with pytest.raises(RuntimeError, match="API request failed"):
        cli._request_json("http://127.0.0.1:8000/agents/interactions", {}, timeout=1.0)

    def _raise_url_error(req: object, timeout: float) -> _FakeResponse:
        del req, timeout
        raise URLError("connection refused")

    monkeypatch.setattr(cli, "urlopen", _raise_url_error)
    with pytest.raises(RuntimeError, match="Unable to reach API"):
        cli._request_json("http://127.0.0.1:8000/agents/interactions", {}, timeout=1.0)


def test_main_handles_runtime_errors(
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    def _raise_runtime(args: Namespace) -> int:
        del args
        raise RuntimeError("boom")

    monkeypatch.setattr(cli, "_cmd_ask", _raise_runtime)
    rc = cli.main(["ask", "hello"])

    assert rc == 1
    assert "boom" in capsys.readouterr().err


def test_build_parser_and_main_success(monkeypatch: MonkeyPatch) -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["personas"])
    assert callable(args.func)

    monkeypatch.setattr(cli, "_cmd_personas", lambda args: 0)
    assert cli.main(["personas"]) == 0
