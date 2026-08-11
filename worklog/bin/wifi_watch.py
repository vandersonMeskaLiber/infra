#!/usr/bin/env python3
"""Monitora presença na rede do escritório e grava eventos in/out em wifi.jsonl."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
WORKLOG_DIR = SCRIPT_DIR.parent
CONFIG_PATH = WORKLOG_DIR / "config.json"
STATE_PATH = WORKLOG_DIR / "logs" / "state" / "wifi_state.json"
LOG_PATH = WORKLOG_DIR / "logs" / "wifi.jsonl"


def load_config() -> Dict[str, Any]:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def run_cmd(args: list, timeout: int = 8) -> str:
    try:
        out = subprocess.check_output(args, stderr=subprocess.DEVNULL, timeout=timeout)
        return out.decode("utf-8", errors="replace")
    except Exception:
        return ""


def get_default_gateway_and_iface() -> Tuple[Optional[str], Optional[str]]:
    text = run_cmd(["route", "-n", "get", "default"])
    gateway = None
    iface = None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("gateway:"):
            gateway = line.split(":", 1)[1].strip()
        elif line.startswith("interface:"):
            iface = line.split(":", 1)[1].strip()
    return gateway, iface


def get_ssid(iface: str) -> Optional[str]:
    # Método 1: networksetup (funciona em alguns macOS)
    text = run_cmd(["networksetup", "-getairportnetwork", iface])
    m = re.search(r"Current Wi-Fi Network:\s*(.+)$", text.strip())
    if m:
        ssid = m.group(1).strip()
        if ssid and ssid.lower() not in {"you are not associated with an airport network.", "<redacted>"}:
            return ssid

    # Método 2: ipconfig getsummary
    text = run_cmd(["ipconfig", "getsummary", iface])
    m = re.search(r"^\s*SSID\s*:\s*(.+)$", text, re.MULTILINE)
    if m:
        ssid = m.group(1).strip()
        if ssid and ssid.lower() not in {"<redacted>", "nil", "none"}:
            return ssid

    # Método 3: system_profiler (SSID costuma vir redacted no macOS recente)
    text = run_cmd(["system_profiler", "SPAirPortDataType"])
    # Se algum dia deixar de redigir, captura o nome antes dos ":"
    block = re.search(
        r"Current Network Information:\s*\n\s*([^\n:]+):",
        text,
        re.MULTILINE,
    )
    if block:
        ssid = block.group(1).strip()
        if ssid and ssid.lower() not in {"<redacted>", "network type"}:
            return ssid

    return None


def is_iface_active(iface: str) -> bool:
    text = run_cmd(["ifconfig", iface])
    return "status: active" in text


def is_at_office(cfg: Dict[str, Any], ssid: Optional[str], gateway: Optional[str]) -> bool:
    ssids = {s.lower() for s in cfg.get("office_ssids", [])}
    gateways = set(cfg.get("office_gateways", []))
    mode = cfg.get("match_mode", "any")

    ssid_ok = bool(ssid and ssid.lower() in ssids)
    gw_ok = bool(gateway and gateway in gateways)

    if mode == "ssid":
        return ssid_ok
    if mode == "gateway":
        return gw_ok
    if mode == "all":
        # se SSID indisponível, cai para gateway
        if ssid is None:
            return gw_ok
        return ssid_ok and gw_ok
    # any (default)
    return ssid_ok or gw_ok


def load_state() -> Dict[str, Any]:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"at_office": False, "last_ssid": None, "last_gateway": None}


def save_state(state: Dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_event(
    event: str,
    ssid: Optional[str],
    gateway: Optional[str],
    iface: Optional[str],
    ts: Optional[str] = None,
) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": ts or now_iso(),
        "event": event,
        "ssid": ssid,
        "gateway": gateway,
        "iface": iface,
    }
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def tick(cfg: Dict[str, Any]) -> None:
    iface_cfg = cfg.get("wifi_interface", "en0")
    gateway, iface_route = get_default_gateway_and_iface()
    iface = iface_route or iface_cfg

    active = is_iface_active(iface) if iface else False
    ssid = get_ssid(iface) if active else None
    if not active:
        gateway = None

    at_office = active and is_at_office(cfg, ssid, gateway)
    state = load_state()
    was = bool(state.get("at_office"))
    now = now_iso()

    if at_office and not was:
        append_event("in", ssid, gateway, iface, ts=now)
    elif (not at_office) and was:
        # Mac em sleep não faz poll: usa o último momento visto no escritório,
        # não o horário do wake (evita presença inflada após fechar a tampa).
        out_ts = state.get("last_office_seen") or state.get("last_check") or now
        append_event("out", state.get("last_ssid"), state.get("last_gateway"), iface, ts=out_ts)

    new_state = {
        "at_office": at_office,
        "last_ssid": ssid if at_office else state.get("last_ssid"),
        "last_gateway": gateway if at_office else state.get("last_gateway"),
        "last_check": now,
        "active": active,
    }
    if at_office:
        new_state["last_office_seen"] = now
    elif state.get("last_office_seen"):
        new_state["last_office_seen"] = state.get("last_office_seen")
    state.update(new_state)
    save_state(state)


def main() -> int:
    once = "--once" in sys.argv
    cfg = load_config()
    poll = int(cfg.get("poll_seconds", 60))

    if once:
        tick(cfg)
        return 0

    # loop contínuo (launchd KeepAlive)
    while True:
        try:
            cfg = load_config()
            poll = int(cfg.get("poll_seconds", 60))
            tick(cfg)
        except Exception as exc:
            # nunca derruba o agente
            err_path = WORKLOG_DIR / "logs" / "wifi_watch.err.log"
            with open(err_path, "a", encoding="utf-8") as f:
                f.write(f"{now_iso()} ERROR {exc}\n")
        time.sleep(max(15, poll))


if __name__ == "__main__":
    sys.exit(main())
