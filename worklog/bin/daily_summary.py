#!/usr/bin/env python3
"""Consolida wifi.jsonl + cursor.jsonl em diario/YYYY-MM-DD.md."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
WORKLOG_DIR = SCRIPT_DIR.parent
CONFIG_PATH = WORKLOG_DIR / "config.json"
WIFI_LOG = WORKLOG_DIR / "logs" / "wifi.jsonl"
CURSOR_LOG = WORKLOG_DIR / "logs" / "cursor.jsonl"
DIARIO_DIR = WORKLOG_DIR / "diario"


@dataclass
class Interval:
    start: datetime
    end: datetime
    label: str = ""

    @property
    def seconds(self) -> int:
        return max(0, int((self.end - self.start).total_seconds()))


def load_config() -> Dict[str, Any]:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def parse_ts(value: str) -> datetime:
    # aceita ISO com offset
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt


def day_bounds(day: date) -> Tuple[datetime, datetime]:
    local = datetime.now().astimezone().tzinfo
    start = datetime(day.year, day.month, day.day, 0, 0, 0, tzinfo=local)
    end = start + timedelta(days=1)
    return start, end


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def fmt_hm(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def fmt_dur(seconds: int) -> str:
    seconds = max(0, int(seconds))
    h = seconds // 3600
    m = (seconds % 3600) // 60
    if h and m:
        return f"{h}h{m:02d}"
    if h:
        return f"{h}h"
    return f"{m}min"


def merge_short_gaps(intervals: List[Interval], gap_ignore: int) -> List[Interval]:
    if not intervals:
        return []
    intervals = sorted(intervals, key=lambda i: i.start)
    merged = [intervals[0]]
    for cur in intervals[1:]:
        prev = merged[-1]
        gap = (cur.start - prev.end).total_seconds()
        if gap < gap_ignore:
            prev.end = max(prev.end, cur.end)
        else:
            merged.append(cur)
    return merged


def build_wifi_intervals(
    rows: List[Dict[str, Any]],
    day_start: datetime,
    day_end: datetime,
    gap_ignore: int,
    now: datetime,
) -> List[Interval]:
    events: List[Tuple[datetime, str, Optional[str]]] = []
    for row in rows:
        try:
            ts = parse_ts(row["ts"])
        except Exception:
            continue
        if not (day_start <= ts < day_end):
            continue
        event = row.get("event")
        if event not in {"in", "out"}:
            continue
        ssid = row.get("ssid")
        events.append((ts, event, ssid))

    events.sort(key=lambda x: x[0])
    intervals: List[Interval] = []
    open_start: Optional[datetime] = None
    last_ssid = None

    for ts, event, ssid in events:
        if event == "in":
            if open_start is None:
                open_start = ts
                last_ssid = ssid or last_ssid
        elif event == "out" and open_start is not None:
            intervals.append(Interval(open_start, ts, label=str(last_ssid or "")))
            open_start = None

    # ainda conectado no fim do dia / agora
    if open_start is not None:
        end = min(now, day_end - timedelta(seconds=1))
        if end > open_start:
            intervals.append(Interval(open_start, end, label=str(last_ssid or "")))

    return merge_short_gaps(intervals, gap_ignore)


def topic_title(prompt: str) -> str:
    text = " ".join((prompt or "").split()).strip()
    if not text:
        return "Assunto sem título"
    # pega até ~70 chars, preferindo pontuação
    cut = text[:70]
    for sep in [". ", "? ", "! ", " — ", " - "]:
        idx = text.find(sep)
        if 12 <= idx <= 70:
            cut = text[:idx]
            break
    if len(text) > len(cut):
        cut = cut.rstrip(" ,;:") + "…"
    return cut


def build_topics(
    rows: List[Dict[str, Any]],
    day_start: datetime,
    day_end: datetime,
    topic_gap_minutes: int,
    fallback_end: datetime,
) -> List[Interval]:
    prompts: List[Tuple[datetime, str]] = []
    for row in rows:
        prompt = row.get("prompt")
        if not prompt:
            continue
        try:
            ts = parse_ts(row["ts"])
        except Exception:
            continue
        if not (day_start <= ts < day_end):
            continue
        prompts.append((ts, str(prompt)))

    prompts.sort(key=lambda x: x[0])
    if not prompts:
        return []

    gap = timedelta(minutes=topic_gap_minutes)
    groups: List[List[Tuple[datetime, str]]] = []
    current: List[Tuple[datetime, str]] = [prompts[0]]
    for ts, prompt in prompts[1:]:
        last_ts = current[-1][0]
        if ts - last_ts >= gap:
            groups.append(current)
            current = [(ts, prompt)]
        else:
            current.append((ts, prompt))
    groups.append(current)

    topics: List[Interval] = []
    for idx, group in enumerate(groups):
        start = group[0][0]
        title = topic_title(group[0][1])
        if idx + 1 < len(groups):
            end = groups[idx + 1][0][0]
        else:
            end = max(group[-1][0], fallback_end)
            if end <= start:
                end = start + timedelta(minutes=1)
        topics.append(Interval(start, end, label=title))
    return topics


def dominant_wifi_label(intervals: List[Interval], cfg: Dict[str, Any]) -> str:
    for iv in intervals:
        if iv.label:
            return iv.label
    ssids = cfg.get("office_ssids") or []
    if ssids:
        return str(ssids[0])
    return "escritório"


def render_markdown(
    day: date,
    wifi: List[Interval],
    topics: List[Interval],
    wifi_label: str,
) -> str:
    lines: List[str] = []
    lines.append(f"# {day.isoformat()}")

    if wifi:
        first = wifi[0].start
        last = wifi[-1].end
        total = sum(iv.seconds for iv in wifi)
        lines.append(f"Wi‑Fi: {wifi_label}")
        lines.append(f"Primeira conexão: {fmt_hm(first)} | Última desconexão: {fmt_hm(last)}")
        lines.append(f"Total conectado: {fmt_dur(total)}")
        lines.append("")
        lines.append("### Intervalos Wi‑Fi")
        for iv in wifi:
            lines.append(f"- {fmt_hm(iv.start)}–{fmt_hm(iv.end)} ({fmt_dur(iv.seconds)})")
    else:
        lines.append("Wi‑Fi: sem registros de presença no escritório neste dia")

    lines.append("")
    lines.append("### Assuntos (Cursor)")
    if topics:
        for iv in topics:
            lines.append(
                f"- {fmt_hm(iv.start)}–{fmt_hm(iv.end)} ({fmt_dur(iv.seconds)}) · {iv.label}"
            )
        total_topics = sum(iv.seconds for iv in topics)
        lines.append("")
        lines.append(f"Total em assuntos: {fmt_dur(total_topics)}")
    else:
        lines.append("- (nenhum prompt registrado neste dia)")

    lines.append("")
    return "\n".join(lines)


def summarize(day: date, write: bool = True) -> str:
    cfg = load_config()
    gap_ignore = int(cfg.get("gap_ignore_seconds", 120))
    topic_gap = int(cfg.get("topic_gap_minutes", 20))
    now = datetime.now().astimezone()
    day_start, day_end = day_bounds(day)

    wifi_rows = read_jsonl(WIFI_LOG)
    cursor_rows = read_jsonl(CURSOR_LOG)

    wifi = build_wifi_intervals(wifi_rows, day_start, day_end, gap_ignore, now)

    # fim padrão dos assuntos: agora (se hoje), senão fim do dia / último wifi
    if day == now.date():
        fallback_end = now
    elif wifi:
        fallback_end = wifi[-1].end
    else:
        fallback_end = day_end - timedelta(seconds=1)

    topics = build_topics(cursor_rows, day_start, day_end, topic_gap, fallback_end)
    label = dominant_wifi_label(wifi, cfg)
    md = render_markdown(day, wifi, topics, label)

    if write:
        DIARIO_DIR.mkdir(parents=True, exist_ok=True)
        out = DIARIO_DIR / f"{day.isoformat()}.md"
        out.write_text(md, encoding="utf-8")
    return md


def main() -> int:
    parser = argparse.ArgumentParser(description="Gera resumo diário do worklog")
    parser.add_argument("--date", help="YYYY-MM-DD (default: hoje)")
    parser.add_argument("--yesterday", action="store_true")
    parser.add_argument("--stdout", action="store_true", help="só imprime, não grava")
    args = parser.parse_args()

    today = datetime.now().astimezone().date()
    if args.yesterday:
        day = today - timedelta(days=1)
    elif args.date:
        day = date.fromisoformat(args.date)
    else:
        day = today

    md = summarize(day, write=not args.stdout)
    print(md)
    if not args.stdout:
        print(f"[ok] gravado em {DIARIO_DIR / (day.isoformat() + '.md')}", file=sys.stderr)
        # atualiza painel visual
        try:
            import subprocess

            subprocess.run(
                [sys.executable, str(SCRIPT_DIR / "build_dashboard.py")],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
