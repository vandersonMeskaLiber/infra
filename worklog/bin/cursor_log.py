#!/usr/bin/env python3
"""Hook do Cursor: grava prompts/sessões e atualiza assunto sticky local. Fail-open."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
WORKLOG_DIR = SCRIPT_DIR.parent
LOG_PATH = WORKLOG_DIR / "logs" / "cursor.jsonl"

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def clean_text(value: Any, limit: int = 240) -> str:
    if value is None:
        return ""
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    text = " ".join(text.split())
    if len(text) > limit:
        return text[: limit - 1] + "…"
    return text


def pick(payload: Dict[str, Any], *keys: str) -> Optional[Any]:
    for key in keys:
        if key in payload and payload[key] not in (None, ""):
            return payload[key]
    return None


def main() -> int:
    raw = sys.stdin.read()
    payload: Dict[str, Any] = {}
    try:
        if raw.strip():
            payload = json.loads(raw)
    except Exception:
        payload = {"_raw": raw[:500]}

    event = (
        pick(payload, "hook_event_name", "event", "event_name", "type")
        or "unknown"
    )
    event = str(event)

    prompt = pick(payload, "prompt", "user_prompt", "message", "text", "content")
    conversation_id = pick(
        payload,
        "conversation_id",
        "conversationId",
        "session_id",
        "sessionId",
        "composerId",
        "generation_id",
    )
    workspace = pick(payload, "workspace_roots", "workspaceRoots", "cwd", "workspace")

    row = {
        "ts": now_iso(),
        "event": event,
        "prompt": clean_text(prompt, 300) if prompt else None,
        "conversation_id": str(conversation_id) if conversation_id else None,
        "workspace": clean_text(workspace, 200) if workspace else None,
    }

    useful = False
    if row["prompt"]:
        useful = True
    if event.lower() in {
        "beforesubmitprompt",
        "sessionstart",
        "sessionend",
        "stop",
        "userpromptsubmit",
    }:
        useful = True

    if useful:
        try:
            LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        except Exception:
            pass

        # atualiza assunto sticky (local) — nunca bloqueia o Cursor
        try:
            import assuntos_engine as ae

            ae.apply_event(
                prompt=row["prompt"],
                conversation_id=row["conversation_id"],
                workspace=str(row.get("workspace") or ""),
                event=event,
            )
        except Exception:
            pass

    print("{}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
