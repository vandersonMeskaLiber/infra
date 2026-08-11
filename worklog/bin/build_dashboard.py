#!/usr/bin/env python3
"""Gera dashboard.html visual a partir dos logs do worklog."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
WORKLOG_DIR = SCRIPT_DIR.parent
OUT_HTML = WORKLOG_DIR / "dashboard.html"
STATE_PATH = WORKLOG_DIR / "logs" / "state" / "wifi_state.json"
WIFI_PRESENCA_PATH = WORKLOG_DIR / "logs" / "wifi_presenca.json"
ASSUNTOS_MANUAIS_PATH = WORKLOG_DIR / "logs" / "assuntos_manuais.json"

# reusa a lógica do daily_summary (mesmo diretório)
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import daily_summary as ds  # noqa: E402


def load_state() -> Dict[str, Any]:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def load_wifi_presenca_overrides() -> Dict[str, Any]:
    if not WIFI_PRESENCA_PATH.exists():
        return {}
    try:
        data = json.loads(WIFI_PRESENCA_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _parse_hm(value: str) -> Optional[tuple]:
    import re

    value = (value or "").strip()
    m = re.match(r"^(\d{1,2}):(\d{2})$", value)
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if h > 23 or mi > 59:
        return None
    return h, mi


def _fmt_hm(h: int, m: int) -> str:
    return f"{h:02d}:{m:02d}"


def save_wifi_presenca_dia(day: date, inicio: str, fim: str) -> Dict[str, Any]:
    pi = _parse_hm(inicio)
    pf = _parse_hm(fim)
    if not pi or not pf:
        raise ValueError("Horário inválido (use HH:MM)")
    ini_s = _fmt_hm(*pi)
    fim_s = _fmt_hm(*pf)
    if (pi[0], pi[1]) >= (pf[0], pf[1]):
        raise ValueError("Saída deve ser maior que a chegada")
    data = load_wifi_presenca_overrides()
    data[day.isoformat()] = {"inicio": ini_s, "fim": fim_s}
    WIFI_PRESENCA_PATH.parent.mkdir(parents=True, exist_ok=True)
    WIFI_PRESENCA_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"day": day.isoformat(), "inicio": ini_s, "fim": fim_s, "manual": True}


def clear_wifi_presenca_dia(day: date) -> Dict[str, Any]:
    data = load_wifi_presenca_overrides()
    data.pop(day.isoformat(), None)
    WIFI_PRESENCA_PATH.parent.mkdir(parents=True, exist_ok=True)
    WIFI_PRESENCA_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"day": day.isoformat(), "manual": False, "cleared": True}


def load_assuntos_manuais() -> Dict[str, Any]:
    if not ASSUNTOS_MANUAIS_PATH.exists():
        return {}
    try:
        data = json.loads(ASSUNTOS_MANUAIS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_assuntos_manuais(data: Dict[str, Any]) -> None:
    ASSUNTOS_MANUAIS_PATH.parent.mkdir(parents=True, exist_ok=True)
    ASSUNTOS_MANUAIS_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def assuntos_manuais_do_dia(day: date) -> List[Dict[str, Any]]:
    raw = load_assuntos_manuais().get(day.isoformat()) or []
    if not isinstance(raw, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        if not (item.get("inicio") and item.get("fim") and item.get("assunto")):
            continue
        out.append(item)
    return out


def add_assunto_manual(
    day: date,
    inicio: str,
    fim: str,
    assunto: str,
    codigo_chamado: Optional[str] = None,
) -> Dict[str, Any]:
    pi = _parse_hm(inicio)
    pf = _parse_hm(fim)
    if not pi or not pf:
        raise ValueError("Horário inválido (use HH:MM)")
    ini_s = _fmt_hm(*pi)
    fim_s = _fmt_hm(*pf)
    if (pi[0], pi[1]) >= (pf[0], pf[1]):
        raise ValueError("Fim deve ser maior que o início")
    label = (assunto or "").strip()
    if not label:
        raise ValueError("Informe o assunto (ex.: reunião)")
    if len(label) > 200:
        label = label[:200].rstrip()
    codigo = (codigo_chamado or "").strip().upper() or None
    if codigo:
        import re

        m = re.match(r"^(?:CHA[\s\-_]*)?(\d{1,6})$", codigo)
        if not m:
            raise ValueError("Chamado inválido (use CHA-XXXX)")
        n = int(m.group(1))
        codigo = f"CHA-{n:04d}" if n < 1000 else f"CHA-{n}"

    item = {
        "id": f"manual-{uuid.uuid4().hex[:10]}",
        "inicio": ini_s,
        "fim": fim_s,
        "assunto": label,
        "codigo_chamado": codigo,
        "manual": True,
    }
    data = load_assuntos_manuais()
    day_s = day.isoformat()
    lista = data.get(day_s) or []
    if not isinstance(lista, list):
        lista = []
    lista.append(item)
    lista.sort(key=lambda x: (str(x.get("inicio") or ""), str(x.get("fim") or "")))
    data[day_s] = lista
    _save_assuntos_manuais(data)
    return {"day": day_s, **item}


def delete_assunto_manual(day: date, item_id: str) -> Dict[str, Any]:
    item_id = (item_id or "").strip()
    if not item_id:
        raise ValueError("id do assunto manual obrigatório")
    data = load_assuntos_manuais()
    day_s = day.isoformat()
    lista = data.get(day_s) or []
    if not isinstance(lista, list):
        lista = []
    nova = [x for x in lista if str(x.get("id")) != item_id]
    if len(nova) == len(lista):
        raise ValueError("Assunto manual não encontrado")
    if nova:
        data[day_s] = nova
    else:
        data.pop(day_s, None)
    _save_assuntos_manuais(data)
    return {"day": day_s, "deleted": item_id, "ok": True}


def _topic_dict_from_manual(day: date, item: Dict[str, Any], now: datetime) -> Optional[Dict[str, Any]]:
    pi = _parse_hm(str(item.get("inicio") or ""))
    pf = _parse_hm(str(item.get("fim") or ""))
    label = str(item.get("assunto") or "").strip()
    if not pi or not pf or not label:
        return None
    local = now.tzinfo or datetime.now().astimezone().tzinfo
    start = datetime(day.year, day.month, day.day, pi[0], pi[1], 0, tzinfo=local)
    end = datetime(day.year, day.month, day.day, pf[0], pf[1], 0, tzinfo=local)
    if end <= start:
        return None
    seconds = max(0, int((end - start).total_seconds()))
    return {
        "id": item.get("id") or f"manual-{uuid.uuid4().hex[:8]}",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "start_hm": ds.fmt_hm(start),
        "end_hm": ds.fmt_hm(end),
        "dur": ds.fmt_dur(seconds),
        "seconds": seconds,
        "label": label,
        "manual": True,
        "codigo_chamado": item.get("codigo_chamado"),
    }


def _carve_auto_topics_around_manuals(
    auto_topics: List[Dict[str, Any]],
    manual_topics: List[Dict[str, Any]],
    min_minutes: int = 5,
) -> List[Dict[str, Any]]:
    """Manual prevalece: remove a faixa manual dos assuntos monitorados (mantém sobras)."""
    if not auto_topics:
        return []
    if not manual_topics:
        return list(auto_topics)

    blockers = []
    for m in manual_topics:
        try:
            blockers.append((ds.parse_ts(m["start"]), ds.parse_ts(m["end"])))
        except Exception:
            continue
    if not blockers:
        return list(auto_topics)

    min_sec = max(1, int(min_minutes)) * 60
    carved: List[Dict[str, Any]] = []
    for t in auto_topics:
        try:
            start = ds.parse_ts(t["start"])
            end = ds.parse_ts(t["end"])
        except Exception:
            continue
        for a0, a1 in ds._subtract_time_ranges(start, end, blockers):
            seconds = max(0, int((a1 - a0).total_seconds()))
            if seconds < min_sec:
                continue
            piece = dict(t)
            piece.update(
                {
                    "start": a0.isoformat(),
                    "end": a1.isoformat(),
                    "start_hm": ds.fmt_hm(a0),
                    "end_hm": ds.fmt_hm(a1),
                    "dur": ds.fmt_dur(seconds),
                    "seconds": seconds,
                    "manual": False,
                }
            )
            carved.append(piece)
    return carved


def _manual_wifi_interval(
    day: date, inicio: str, fim: str, now: datetime, cfg: Dict[str, Any]
) -> ds.Interval:
    pi = _parse_hm(inicio)
    pf = _parse_hm(fim)
    if not pi or not pf:
        raise ValueError("Override de presença inválido")
    local = now.tzinfo or datetime.now().astimezone().tzinfo
    start = datetime(day.year, day.month, day.day, pi[0], pi[1], 0, tzinfo=local)
    end = datetime(day.year, day.month, day.day, pf[0], pf[1], 0, tzinfo=local)
    # se for hoje e a saída manual ainda é no futuro, limita ao agora para o tempo útil atual
    if day == now.date() and end > now:
        end = now
    if end <= start:
        end = start + timedelta(minutes=1)
    label = "presença manual"
    ssids = cfg.get("office_ssids") or []
    if ssids:
        label = f"{ssids[0]} (manual)"
    return ds.Interval(start, end, label=label)


def available_days(wifi_rows: List[Dict], cursor_rows: List[Dict], today: date) -> List[str]:
    days = {today.isoformat()}
    for rows in (wifi_rows, cursor_rows):
        for row in rows:
            try:
                days.add(ds.parse_ts(row["ts"]).date().isoformat())
            except Exception:
                continue
    for day_s in load_wifi_presenca_overrides().keys():
        try:
            date.fromisoformat(str(day_s))
            days.add(str(day_s))
        except Exception:
            continue
    for day_s, items in load_assuntos_manuais().items():
        try:
            date.fromisoformat(str(day_s))
        except Exception:
            continue
        if isinstance(items, list) and items:
            days.add(str(day_s))
    return sorted(days, reverse=True)


def day_payload(day: date, cfg: Dict[str, Any], wifi_rows, cursor_rows, now: datetime) -> Dict[str, Any]:
    gap_ignore = int(cfg.get("gap_ignore_seconds", 120))
    topic_gap = int(cfg.get("topic_gap_minutes", 20))
    day_start, day_end = ds.day_bounds(day)
    wifi_auto = ds.build_wifi_intervals(wifi_rows, day_start, day_end, gap_ignore, now)

    detectado_inicio = ds.fmt_hm(wifi_auto[0].start) if wifi_auto else None
    detectado_fim = ds.fmt_hm(wifi_auto[-1].end) if wifi_auto else None

    ov = load_wifi_presenca_overrides().get(day.isoformat()) or {}
    manual = bool(ov.get("inicio") and ov.get("fim"))
    if manual:
        wifi = [_manual_wifi_interval(day, str(ov["inicio"]), str(ov["fim"]), now, cfg)]
        # mantém no payload a saída salva (mesmo se clampou ao agora no intervalo)
        inicio_ui = str(ov["inicio"])
        fim_ui = str(ov["fim"])
    else:
        wifi = wifi_auto
        inicio_ui = detectado_inicio
        fim_ui = detectado_fim

    if day == now.date():
        fallback_end = now
    elif wifi:
        fallback_end = wifi[-1].end
    else:
        fallback_end = day_end - timedelta(seconds=1)

    topics = ds.build_topics(cursor_rows, day_start, day_end, topic_gap, fallback_end, cfg)
    label = ds.dominant_wifi_label(wifi, cfg)

    wifi_total = sum(iv.seconds for iv in wifi)
    auto_topics: List[Dict[str, Any]] = [
        {
            "start": iv.start.isoformat(),
            "end": iv.end.isoformat(),
            "start_hm": ds.fmt_hm(iv.start),
            "end_hm": ds.fmt_hm(iv.end),
            "dur": ds.fmt_dur(iv.seconds),
            "seconds": iv.seconds,
            "label": iv.label,
            "manual": False,
        }
        for iv in topics
    ]
    manual_topics: List[Dict[str, Any]] = []
    for item in assuntos_manuais_do_dia(day):
        t = _topic_dict_from_manual(day, item, now)
        if t:
            manual_topics.append(t)

    min_minutes = int(cfg.get("topic_min_minutes") or (cfg.get("apontamento") or {}).get("min_minutes") or 5)
    # Manual prevalece: corta o monitorado; sobras viram pedaços ajustados
    auto_topics = _carve_auto_topics_around_manuals(auto_topics, manual_topics, min_minutes)
    topics_out = auto_topics + manual_topics
    topics_out.sort(key=lambda t: (t.get("start") or "", t.get("end") or "", 0 if t.get("manual") else 1))
    topic_total = sum(int(t.get("seconds") or 0) for t in topics_out)

    return {
        "date": day.isoformat(),
        "wifi_label": label,
        "first_in": ds.fmt_hm(wifi[0].start) if wifi else None,
        "last_out": ds.fmt_hm(wifi[-1].end) if wifi else None,
        "wifi_total_sec": wifi_total,
        "wifi_total": ds.fmt_dur(wifi_total),
        "topic_total_sec": topic_total,
        "topic_total": ds.fmt_dur(topic_total),
        "wifi_presenca": {
            "inicio": inicio_ui,
            "fim": fim_ui,
            "manual": manual,
            "detectado": {
                "inicio": detectado_inicio,
                "fim": detectado_fim,
            },
        },
        "wifi": [
            {
                "start": iv.start.isoformat(),
                "end": iv.end.isoformat(),
                "start_hm": ds.fmt_hm(iv.start),
                "end_hm": ds.fmt_hm(iv.end),
                "dur": ds.fmt_dur(iv.seconds),
                "seconds": iv.seconds,
                "label": iv.label,
            }
            for iv in wifi
        ],
        "topics": topics_out,
    }


def build_data() -> Dict[str, Any]:
    cfg = ds.load_config()
    now = datetime.now().astimezone()
    today = now.date()
    wifi_rows = ds.read_jsonl(ds.WIFI_LOG)
    cursor_rows = ds.read_jsonl(ds.CURSOR_LOG)
    days = available_days(wifi_rows, cursor_rows, today)
    by_day = {}
    for d in days:
        day = date.fromisoformat(d)
        by_day[d] = day_payload(day, cfg, wifi_rows, cursor_rows, now)

    state = load_state()
    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "today": today.isoformat(),
        "at_office": bool(state.get("at_office")),
        "last_check": state.get("last_check"),
        "last_gateway": state.get("last_gateway"),
        "days": days,
        "by_day": by_day,
    }


def render_html(data: Dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Worklog</title>
<style>
  :root {{
    --bg: #0f1419;
    --bg2: #171d25;
    --panel: #1c2430;
    --line: #2a3544;
    --text: #e8eef6;
    --muted: #8b9bb0;
    --accent: #7d00fe;
    --accent2: #00c2a8;
    --wifi: #3b82f6;
    --topic: #f59e0b;
    --ok: #22c55e;
    --off: #64748b;
    --radius: 14px;
    --font: "IBM Plex Sans", "Segoe UI", sans-serif;
    --mono: "IBM Plex Mono", ui-monospace, monospace;
  }}
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; min-height: 100%; background: var(--bg); color: var(--text); font-family: var(--font); }}
  body {{
    background:
      radial-gradient(900px 420px at 8% -10%, rgba(125,0,254,.22), transparent 55%),
      radial-gradient(700px 380px at 100% 0%, rgba(0,194,168,.12), transparent 50%),
      var(--bg);
  }}
  .wrap {{ max-width: 1100px; margin: 0 auto; padding: 28px 20px 48px; }}
  header {{
    display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between;
    gap: 16px; margin-bottom: 22px;
  }}
  .brand {{ display: flex; flex-direction: column; gap: 4px; }}
  .brand h1 {{
    margin: 0; font-size: clamp(1.6rem, 3vw, 2.1rem); letter-spacing: -.02em; font-weight: 650;
  }}
  .brand p {{ margin: 0; color: var(--muted); font-size: .95rem; }}
  .status {{
    display: inline-flex; align-items: center; gap: 8px;
    padding: 8px 12px; border-radius: 999px; background: var(--panel); border: 1px solid var(--line);
    font-size: .85rem;
  }}
  .dot {{ width: 8px; height: 8px; border-radius: 50%; background: var(--off); }}
  .dot.on {{ background: var(--ok); box-shadow: 0 0 0 4px rgba(34,197,94,.15); }}
  .toolbar {{
    display: flex; flex-wrap: wrap; gap: 10px; align-items: center;
    margin-bottom: 18px;
  }}
  select, button {{
    font: inherit; color: var(--text); background: var(--panel);
    border: 1px solid var(--line); border-radius: 10px; padding: 9px 12px;
  }}
  button {{ cursor: pointer; }}
  button:hover {{ border-color: #445164; }}
  .meta {{ color: var(--muted); font-size: .82rem; font-family: var(--mono); }}
  .kpis {{
    display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 18px;
  }}
  @media (max-width: 820px) {{ .kpis {{ grid-template-columns: repeat(2, 1fr); }} }}
  .kpi {{
    background: linear-gradient(180deg, #222b38, var(--panel));
    border: 1px solid var(--line); border-radius: var(--radius); padding: 14px 16px;
  }}
  .kpi .label {{ color: var(--muted); font-size: .78rem; text-transform: uppercase; letter-spacing: .04em; }}
  .kpi .value {{ margin-top: 6px; font-size: 1.35rem; font-weight: 650; }}
  .kpi .sub {{ margin-top: 4px; color: var(--muted); font-size: .82rem; }}
  .panel {{
    background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius);
    padding: 16px 18px; margin-bottom: 14px;
  }}
  .panel h2 {{ margin: 0 0 12px; font-size: 1rem; font-weight: 600; }}
  .timeline-wrap {{
    display: grid; grid-template-columns: 72px 1fr; gap: 8px; align-items: start;
    margin-bottom: 10px;
  }}
  .timeline-lanes {{
    display: grid; grid-template-rows: 1fr 1fr; height: 68px; gap: 0;
    color: var(--muted); font-size: .7rem; font-family: var(--mono);
  }}
  .timeline-lanes span {{
    display: flex; align-items: center; justify-content: flex-end; padding-right: 2px;
  }}
  .timeline {{
    position: relative; height: 68px; border-radius: 10px;
    background:
      linear-gradient(180deg, transparent 33px, var(--line) 33px, var(--line) 34px, transparent 34px),
      repeating-linear-gradient(
        90deg, var(--bg2) 0, var(--bg2) calc(100%/14 - 1px), var(--line) calc(100%/14 - 1px), var(--line) calc(100%/14)
      );
    overflow: hidden;
  }}
  .seg {{
    position: absolute; height: 22px; border-radius: 6px; opacity: .92;
    min-width: 3px;
  }}
  .seg.wifi {{ background: linear-gradient(90deg, #2563eb, #60a5fa); top: 6px; }}
  .seg.topic {{ background: linear-gradient(90deg, #d97706, #fbbf24); top: 40px; opacity: .9; }}
  .hours {{
    display: flex; justify-content: space-between; color: var(--muted);
    font-size: .7rem; font-family: var(--mono); margin-bottom: 14px;
  }}
  .legend {{ display: flex; gap: 14px; color: var(--muted); font-size: .82rem; margin-bottom: 8px; }}
  .legend i {{ display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: 6px; }}
  .legend .w {{ background: #3b82f6; }}
  .legend .t {{ background: #f59e0b; }}
  ul.list {{ list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }}
  ul.list li {{
    display: grid; grid-template-columns: 120px 70px 1fr; gap: 10px; align-items: center;
    padding: 10px 12px; border-radius: 10px; background: var(--bg2); border: 1px solid var(--line);
  }}
  @media (max-width: 640px) {{
    ul.list li {{ grid-template-columns: 1fr; gap: 4px; }}
  }}
  .time {{ font-family: var(--mono); color: #c7d2e0; font-size: .88rem; }}
  .dur {{ color: var(--accent2); font-family: var(--mono); font-size: .85rem; }}
  .empty {{ color: var(--muted); padding: 8px 0; }}
  footer {{ margin-top: 18px; color: var(--muted); font-size: .8rem; }}
</style>
</head>
<body>
  <div class="wrap">
    <header>
      <div class="brand">
        <h1>Worklog</h1>
        <p>Presença Wi‑Fi + assuntos do Cursor</p>
      </div>
      <div class="status" id="statusPill">
        <span class="dot" id="statusDot"></span>
        <span id="statusText">carregando…</span>
      </div>
    </header>

    <div class="toolbar">
      <label>
        Dia
        <select id="daySelect"></select>
      </label>
      <button type="button" id="btnToday">Hoje</button>
      <span class="meta" id="generatedAt"></span>
    </div>

    <section class="kpis" id="kpis"></section>

    <section class="panel">
      <h2>Linha do tempo (05:00–19:00)</h2>
      <div class="legend">
        <span><i class="w"></i>Wi‑Fi</span>
        <span><i class="t"></i>Assuntos</span>
      </div>
      <div class="timeline-wrap">
        <div class="timeline-lanes"><span>Wi‑Fi</span><span>Assuntos</span></div>
        <div>
          <div class="timeline" id="timeline"></div>
          <div class="hours">
            <span>05</span><span>08</span><span>12</span><span>15</span><span>19</span>
          </div>
        </div>
      </div>
    </section>

    <section class="panel">
      <h2>Intervalos Wi‑Fi</h2>
      <ul class="list" id="wifiList"></ul>
    </section>

    <section class="panel">
      <h2>Assuntos (Cursor)</h2>
      <ul class="list" id="topicList"></ul>
    </section>

    <footer>
      Arquivo gerado localmente em <code>dashboard.html</code>.
      Painel ao vivo: <code>http://127.0.0.1:8765/</code>
    </footer>
  </div>

<script>
const DATA = {payload};

function esc(s) {{
  return String(s ?? '').replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
}}

const TL_START_MIN = 5 * 60;   // 05:00
const TL_END_MIN = 19 * 60;    // 19:00
const TL_SPAN_MIN = TL_END_MIN - TL_START_MIN;

function minutesOfDay(iso) {{
  const d = new Date(iso);
  return d.getHours() * 60 + d.getMinutes() + d.getSeconds() / 60;
}}

function pct(min) {{
  return Math.max(0, Math.min(100, ((min - TL_START_MIN) / TL_SPAN_MIN) * 100));
}}

function renderStatus() {{
  const on = !!DATA.at_office;
  document.getElementById('statusDot').classList.toggle('on', on);
  document.getElementById('statusText').textContent = on
    ? 'No escritório agora'
    : 'Fora do escritório';
  const gen = DATA.generated_at ? new Date(DATA.generated_at).toLocaleString('pt-BR') : '—';
  document.getElementById('generatedAt').textContent = 'Atualizado: ' + gen;
}}

function fillDays() {{
  const sel = document.getElementById('daySelect');
  sel.innerHTML = '';
  (DATA.days || []).forEach(d => {{
    const opt = document.createElement('option');
    opt.value = d;
    opt.textContent = d;
    if (d === DATA.today) opt.textContent += ' (hoje)';
    sel.appendChild(opt);
  }});
  sel.value = DATA.today;
  sel.addEventListener('change', () => renderDay(sel.value));
  document.getElementById('btnToday').addEventListener('click', () => {{
    sel.value = DATA.today;
    renderDay(DATA.today);
  }});
}}

function renderDay(day) {{
  const d = DATA.by_day[day];
  if (!d) return;

  document.getElementById('kpis').innerHTML = `
    <div class="kpi"><div class="label">Wi‑Fi</div><div class="value">${{esc(d.wifi_label || '—')}}</div><div class="sub">${{esc(d.first_in || '—')}} → ${{esc(d.last_out || '—')}}</div></div>
    <div class="kpi"><div class="label">Tempo conectado</div><div class="value">${{esc(d.wifi_total || '0min')}}</div><div class="sub">${{d.wifi.length}} intervalo(s)</div></div>
    <div class="kpi"><div class="label">Assuntos</div><div class="value">${{d.topics.length}}</div><div class="sub">total ${{esc(d.topic_total || '0min')}}</div></div>
    <div class="kpi"><div class="label">Gateway</div><div class="value" style="font-size:1rem;font-family:var(--mono)">${{esc(DATA.last_gateway || '—')}}</div><div class="sub">último check ${{esc((DATA.last_check || '').slice(11,19) || '—')}}</div></div>
  `;

  const tl = document.getElementById('timeline');
  tl.innerHTML = '';
  (d.wifi || []).forEach(iv => {{
    const left = pct(minutesOfDay(iv.start));
    const right = pct(minutesOfDay(iv.end));
    if (right <= left) return;
    const el = document.createElement('div');
    el.className = 'seg wifi';
    el.style.left = left + '%';
    el.style.width = Math.max(0.35, right - left) + '%';
    el.title = `${{iv.start_hm}}–${{iv.end_hm}} (${{iv.dur}})`;
    tl.appendChild(el);
  }});
  (d.topics || []).forEach(iv => {{
    const left = pct(minutesOfDay(iv.start));
    const right = pct(minutesOfDay(iv.end));
    if (right <= left) return;
    const el = document.createElement('div');
    el.className = 'seg topic';
    el.style.left = left + '%';
    el.style.width = Math.max(0.35, right - left) + '%';
    el.title = `${{iv.start_hm}}–${{iv.end_hm}} · ${{iv.label}}`;
    tl.appendChild(el);
  }});

  const wifiList = document.getElementById('wifiList');
  if (!d.wifi.length) {{
    wifiList.innerHTML = '<li class="empty">Sem registros de presença neste dia.</li>';
  }} else {{
    wifiList.innerHTML = d.wifi.map(iv => `
      <li>
        <span class="time">${{esc(iv.start_hm)}}–${{esc(iv.end_hm)}}</span>
        <span class="dur">${{esc(iv.dur)}}</span>
        <span>${{esc(iv.label || d.wifi_label || '')}}</span>
      </li>`).join('');
  }}

  const topicList = document.getElementById('topicList');
  if (!d.topics.length) {{
    topicList.innerHTML = '<li class="empty">Nenhum prompt registrado neste dia.</li>';
  }} else {{
    topicList.innerHTML = d.topics.map(iv => `
      <li>
        <span class="time">${{esc(iv.start_hm)}}–${{esc(iv.end_hm)}}</span>
        <span class="dur">${{esc(iv.dur)}}</span>
        <span>${{esc(iv.label)}}</span>
      </li>`).join('');
  }}
}}

renderStatus();
fillDays();
renderDay(DATA.today);
</script>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Gera dashboard HTML do worklog")
    parser.add_argument("--open", action="store_true", help="abre no navegador após gerar")
    args = parser.parse_args()

    data = build_data()
    OUT_HTML.write_text(render_html(data), encoding="utf-8")
    print(f"[ok] {OUT_HTML}")
    print(f"     dias: {len(data['days'])} | hoje: {data['today']} | no escritório: {data['at_office']}")

    if args.open:
        subprocess.run(["open", str(OUT_HTML)], check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
