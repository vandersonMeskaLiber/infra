#!/usr/bin/env python3
"""Gera dashboard.html visual a partir dos logs do worklog."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
WORKLOG_DIR = SCRIPT_DIR.parent
OUT_HTML = WORKLOG_DIR / "dashboard.html"
STATE_PATH = WORKLOG_DIR / "logs" / "state" / "wifi_state.json"
WIFI_PRESENCA_PATH = WORKLOG_DIR / "logs" / "wifi_presenca.json"

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
    topic_total = sum(iv.seconds for iv in topics)

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
        "topics": [
            {
                "start": iv.start.isoformat(),
                "end": iv.end.isoformat(),
                "start_hm": ds.fmt_hm(iv.start),
                "end_hm": ds.fmt_hm(iv.end),
                "dur": ds.fmt_dur(iv.seconds),
                "seconds": iv.seconds,
                "label": iv.label,
            }
            for iv in topics
        ],
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
  .timeline {{
    position: relative; height: 54px; border-radius: 10px;
    background: repeating-linear-gradient(
      90deg, var(--bg2) 0, var(--bg2) calc(100%/24 - 1px), var(--line) calc(100%/24 - 1px), var(--line) calc(100%/24)
    );
    overflow: hidden; margin-bottom: 10px;
  }}
  .seg {{
    position: absolute; top: 10px; height: 34px; border-radius: 8px; opacity: .92;
    min-width: 3px;
  }}
  .seg.wifi {{ background: linear-gradient(90deg, #2563eb, #60a5fa); }}
  .seg.topic {{ background: linear-gradient(90deg, #d97706, #fbbf24); top: 14px; height: 26px; opacity: .85; }}
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
      <h2>Linha do tempo (00:00–24:00)</h2>
      <div class="legend">
        <span><i class="w"></i>Wi‑Fi</span>
        <span><i class="t"></i>Assuntos</span>
      </div>
      <div class="timeline" id="timeline"></div>
      <div class="hours">
        <span>00</span><span>06</span><span>12</span><span>18</span><span>24</span>
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

function minutesOfDay(iso) {{
  const d = new Date(iso);
  return d.getHours() * 60 + d.getMinutes() + d.getSeconds() / 60;
}}

function pct(min) {{
  return Math.max(0, Math.min(100, (min / (24 * 60)) * 100));
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
    const a = minutesOfDay(iv.start);
    const b = minutesOfDay(iv.end);
    const el = document.createElement('div');
    el.className = 'seg wifi';
    el.style.left = pct(a) + '%';
    el.style.width = Math.max(0.35, pct(b) - pct(a)) + '%';
    el.title = `${{iv.start_hm}}–${{iv.end_hm}} (${{iv.dur}})`;
    tl.appendChild(el);
  }});
  (d.topics || []).forEach(iv => {{
    const a = minutesOfDay(iv.start);
    const b = minutesOfDay(iv.end);
    const el = document.createElement('div');
    el.className = 'seg topic';
    el.style.left = pct(a) + '%';
    el.style.width = Math.max(0.35, pct(b) - pct(a)) + '%';
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
