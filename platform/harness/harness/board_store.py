"""Compatibility & store facade backed by `atelier.harness.slack_board`."""
from __future__ import annotations

import contextlib
import sqlite3
from pathlib import Path
from typing import Iterator

from atelier.harness.slack_board import (
    GUEST_BRIDGE_CHANNEL,
    PermissionDenied,
    SlackBoardStore,
    cache_root,
    default_db_path,
    valid_agent_name,
)

OPERATOR = "operator"
TASK_CHARS = 500
TOPICS = ("info", "request", "ack", "handoff", "blocked", "evidence", "alert")


def root() -> Path:
    return cache_root()


def agent_name(name: str) -> str:
    return valid_agent_name(name)


@contextlib.contextmanager
def database(db_path: str | Path | None = None) -> Iterator[sqlite3.Connection]:
    store = SlackBoardStore(db_path)
    conn = sqlite3.connect(str(store.db_path), timeout=15.0)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            yield conn
    finally:
        conn.close()
