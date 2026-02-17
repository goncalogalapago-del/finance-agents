from __future__ import annotations

import argparse
import json
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


def _ensure_http_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise RuntimeError("api-url must start with http:// or https://")
    return url


def _request_json(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    safe_url = _ensure_http_url(url)
    req = Request(  # noqa: S310 - scheme is validated in _ensure_http_url
        safe_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=timeout) as response:  # noqa: S310
            raw = response.read().decode("utf-8")
            return json.loads(raw)
    except HTTPError as exc:
        body = exc.read().decode("utf-8") if exc.fp is not None else ""
        detail = body or exc.reason
        raise RuntimeError(f"API request failed ({exc.code}): {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Unable to reach API: {exc.reason}") from exc


def _cmd_ask(args: argparse.Namespace) -> int:
    payload = {
        "channel": "cli",
        "actor_id": args.actor_id,
        "conversation_id": args.conversation_id,
        "message": args.message,
        "preferred_agent": args.agent,
    }
    url = args.api_url.rstrip("/") + "/agents/interactions"
    response = _request_json(url=url, payload=payload, timeout=args.timeout)

    if args.as_json:
        print(json.dumps(response, indent=2, sort_keys=True))
        return 0

    print(response["answer_text"])
    print(f"agent={response['agent']} intent={response['intent']}")
    print(f"interaction_id={response['interaction_id']}")
    return 0


def _cmd_personas(args: argparse.Namespace) -> int:
    url = _ensure_http_url(args.api_url.rstrip("/") + "/agents/personas")
    req = Request(url, method="GET")  # noqa: S310 - scheme is validated above
    try:
        with urlopen(req, timeout=args.timeout) as response:  # noqa: S310
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8") if exc.fp is not None else ""
        detail = body or exc.reason
        raise RuntimeError(f"API request failed ({exc.code}): {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Unable to reach API: {exc.reason}") from exc

    if args.as_json:
        print(json.dumps(data, indent=2, sort_keys=True))
        return 0

    for row in data:
        print(f"{row['key']}: {row['name']} - {row['description']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="finance-agents")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=float, default=10.0)

    subparsers = parser.add_subparsers(dest="command", required=True)

    ask = subparsers.add_parser("ask", help="Send a natural-language request")
    ask.add_argument("message")
    ask.add_argument("--actor-id", default="cli-user")
    ask.add_argument("--conversation-id", default="cli-session")
    ask.add_argument("--agent", default=None)
    ask.add_argument("--json", action="store_true", dest="as_json")
    ask.set_defaults(func=_cmd_ask)

    personas = subparsers.add_parser("personas", help="List available agent personas")
    personas.add_argument("--json", action="store_true", dest="as_json")
    personas.set_defaults(func=_cmd_personas)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
