"""Web asset locator and `atelier board serve` entry point for the Slack-style Atelier Board."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from atelier import paths
from atelier.harness.slack_board import DEFAULT_PORT, serve_board

REPO_ROOT = paths.REPO
ASSETS = Path(__file__).resolve().with_name("board_web_assets")


def serve(args: Any) -> int:
    port = int(getattr(args, "port", DEFAULT_PORT) or DEFAULT_PORT)
    host = str(getattr(args, "host", "127.0.0.1") or "127.0.0.1")
    owner_login = getattr(args, "owner_login", None) or getattr(args, "allowed_user", None)
    guest_channel = getattr(args, "guest_channel", None)
    public_origins = list(getattr(args, "public_origin", None) or [])
    db_path = getattr(args, "db", None)
    allow_loopback_browser = bool(getattr(args, "allow_loopback_browser", False))
    seed = bool(getattr(args, "seed", False))
    return serve_board(
        db_path=db_path,
        host=host,
        port=port,
        owner_login=owner_login,
        guest_channel=guest_channel,
        public_origins=public_origins,
        allow_loopback_browser=allow_loopback_browser,
        seed=seed,
    )
