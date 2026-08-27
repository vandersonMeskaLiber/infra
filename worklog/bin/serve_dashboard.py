#!/usr/bin/env python3
"""Serve o painel Worklog ao vivo (lê wifi/cursor logs a cada request)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict
from urllib.parse import parse_qs, urlparse

SCRIPT_DIR = Path(__file__).resolve().parent
WORKLOG_DIR = SCRIPT_DIR.parent
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import build_dashboard as bd  # noqa: E402

LIVE_HTML = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Worklog</title>
<style>
  :root {
    --bg: #0f1419;
    --bg2: #171d25;
    --panel: #1c2430;
    --line: #2a3544;
    --text: #e8eef6;
    --muted: #8b9bb0;
    --accent: #7d00fe;
    --accent2: #00c2a8;
    --ok: #22c55e;
    --off: #64748b;
    --radius: 14px;
    --font: "IBM Plex Sans", "Segoe UI", sans-serif;
    --mono: "IBM Plex Mono", ui-monospace, monospace;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; min-height: 100%; background: var(--bg); color: var(--text); font-family: var(--font); }
  body {
    background:
      radial-gradient(900px 420px at 8% -10%, rgba(125,0,254,.22), transparent 55%),
      radial-gradient(700px 380px at 100% 0%, rgba(0,194,168,.12), transparent 50%),
      var(--bg);
  }
  .wrap { max-width: min(1680px, 98vw); margin: 0 auto; padding: 24px 16px 48px; }
  .apto-horarios {
    display: flex; flex-direction: row; flex-wrap: nowrap; align-items: center; gap: 6px;
    white-space: nowrap;
  }
  .apto-horarios input.apto-hi,
  .apto-horarios input.apto-hf {
    width: 4.6rem; min-width: 4.6rem; max-width: 4.6rem;
    box-sizing: border-box;
    background: var(--bg2); color: var(--text);
    border: 1px solid var(--line); border-radius: 8px;
    padding: 6px 8px; font-family: var(--mono); font-size: .85rem;
    text-align: center;
  }
  #aptoTableWrap table { width: 100%; border-collapse: collapse; table-layout: fixed; }
  #aptoTableWrap th,
  #aptoTableWrap td { vertical-align: middle; overflow: hidden; }
  #aptoTableWrap .apto-col-ok { width: 44px; }
  #aptoTableWrap .apto-col-hora { width: 200px; }
  #aptoTableWrap .apto-col-dur {
    width: 72px; color: var(--accent2); font-family: var(--mono);
    white-space: nowrap;
  }
  #aptoTableWrap th.apto-col-dur { color: var(--muted); font-family: inherit; }
  #aptoTableWrap .apto-col-assunto { width: auto; }
  #aptoTableWrap .apto-col-cha { width: 150px; }
  #aptoTableWrap .apto-col-act { width: 88px; }
  #aptoTableWrap .apto-assunto-input {
    width: 100%; min-width: 140px;
    background: var(--bg2); color: var(--text);
    border: 1px solid var(--line); border-radius: 8px;
    padding: 7px 10px; font: inherit;
  }
  #aptoTableWrap .apto-assunto-input:disabled {
    opacity: .7; border-style: dashed;
  }
  tr.apto-pausa td {
    padding: 8px 10px !important;
    background: rgba(148, 163, 184, 0.12);
    border-top: 1px dashed #475569;
    border-bottom: 1px dashed #475569;
    color: var(--muted);
    font-size: .82rem;
  }
  tr.apto-pausa .apto-pausa-label {
    display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
    font-family: var(--mono);
  }
  tr.apto-pausa .apto-pausa-tag {
    display: inline-block; padding: 2px 8px; border-radius: 999px;
    background: rgba(100, 116, 139, 0.35); color: #cbd5e1; font-size: .75rem;
    text-transform: uppercase; letter-spacing: .04em;
  }
  tr.apto-pausa.apto-pausa-almoco td {
    background: rgba(245, 158, 11, 0.10);
    border-top-color: rgba(245, 158, 11, 0.45);
    border-bottom-color: rgba(245, 158, 11, 0.45);
  }
  tr.apto-pausa.apto-pausa-almoco .apto-pausa-tag {
    background: rgba(245, 158, 11, 0.22); color: #fbbf24;
  }
  header {
    display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between;
    gap: 16px; margin-bottom: 22px;
  }
  .brand h1 {
    margin: 0; font-size: clamp(1.6rem, 3vw, 2.1rem); letter-spacing: -.02em; font-weight: 650;
  }
  .brand p { margin: 4px 0 0; color: var(--muted); font-size: .95rem; }
  .status {
    display: inline-flex; align-items: center; gap: 8px;
    padding: 8px 12px; border-radius: 999px; background: var(--panel); border: 1px solid var(--line);
    font-size: .85rem;
  }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--off); }
  .dot.on { background: var(--ok); box-shadow: 0 0 0 4px rgba(34,197,94,.15); }
  .toolbar {
    display: flex; flex-wrap: wrap; gap: 10px; align-items: center;
    margin-bottom: 18px;
  }
  select, button {
    font: inherit; color: var(--text); background: var(--panel);
    border: 1px solid var(--line); border-radius: 10px; padding: 9px 12px;
  }
  button { cursor: pointer; }
  button:hover { border-color: #445164; }
  .meta { color: var(--muted); font-size: .82rem; font-family: var(--mono); }
  .kpis {
    display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 18px;
  }
  @media (max-width: 820px) { .kpis { grid-template-columns: repeat(2, 1fr); } }
  .kpi {
    background: linear-gradient(180deg, #222b38, var(--panel));
    border: 1px solid var(--line); border-radius: var(--radius); padding: 14px 16px;
  }
  .kpi .label { color: var(--muted); font-size: .78rem; text-transform: uppercase; letter-spacing: .04em; }
  .kpi .value { margin-top: 6px; font-size: 1.35rem; font-weight: 650; }
  .kpi .sub { margin-top: 4px; color: var(--muted); font-size: .82rem; }
  .panel {
    background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius);
    padding: 16px 18px; margin-bottom: 14px;
  }
  .panel h2 { margin: 0 0 12px; font-size: 1rem; font-weight: 600; }
  .timeline-wrap {
    display: grid; grid-template-columns: 72px 1fr; gap: 8px; align-items: start;
    margin-bottom: 10px;
  }
  .timeline-lanes {
    display: grid; grid-template-rows: 1fr 1fr; height: 68px; gap: 0;
    color: var(--muted); font-size: .7rem; font-family: var(--mono);
  }
  .timeline-lanes span {
    display: flex; align-items: center; justify-content: flex-end; padding-right: 2px;
  }
  .timeline {
    position: relative; height: 68px; border-radius: 10px;
    background:
      linear-gradient(180deg, transparent 33px, var(--line) 33px, var(--line) 34px, transparent 34px),
      repeating-linear-gradient(
        90deg, var(--bg2) 0, var(--bg2) calc(100%/14 - 1px), var(--line) calc(100%/14 - 1px), var(--line) calc(100%/14)
      );
    overflow: hidden;
  }
  .seg {
    position: absolute; height: 22px; border-radius: 6px; opacity: .92;
    min-width: 3px;
  }
  .seg.wifi { background: linear-gradient(90deg, #2563eb, #60a5fa); top: 6px; }
  .seg.topic { background: linear-gradient(90deg, #d97706, #fbbf24); top: 40px; opacity: .9; }
  .hours {
    display: flex; justify-content: space-between; color: var(--muted);
    font-size: .7rem; font-family: var(--mono); margin-bottom: 14px;
  }
  .legend { display: flex; gap: 14px; color: var(--muted); font-size: .82rem; margin-bottom: 8px; }
  .legend i { display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: 6px; }
  .legend .w { background: #3b82f6; }
  .legend .t { background: #f59e0b; }
  ul.list { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }
  ul.list li {
    display: grid; grid-template-columns: 120px 70px 1fr; gap: 10px; align-items: center;
    padding: 10px 12px; border-radius: 10px; background: var(--bg2); border: 1px solid var(--line);
  }
  @media (max-width: 640px) { ul.list li { grid-template-columns: 1fr; gap: 4px; } }
  .time { font-family: var(--mono); color: #c7d2e0; font-size: .88rem; }
  .dur { color: var(--accent2); font-family: var(--mono); font-size: .85rem; }
  .empty { color: var(--muted); padding: 8px 0; }
  footer { margin-top: 18px; color: var(--muted); font-size: .8rem; }
  .err { color: #f87171; margin: 12px 0; }
  .apto-loading {
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    gap: 14px; min-height: 140px; padding: 28px 12px;
    border: 1px dashed var(--line); border-radius: 12px; background: rgba(15,20,25,.35);
  }
  .apto-spinner {
    width: 28px; height: 28px; border-radius: 50%;
    border: 3px solid rgba(125,0,254,.22);
    border-top-color: var(--accent);
    animation: apto-spin .7s linear infinite;
  }
  .apto-loading-text { color: var(--muted); font-size: .9rem; }
  .apto-skel {
    width: 100%; display: grid; gap: 10px; margin-top: 4px;
  }
  .apto-skel-row {
    height: 42px; border-radius: 10px;
    background: linear-gradient(90deg, var(--bg2) 0%, #243040 45%, var(--bg2) 90%);
    background-size: 200% 100%;
    animation: apto-shimmer 1.2s ease-in-out infinite;
    opacity: .85;
  }
  @keyframes apto-spin { to { transform: rotate(360deg); } }
  @keyframes apto-shimmer {
    0% { background-position: 100% 0; }
    100% { background-position: -100% 0; }
  }
  button:disabled { opacity: .55; cursor: wait; }
</style>
</head>
<body>
  <div class="wrap">
    <header>
      <div class="brand">
        <h1>Worklog</h1>
        <p>Presença Wi‑Fi + assuntos do Cursor · ao vivo</p>
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
      <button type="button" id="btnRefresh">Atualizar</button>
      <span class="meta" id="generatedAt"></span>
    </div>
    <div class="err" id="errBox" hidden></div>

    <section class="kpis" id="kpis"></section>

    <section class="panel">
      <h2>Linha do tempo (05:00–19:00)</h2>
      <div class="legend">
        <span><i class="w"></i>Trabalho</span>
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
      <h2>Janelas de trabalho</h2>
      <p class="meta" id="wifiDetectadoHint" style="margin:0 0 10px"></p>
      <div style="display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:12px">
        <button type="button" id="btnAddTrabalho">+ intervalo</button>
        <button type="button" id="btnSalvarWifi">Salvar janelas</button>
        <button type="button" id="btnWifiAuto">Usar automático (Wi‑Fi)</button>
        <span class="meta" id="wifiPresencaMsg"></span>
      </div>
      <div id="trabalhoIntervalos" style="display:grid;gap:8px"></div>
      <div style="display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-top:12px">
        <span class="meta">Almoço</span>
        <input id="almocoInicio" type="time" style="background:var(--bg2);color:var(--text);border:1px solid var(--line);border-radius:8px;padding:8px 10px;font-family:var(--mono)" />
        <span class="meta">até</span>
        <input id="almocoFim" type="time" style="background:var(--bg2);color:var(--text);border:1px solid var(--line);border-radius:8px;padding:8px 10px;font-family:var(--mono)" />
        <button type="button" id="btnSalvarAlmoco">Salvar almoço</button>
        <span class="meta" id="almocoMsg"></span>
      </div>
    </section>

    <section class="panel" id="apontamentoPanel">
      <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px;flex-wrap:wrap">
        <h2 style="margin:0">Assuntos</h2>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <button type="button" id="btnUnificarAssuntos">Unificar selecionados</button>
          <button type="button" id="btnDistribuirWifi">Distribuir tempo de trabalho</button>
          <button type="button" id="btnConfirmApto">Confirmar apontamentos</button>
        </div>
      </div>
      <div style="display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:12px">
        <span class="meta">Manual</span>
        <input id="manualInicio" type="time" style="background:var(--bg2);color:var(--text);border:1px solid var(--line);border-radius:8px;padding:8px 10px;font-family:var(--mono)" />
        <span class="meta">até</span>
        <input id="manualFim" type="time" style="background:var(--bg2);color:var(--text);border:1px solid var(--line);border-radius:8px;padding:8px 10px;font-family:var(--mono)" />
        <input id="manualAssunto" type="text" placeholder="Ex.: reunião com cliente" style="flex:1;min-width:180px;background:var(--bg2);color:var(--text);border:1px solid var(--line);border-radius:8px;padding:8px 10px" />
        <div style="display:flex;align-items:center;background:var(--bg2);border:1px solid var(--line);border-radius:8px;overflow:hidden">
          <span style="padding:7px 8px;color:var(--muted);font-family:var(--mono);font-size:.82rem;border-right:1px solid var(--line)">CHA-</span>
          <input id="manualCha" type="text" inputmode="numeric" placeholder="2761" style="width:72px;background:transparent;color:var(--text);border:0;padding:8px 10px;font-family:var(--mono)" />
        </div>
        <button type="button" id="btnAddManual">Adicionar assunto</button>
        <span class="meta" id="manualMsg"></span>
      </div>
      <div class="err" id="aptoErr" hidden></div>
      <div class="meta" id="aptoMsg" style="margin-bottom:10px" hidden></div>
      <div id="aptoTableWrap">
        <div class="apto-loading" aria-busy="true" aria-live="polite">
          <div class="apto-spinner" aria-hidden="true"></div>
          <div class="apto-loading-text">Carregando assuntos…</div>
          <div class="apto-skel">
            <div class="apto-skel-row"></div>
            <div class="apto-skel-row"></div>
            <div class="apto-skel-row"></div>
          </div>
        </div>
      </div>
    </section>

    <footer>
      Abra sempre <code>http://127.0.0.1:8765/</code> — os dados vêm direto dos logs, sem gerar HTML de novo.
      Atualiza sozinho a cada 30s.
    </footer>
  </div>

<script>
let DATA = null;
let selectedDay = null;
let daysWired = false;
let APTO = null;
let aptoLocked = false;
let aptoLoading = false;
const REFRESH_MS = 30000;

function setAptoButtonsDisabled(disabled) {
  const ids = ['btnConfirmApto', 'btnDistribuirWifi', 'btnAddManual', 'btnUnificarAssuntos'];
  ids.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.disabled = !!disabled;
  });
}

function showAptoLoading(text) {
  aptoLoading = true;
  setAptoButtonsDisabled(true);
  const wrap = document.getElementById('aptoTableWrap');
  if (!wrap) return;
  wrap.innerHTML = `
    <div class="apto-loading" aria-busy="true" aria-live="polite">
      <div class="apto-spinner" aria-hidden="true"></div>
      <div class="apto-loading-text">${esc(text || 'Carregando assuntos…')}</div>
      <div class="apto-skel">
        <div class="apto-skel-row"></div>
        <div class="apto-skel-row"></div>
        <div class="apto-skel-row"></div>
      </div>
    </div>`;
}

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

const TL_START_MIN = 5 * 60;   // 05:00
const TL_END_MIN = 19 * 60;    // 19:00
const TL_SPAN_MIN = TL_END_MIN - TL_START_MIN;

function minutesOfDay(iso) {
  const d = new Date(iso);
  return d.getHours() * 60 + d.getMinutes() + d.getSeconds() / 60;
}

function pct(min) {
  return Math.max(0, Math.min(100, ((min - TL_START_MIN) / TL_SPAN_MIN) * 100));
}

function renderStatus() {
  const place = DATA.place;
  const on = !!(DATA.at_work || DATA.at_office);
  document.getElementById('statusDot').classList.toggle('on', on);
  let txt = 'Fora da rede de trabalho';
  if (place === 'home') txt = 'Em casa agora';
  else if (place === 'office' || DATA.at_office) txt = 'No escritório agora';
  else if (DATA.at_work) txt = 'Na rede de trabalho agora';
  document.getElementById('statusText').textContent = txt;
  const gen = DATA.generated_at ? new Date(DATA.generated_at).toLocaleString('pt-BR') : '—';
  document.getElementById('generatedAt').textContent = 'Atualizado: ' + gen;
}

function ensureDays() {
  const sel = document.getElementById('daySelect');
  const prev = selectedDay || sel.value || DATA.today;
  sel.innerHTML = '';
  (DATA.days || []).forEach(d => {
    const opt = document.createElement('option');
    opt.value = d;
    opt.textContent = d === DATA.today ? d + ' (hoje)' : d;
    sel.appendChild(opt);
  });
  if (DATA.days.includes(prev)) selectedDay = prev;
  else selectedDay = DATA.today;
  sel.value = selectedDay;

  if (!daysWired) {
    sel.addEventListener('change', () => {
      selectedDay = sel.value;
      aptoLocked = false;
      renderDay(selectedDay);
      loadApontamentos(true);
    });
    document.getElementById('btnToday').addEventListener('click', () => {
      selectedDay = DATA.today;
      sel.value = selectedDay;
      aptoLocked = false;
      renderDay(selectedDay);
      loadApontamentos(true);
    });
    document.getElementById('btnRefresh').addEventListener('click', () => loadData(true));
    document.getElementById('btnConfirmApto').addEventListener('click', () => confirmarApontamentos());
    document.getElementById('btnDistribuirWifi').addEventListener('click', () => distribuirWifi());
    document.getElementById('btnUnificarAssuntos').addEventListener('click', () => unificarAssuntosSelecionados());
    document.getElementById('btnAddManual').addEventListener('click', () => adicionarAssuntoManual());
    document.getElementById('btnSalvarAlmoco').addEventListener('click', () => salvarAlmoco());
    document.getElementById('btnSalvarWifi').addEventListener('click', () => salvarWifiPresenca());
    document.getElementById('btnWifiAuto').addEventListener('click', () => limparWifiPresenca());
    document.getElementById('btnAddTrabalho').addEventListener('click', () => adicionarLinhaTrabalho());
    daysWired = true;
  }
}

function renderDay(day) {
  const d = DATA.by_day[day];
  if (!d) return;

  document.getElementById('kpis').innerHTML = `
    <div class="kpi"><div class="label">Trabalho</div><div class="value">${esc(d.wifi_label || '—')}</div><div class="sub">${esc(d.first_in || '—')} → ${esc(d.last_out || '—')}</div></div>
    <div class="kpi"><div class="label">Tempo nas janelas</div><div class="value">${esc(d.wifi_total || '0min')}</div><div class="sub">${d.wifi.length} bloco(s)${(d.almoco && d.almoco_sec) ? ` · −almoço ${esc(d.almoco.dur || '')}` : ''}</div></div>
    <div class="kpi"><div class="label">Assuntos</div><div class="value">${d.topics.length}</div><div class="sub">total ${esc(d.topic_total || '0min')}</div></div>
    <div class="kpi"><div class="label">Gateway</div><div class="value" style="font-size:1rem;font-family:var(--mono)">${esc(DATA.last_gateway || '—')}</div><div class="sub">SSID ${esc(DATA.last_ssid || '—')} · ${esc((DATA.last_check || '').slice(11,19) || '—')}</div></div>
  `;

  const tl = document.getElementById('timeline');
  tl.innerHTML = '';
  (d.wifi || []).forEach(iv => {
    const left = pct(minutesOfDay(iv.start));
    const right = pct(minutesOfDay(iv.end));
    if (right <= left) return;
    const el = document.createElement('div');
    el.className = 'seg wifi';
    el.style.left = left + '%';
    el.style.width = Math.max(0.35, right - left) + '%';
    el.title = `${iv.start_hm}–${iv.end_hm} (${iv.dur}) ${iv.label || ''}`;
    tl.appendChild(el);
  });
  (d.topics || []).forEach(iv => {
    const left = pct(minutesOfDay(iv.start));
    const right = pct(minutesOfDay(iv.end));
    if (right <= left) return;
    const el = document.createElement('div');
    el.className = 'seg topic';
    el.style.left = left + '%';
    el.style.width = Math.max(0.35, right - left) + '%';
    el.title = `${iv.start_hm}–${iv.end_hm} · ${iv.label}`;
    tl.appendChild(el);
  });

  fillWifiPresencaInputs(d);
}

function fillWifiPresencaInputs(dayData) {
  const wp = (dayData && dayData.wifi_presenca) || {};
  const det = wp.detectado || {};
  const msg = document.getElementById('wifiPresencaMsg');
  const hint = document.getElementById('wifiDetectadoHint');
  const rows = (wp.intervalos && wp.intervalos.length)
    ? wp.intervalos
    : ((det.intervalos && det.intervalos.length)
      ? det.intervalos
      : ((wp.inicio && wp.fim) ? [{ inicio: wp.inicio, fim: wp.fim, label: '' }] : []));
  renderTrabalhoEditor(rows);

  const detRows = det.intervalos || [];
  if (hint) {
    if (detRows.length) {
      hint.textContent = 'Sugestão Wi‑Fi: ' + detRows.map(x => `${x.inicio}–${x.fim}${x.label ? ' (' + x.label + ')' : ''}`).join(' · ');
    } else if (det.inicio || det.fim) {
      hint.textContent = `Sugestão Wi‑Fi: ${det.inicio || '—'}→${det.fim || '—'}`;
    } else {
      hint.textContent = 'Sem detecção Wi‑Fi — informe as janelas manualmente (escritório/casa).';
    }
  }
  if (msg) {
    if (wp.manual) {
      msg.textContent = `manual (${(wp.intervalos || []).length || 1} janela(s))`;
    } else if (detRows.length || det.inicio) {
      msg.textContent = 'usando automático (Wi‑Fi)';
    } else {
      msg.textContent = 'sem janelas';
    }
  }
}

function renderTrabalhoEditor(rows) {
  const wrap = document.getElementById('trabalhoIntervalos');
  if (!wrap) return;
  const list = (rows && rows.length) ? rows : [{ inicio: '', fim: '', label: '' }];
  const timeStyle = 'background:var(--bg2);color:var(--text);border:1px solid var(--line);border-radius:8px;padding:8px 10px;font-family:var(--mono)';
  const textStyle = 'flex:1;min-width:120px;background:var(--bg2);color:var(--text);border:1px solid var(--line);border-radius:8px;padding:8px 10px';
  wrap.innerHTML = list.map((r, i) => `
    <div class="trabalho-row" data-i="${i}" style="display:flex;flex-wrap:wrap;gap:8px;align-items:center">
      <input class="tr-ini" type="time" value="${esc(r.inicio || '')}" style="${timeStyle}" />
      <span class="meta">até</span>
      <input class="tr-fim" type="time" value="${esc(r.fim || '')}" style="${timeStyle}" />
      <input class="tr-label" type="text" placeholder="Ex.: Liber / Casa" value="${esc(r.label || '')}" style="${textStyle}" />
      <button type="button" class="tr-del" data-i="${i}" style="padding:6px 8px;font-size:.78rem">Remover</button>
    </div>`).join('');
  wrap.querySelectorAll('.tr-del').forEach(btn => {
    btn.addEventListener('click', () => {
      const cur = collectTrabalhoIntervalos();
      const idx = Number(btn.getAttribute('data-i'));
      cur.splice(idx, 1);
      renderTrabalhoEditor(cur.length ? cur : [{ inicio: '', fim: '', label: '' }]);
    });
  });
}

function collectTrabalhoIntervalos() {
  const rows = [];
  document.querySelectorAll('#trabalhoIntervalos .trabalho-row').forEach(row => {
    rows.push({
      inicio: (row.querySelector('.tr-ini') || {}).value || '',
      fim: (row.querySelector('.tr-fim') || {}).value || '',
      label: (row.querySelector('.tr-label') || {}).value || '',
    });
  });
  return rows;
}

function adicionarLinhaTrabalho() {
  const cur = collectTrabalhoIntervalos();
  cur.push({ inicio: '', fim: '', label: '' });
  renderTrabalhoEditor(cur);
}

async function salvarWifiPresenca() {
  const err = document.getElementById('errBox');
  const info = document.getElementById('wifiPresencaMsg');
  const day = selectedDay || (DATA && DATA.today);
  if (!day) return;
  const intervalos = collectTrabalhoIntervalos().filter(x => x.inicio && x.fim);
  try {
    const res = await fetch('/api/wifi-presenca', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ day, intervalos }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || ('HTTP ' + res.status));
    aptoLocked = false;
    info.textContent = `Salvo: ${(data.intervalos || []).length} janela(s)`;
    if (err) err.hidden = true;
    await loadData(true);
  } catch (e) {
    if (err) {
      err.hidden = false;
      err.textContent = 'Falha ao salvar janelas: ' + e.message;
    }
  }
}

async function limparWifiPresenca() {
  const err = document.getElementById('errBox');
  const info = document.getElementById('wifiPresencaMsg');
  const day = selectedDay || (DATA && DATA.today);
  if (!day) return;
  if (!confirm('Usar as janelas detectadas pelo Wi‑Fi (escritório/casa) neste dia?')) return;
  try {
    const res = await fetch('/api/wifi-presenca', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ day, clear: true }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || ('HTTP ' + res.status));
    aptoLocked = false;
    info.textContent = 'Usando detecção automática (Wi‑Fi)';
    if (err) err.hidden = true;
    await loadData(true);
  } catch (e) {
    if (err) {
      err.hidden = false;
      err.textContent = 'Falha ao usar automático: ' + e.message;
    }
  }
}


function fillAlmocoInputs() {
  if (!APTO || !APTO.almoco) return;
  const ini = document.getElementById('almocoInicio');
  const fim = document.getElementById('almocoFim');
  if (ini) ini.value = APTO.almoco.inicio || '12:10';
  if (fim) fim.value = APTO.almoco.fim || '13:00';
}

async function salvarAlmoco() {
  const err = document.getElementById('aptoErr');
  const info = document.getElementById('almocoMsg');
  const day = selectedDay || (DATA && DATA.today);
  const inicio = document.getElementById('almocoInicio').value;
  const fim = document.getElementById('almocoFim').value;
  if (!day) return;
  try {
    const res = await fetch('/api/almoco', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ day, inicio, fim }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || ('HTTP ' + res.status));
    if (APTO) APTO.almoco = { inicio: data.inicio, fim: data.fim };
    aptoLocked = false;
    info.textContent = `Salvo: ${data.inicio}–${data.fim}`;
    err.hidden = true;
    await loadData(true);
    await loadApontamentos(true);
  } catch (e) {
    err.hidden = false;
    err.textContent = 'Falha ao salvar almoço: ' + e.message;
  }
}

function draftHm(r, which) {
  if (which === 'ini') return r.hora_inicio_hm || String(r.hora_inicio || '').slice(0, 5);
  return r.hora_fim_hm || String(r.hora_fim || '').slice(0, 5);
}

function classifyAptoPausa(iniMin, fimMin) {
  const alm = (APTO && APTO.almoco) || {};
  const a0 = parseHmToMinutes(alm.inicio || '');
  const a1 = parseHmToMinutes(alm.fim || '');
  const overlap = (a0 != null && a1 != null)
    ? Math.min(fimMin, a1) - Math.max(iniMin, a0)
    : 0;
  if (overlap >= 10) {
    const hi = minutesToHm(Math.max(iniMin, a0));
    const hf = minutesToHm(Math.min(fimMin, a1));
    return {
      kind: 'almoco',
      tag: 'Almoço',
      text: `Pausa sem trabalho · almoço ${hi}–${hf}`,
    };
  }
  return {
    kind: 'pausa',
    tag: 'Pausa',
    text: `Pausa sem trabalho · ${minutesToHm(iniMin)}–${minutesToHm(fimMin)}`,
  };
}

function renderAptoPausaRow(iniMin, fimMin) {
  const info = classifyAptoPausa(iniMin, fimMin);
  const dur = fmtDurSec((fimMin - iniMin) * 60);
  const cls = info.kind === 'almoco' ? 'apto-pausa apto-pausa-almoco' : 'apto-pausa';
  return `
    <tr class="${cls}" aria-label="${esc(info.text)}">
      <td colspan="6">
        <div class="apto-pausa-label">
          <span class="apto-pausa-tag">${esc(info.tag)}</span>
          <span>${esc(info.text)}</span>
          <span>${esc(dur)}</span>
        </div>
      </td>
    </tr>`;
}

function renderApontamentos() {
  const wrap = document.getElementById('aptoTableWrap');
  fillAlmocoInputs();
  aptoLoading = false;
  setAptoButtonsDisabled(false);
  if (!APTO) {
    showAptoLoading('Carregando assuntos…');
    return;
  }
  if (!APTO.drafts.length) {
    wrap.innerHTML = '<div class="empty">Nenhum assunto neste dia.</div>';
    return;
  }

  const defDigits = String(APTO.default_codigo_chamado || '').replace(/^CHA-?/i, '');
  const rowsHtml = [];
  APTO.drafts.forEach((r, i) => {
    if (i > 0) {
      const prev = APTO.drafts[i - 1];
      const prevEnd = parseHmToMinutes(draftHm(prev, 'fim'));
      const curIni = parseHmToMinutes(draftHm(r, 'ini'));
      if (prevEnd != null && curIni != null && curIni - prevEnd >= 5) {
        rowsHtml.push(renderAptoPausaRow(prevEnd, curIni));
      }
    }
    const digits = (r.codigo_chamado || defDigits || '').replace(/^CHA-?/i,'');
    const bloqueado = !!(r.already_sent || r.invalido_las);
    const hint = r.already_sent
      ? ' <span class="meta">(já apontado)</span>'
      : (r.invalido_las
        ? ` <span class="meta">(${esc(r.skip_reason || 'inválido LAS')})</span>`
        : (r.manual
          ? ' <span class="meta">(manual)</span>'
          : (r.hora_editada
            ? ' <span class="meta">(horário editado)</span>'
            : (String(r.id || '').includes('-resto-') ? ' <span class="meta">(restante)</span>' : ''))));
    const delBtn = bloqueado
      ? ''
      : `<button type="button" class="apto-del-assunto" data-i="${i}" data-mid="${esc(r.manual_id || '')}" style="padding:6px 8px;font-size:.78rem">Excluir</button>`;
    const hi = esc(draftHm(r, 'ini'));
    const hf = esc(draftHm(r, 'fim'));
    rowsHtml.push(`
      <tr style="border-top:1px solid var(--line);opacity:${bloqueado ? '.55' : '1'}">
        <td class="apto-col-ok" style="padding:10px 6px"><input type="checkbox" data-i="${i}" class="apto-sel" ${(!bloqueado && (r.selected || digits)) ? 'checked' : ''} ${bloqueado ? 'disabled' : ''}></td>
        <td class="apto-col-hora" style="padding:10px 6px">
          <div class="apto-horarios">
            <input data-i="${i}" class="apto-hi" type="text" inputmode="numeric" placeholder="HH:MM" maxlength="5" value="${hi}" ${bloqueado ? 'disabled' : ''}>
            <span class="meta">–</span>
            <input data-i="${i}" class="apto-hf" type="text" inputmode="numeric" placeholder="HH:MM" maxlength="5" value="${hf}" ${bloqueado ? 'disabled' : ''}>
          </div>
        </td>
        <td class="apto-col-dur apto-dur" data-i="${i}" style="padding:10px 6px">${esc(r.dur)}</td>
        <td class="apto-col-assunto" style="padding:10px 6px">
          <input data-i="${i}" class="apto-assunto-input" type="text"
            value="${esc(r.assunto || '')}"
            data-original="${esc(r.assunto || '')}"
            data-label-base="${esc(r.label_base || '')}"
            ${bloqueado ? 'disabled' : ''}>${hint}
        </td>
        <td class="apto-col-cha" style="padding:10px 6px">
          <div style="display:flex;align-items:center;background:var(--bg2);border:1px solid var(--line);border-radius:8px;overflow:hidden;max-width:150px">
            <span style="padding:7px 8px;color:var(--muted);font-family:var(--mono);font-size:.82rem;border-right:1px solid var(--line)">CHA-</span>
            <input data-i="${i}" class="apto-cha" type="text" inputmode="numeric" placeholder="2761"
              value="${esc(digits)}"
              style="width:88px;background:transparent;color:var(--text);border:0;padding:8px 10px;font-family:var(--mono)" ${bloqueado ? 'disabled' : ''}>
          </div>
        </td>
        <td class="apto-col-act" style="padding:10px 6px">${delBtn}</td>
      </tr>`);
  });

  wrap.innerHTML = `
    <table>
      <thead>
        <tr style="text-align:left;color:var(--muted)">
          <th class="apto-col-ok" style="padding:8px 6px">OK</th>
          <th class="apto-col-hora" style="padding:8px 6px">Horário</th>
          <th class="apto-col-dur" style="padding:8px 6px">Dur</th>
          <th class="apto-col-assunto" style="padding:8px 6px">Assunto</th>
          <th class="apto-col-cha" style="padding:8px 6px">Chamado</th>
          <th class="apto-col-act" style="padding:8px 6px"></th>
        </tr>
      </thead>
      <tbody>
        ${rowsHtml.join('')}
      </tbody>
    </table>`;
  wireChaInputs();
  wireHoraInputs();
  wireAssuntoEdits();
}

function normalizeCodigoInput(v) {
  const s = String(v || '').trim().toUpperCase();
  if (!s) return null;
  const m = s.match(/(?:CHA[\s\-_]*)?(\d{1,6})/);
  if (!m) return null;
  const n = Number(m[1]);
  if (n < 1000) return 'CHA-' + String(n).padStart(4, '0');
  return 'CHA-' + n;
}

function digitsOnlyCha(v) {
  const cod = normalizeCodigoInput(v);
  return cod ? cod.replace(/^CHA-/, '') : String(v || '').replace(/\D+/g, '');
}

function wireChaInputs() {
  document.querySelectorAll('.apto-cha').forEach(inp => {
    if (inp.dataset.wired) return;
    inp.dataset.wired = '1';
    const sync = () => {
      const digits = digitsOnlyCha(inp.value);
      if (inp.value !== digits) inp.value = digits;
      const i = inp.getAttribute('data-i');
      const cb = document.querySelector(`.apto-sel[data-i="${i}"]`);
      if (cb && !cb.disabled) cb.checked = !!digits;
    };
    inp.addEventListener('input', sync);
    inp.addEventListener('blur', sync);
  });
}

function parseHmToMinutes(v) {
  const s = String(v || '').trim();
  let m = s.match(/^(\d{1,2}):(\d{2})$/);
  if (!m) {
    const d = s.replace(/\D/g, '');
    if (d.length === 3 || d.length === 4) {
      const h = d.length === 3 ? d.slice(0, 1) : d.slice(0, 2);
      const min = d.slice(-2);
      m = [null, h, min];
    }
  }
  if (!m) return null;
  const h = Number(m[1]);
  const min = Number(m[2]);
  if (h > 23 || min > 59) return null;
  return h * 60 + min;
}

function roundMinutesToFive(totalMin) {
  let m = Math.round(Number(totalMin) / 5) * 5;
  if (m >= 24 * 60) m = 23 * 60 + 55;
  if (m < 0) m = 0;
  return m;
}

function minutesToHm(totalMin) {
  const h = Math.floor(totalMin / 60);
  const m = totalMin % 60;
  return String(h).padStart(2, '0') + ':' + String(m).padStart(2, '0');
}

function fmtDurSec(sec) {
  sec = Math.max(0, Math.floor(Number(sec) || 0));
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  if (h && m) return h + 'h' + String(m).padStart(2, '0');
  if (h) return h + 'h';
  return m + 'min';
}

function applyDraftHoraEdit(i, roundOnBlur) {
  if (!APTO || !APTO.drafts[i]) return;
  const hiEl = document.querySelector(`.apto-hi[data-i="${i}"]`);
  const hfEl = document.querySelector(`.apto-hf[data-i="${i}"]`);
  const durEl = document.querySelector(`.apto-dur[data-i="${i}"]`);
  const err = document.getElementById('aptoErr');
  if (!hiEl || !hfEl) return;

  let iniMin = parseHmToMinutes(hiEl.value);
  let fimMin = parseHmToMinutes(hfEl.value);
  if (iniMin == null || fimMin == null) {
    if (err) {
      err.hidden = false;
      err.textContent = 'Horário inválido na linha ' + (Number(i) + 1);
    }
    return;
  }

  if (roundOnBlur) {
    iniMin = roundMinutesToFive(iniMin);
    fimMin = roundMinutesToFive(fimMin);
    hiEl.value = minutesToHm(iniMin);
    hfEl.value = minutesToHm(fimMin);
  }

  if (fimMin <= iniMin) {
    if (err) {
      err.hidden = false;
      err.textContent = 'Linha ' + (Number(i) + 1) + ': hora fim deve ser maior que início';
    }
    return;
  }

  const hi = minutesToHm(iniMin);
  const hf = minutesToHm(fimMin);
  const seconds = (fimMin - iniMin) * 60;
  const row = APTO.drafts[i];
  row.hora_inicio = hi + ':00';
  row.hora_fim = hf + ':00';
  row.hora_inicio_hm = hi;
  row.hora_fim_hm = hf;
  row.seconds = seconds;
  row.minutes = Math.max(1, Math.floor(seconds / 60));
  row.dur = fmtDurSec(seconds);
  row.hora_editada = true;
  if (durEl) durEl.textContent = row.dur;
  aptoLocked = true;
  if (err) err.hidden = true;
}

function wireHoraInputs() {
  document.querySelectorAll('.apto-hi, .apto-hf').forEach(inp => {
    if (inp.dataset.wired) return;
    inp.dataset.wired = '1';
    const i = inp.getAttribute('data-i');
    inp.addEventListener('change', () => applyDraftHoraEdit(i, false));
    inp.addEventListener('blur', () => applyDraftHoraEdit(i, true));
  });
}

function wireAssuntoEdits() {
  document.querySelectorAll('.apto-assunto-input').forEach(inp => {
    if (inp.dataset.wired) return;
    inp.dataset.wired = '1';
    inp.addEventListener('keydown', (ev) => {
      if (ev.key === 'Enter') { ev.preventDefault(); inp.blur(); }
    });
    inp.addEventListener('blur', () => salvarRenameAssunto(inp));
  });
  document.querySelectorAll('.apto-del-assunto').forEach(btn => {
    if (btn.dataset.wired) return;
    btn.dataset.wired = '1';
    btn.addEventListener('click', () => {
      const i = Number(btn.getAttribute('data-i'));
      const mid = btn.getAttribute('data-mid') || '';
      excluirAssuntoLinha(i, mid);
    });
  });
}

async function refreshAssuntosAposEdicao(msgText) {
  const info = document.getElementById('aptoMsg');
  const err = document.getElementById('aptoErr');
  aptoLocked = false;
  if (err) err.hidden = true;
  if (info) {
    info.hidden = false;
    info.textContent = msgText || 'Assuntos atualizados';
  }
  await loadData(true);
  await loadApontamentos(true, 'Atualizando assuntos…');
}

async function salvarRenameAssunto(inp) {
  const err = document.getElementById('aptoErr');
  const i = Number(inp.getAttribute('data-i'));
  const original = String(inp.getAttribute('data-original') || '');
  const novo = String(inp.value || '').trim();
  if (!novo) {
    inp.value = original;
    return;
  }
  if (novo === original.trim()) return;
  const fromLabel = String(inp.getAttribute('data-label-base') || original).trim() || original;
  const day = selectedDay || (DATA && DATA.today);
  if (!day) return;
  try {
    const res = await fetch('/api/assuntos-edits', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ day, action: 'rename', from: fromLabel, to: novo }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || ('HTTP ' + res.status));
    if (APTO && APTO.drafts[i]) {
      APTO.drafts[i].assunto = novo;
      APTO.drafts[i].label_base = novo.replace(/\s*\(restante\)\s*$/i, '').trim();
    }
    await refreshAssuntosAposEdicao(`Assunto renomeado: ${novo}`);
  } catch (e) {
    inp.value = original;
    if (err) {
      err.hidden = false;
      err.textContent = 'Falha ao renomear: ' + e.message;
    }
  }
}

async function excluirAssuntoLinha(i, manualId) {
  const err = document.getElementById('aptoErr');
  const day = selectedDay || (DATA && DATA.today);
  if (!day || !APTO || !APTO.drafts[i]) return;
  const row = APTO.drafts[i];
  const label = row.assunto || row.label_base || '';
  if (!confirm('Excluir o assunto "' + label + '"?')) return;
  try {
    let res;
    if (manualId) {
      res = await fetch('/api/assuntos-manuais', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ day, id: manualId, delete: true }),
      });
    } else {
      res = await fetch('/api/assuntos-edits', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ day, action: 'delete', label, id: row.id || '' }),
      });
    }
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || ('HTTP ' + res.status));
    await refreshAssuntosAposEdicao('Assunto excluído');
  } catch (e) {
    if (err) {
      err.hidden = false;
      err.textContent = 'Falha ao excluir: ' + e.message;
    }
  }
}

async function unificarAssuntosSelecionados() {
  const err = document.getElementById('aptoErr');
  const day = selectedDay || (DATA && DATA.today);
  if (!day || !APTO) return;
  const selected = [];
  document.querySelectorAll('.apto-sel:checked').forEach(cb => {
    const i = Number(cb.getAttribute('data-i'));
    const row = APTO.drafts[i];
    if (!row || row.already_sent || row.invalido_las) return;
    const inp = document.querySelector(`.apto-assunto-input[data-i="${i}"]`);
    const label = (inp && inp.value) || row.assunto || '';
    selected.push({ i, label, base: row.label_base || label });
  });
  const bases = [];
  selected.forEach(s => {
    const b = String(s.base || s.label || '').replace(/\s*\(restante\)\s*$/i, '').trim();
    if (b && !bases.includes(b)) bases.push(b);
  });
  if (bases.length < 2) {
    if (err) {
      err.hidden = false;
      err.textContent = 'Selecione ao menos 2 assuntos distintos (OK) para unificar.';
    }
    return;
  }
  const sugerido = bases[0];
  const nome = prompt('Nome do assunto unificado:', sugerido);
  if (nome == null) return;
  const novo = String(nome).trim();
  if (!novo) {
    if (err) {
      err.hidden = false;
      err.textContent = 'Informe um nome para o assunto unificado.';
    }
    return;
  }
  const chaInp = document.querySelector('.apto-cha:not(:disabled)');
  const codigo = normalizeCodigoInput(chaInp ? chaInp.value : (APTO.default_codigo_chamado || ''));
  showAptoLoading('Unificando assuntos…');
  try {
    const res = await fetch('/api/assuntos-edits', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ day, action: 'unify', labels: bases, to: novo, codigo_chamado: codigo }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || ('HTTP ' + res.status));
    await refreshAssuntosAposEdicao(`Unificados em: ${novo}`);
  } catch (e) {
    aptoLoading = false;
    setAptoButtonsDisabled(false);
    if (APTO) renderApontamentos();
    if (err) {
      err.hidden = false;
      err.textContent = 'Falha ao unificar: ' + e.message;
    }
  }
}


async function adicionarAssuntoManual() {
  const err = document.getElementById('aptoErr');
  const info = document.getElementById('manualMsg');
  const day = selectedDay || (DATA && DATA.today);
  if (!day) return;
  const inicio = document.getElementById('manualInicio').value;
  const fim = document.getElementById('manualFim').value;
  const assunto = document.getElementById('manualAssunto').value;
  const chaDigits = document.getElementById('manualCha').value;
  const codigo = normalizeCodigoInput(chaDigits);
  try {
    const res = await fetch('/api/assuntos-manuais', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ day, inicio, fim, assunto, codigo_chamado: codigo }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || ('HTTP ' + res.status));
    err.hidden = true;
    info.textContent = `Adicionado: ${data.inicio}–${data.fim}`;
    document.getElementById('manualAssunto').value = '';
    aptoLocked = false;
    await loadData(true);
    await loadApontamentos(true, 'Atualizando assuntos…');
  } catch (e) {
    err.hidden = false;
    err.textContent = 'Falha ao adicionar assunto: ' + e.message;
    info.textContent = '';
  }
}

async function excluirAssuntoManual(manualId) {
  const err = document.getElementById('aptoErr');
  const info = document.getElementById('manualMsg');
  const day = selectedDay || (DATA && DATA.today);
  if (!day || !manualId) return;
  if (!confirm('Excluir este assunto manual?')) return;
  try {
    const res = await fetch('/api/assuntos-manuais', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ day, id: manualId, delete: true }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || ('HTTP ' + res.status));
    err.hidden = true;
    info.textContent = 'Assunto manual removido';
    aptoLocked = false;
    await loadData(true);
    await loadApontamentos(true, 'Atualizando assuntos…');
  } catch (e) {
    err.hidden = false;
    err.textContent = 'Falha ao excluir: ' + e.message;
  }
}

function collectSelectedRows() {
  if (!APTO) return [];
  const rows = [];
  document.querySelectorAll('.apto-sel').forEach(cb => {
    if (!cb.checked) return;
    const i = Number(cb.getAttribute('data-i'));
    const base = APTO.drafts[i];
    const cha = document.querySelector(`.apto-cha[data-i="${i}"]`);
    const hiEl = document.querySelector(`.apto-hi[data-i="${i}"]`);
    const hfEl = document.querySelector(`.apto-hf[data-i="${i}"]`);
    const codigo = normalizeCodigoInput(cha ? cha.value : '');
    applyDraftHoraEdit(i, true);
    const horaInicio = (hiEl && hiEl.value) ? (hiEl.value.length === 5 ? hiEl.value + ':00' : hiEl.value) : base.hora_inicio;
    const horaFim = (hfEl && hfEl.value) ? (hfEl.value.length === 5 ? hfEl.value + ':00' : hfEl.value) : base.hora_fim;
    const assuntoInp = document.querySelector(`.apto-assunto-input[data-i="${i}"]`);
    const assunto = (assuntoInp && assuntoInp.value.trim()) || base.assunto;
    rows.push({
      data_trabalho: base.data_trabalho,
      hora_inicio: horaInicio,
      hora_fim: horaFim,
      codigo_chamado: codigo,
      usuario_gestao_id: APTO.usuario_gestao_id,
      assunto: assunto,
    });
  });
  return rows;
}

function selectAllApto() {
  document.querySelectorAll('.apto-sel:not(:disabled)').forEach(cb => { cb.checked = true; });
}

function applyDefaultCha() {
  const def = normalizeCodigoInput(document.getElementById('aptoDefaultCha').value);
  if (!def) {
    document.getElementById('aptoErr').hidden = false;
    document.getElementById('aptoErr').textContent = 'Informe um chamado padrão no formato CHA-XXXX';
    return;
  }
  const num = def.replace(/^CHA-/, '');
  document.querySelectorAll('.apto-cha:not(:disabled)').forEach(inp => {
    if (!String(inp.value || '').trim()) inp.value = num;
  });
  document.querySelectorAll('.apto-sel:not(:disabled)').forEach(cb => {
    const i = cb.getAttribute('data-i');
    const inp = document.querySelector(`.apto-cha[data-i="${i}"]`);
    if (inp && String(inp.value || '').trim()) cb.checked = true;
  });
  document.getElementById('aptoErr').hidden = true;
}

async function loadApontamentos(force, loadingText) {
  const err = document.getElementById('aptoErr');
  const day = selectedDay || (DATA && DATA.today);
  if (!day) return;
  if (aptoLocked && !force) return;
  const showLoading = force || !APTO || !!loadingText;
  if (showLoading) showAptoLoading(loadingText || 'Carregando assuntos…');
  try {
    const res = await fetch('/api/apontamentos?day=' + encodeURIComponent(day) + '&t=' + Date.now(), { cache: 'no-store' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || ('HTTP ' + res.status));
    APTO = data;
    err.hidden = true;
    renderApontamentos();
  } catch (e) {
    aptoLoading = false;
    setAptoButtonsDisabled(false);
    err.hidden = false;
    err.textContent = 'Falha ao montar rascunho: ' + e.message;
    if (showLoading) {
      const wrap = document.getElementById('aptoTableWrap');
      if (wrap) wrap.innerHTML = '<div class="empty">Não foi possível carregar os assuntos.</div>';
    }
  }
}

async function distribuirWifi() {
  const err = document.getElementById('aptoErr');
  const msg = document.getElementById('aptoMsg');
  const day = selectedDay || (DATA && DATA.today);
  if (!day) return;
  if (!confirm('Redistribuir os assuntos para preencher o tempo das janelas de trabalho (proporcional, respeitando almoço e lacunas)?')) return;
  if (msg) { msg.hidden = false; msg.textContent = 'Distribuindo tempo de trabalho…'; }
  if (err) err.hidden = true;
  showAptoLoading('Distribuindo tempo de trabalho…');
  try {
    const res = await fetch('/api/apontamentos/distribuir', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ day }),
    });
    const data = await res.json();
    if (!res.ok && data.error) throw new Error(data.error);
    APTO = data;
    if (data.distribuicao && data.distribuicao.ok) aptoLocked = true;
    renderApontamentos();
    const dist = data.distribuicao || {};
    if (dist.ok) {
      err.hidden = true;
      msg.hidden = false;
      msg.textContent = dist.message || 'Distribuição aplicada';
    } else {
      err.hidden = false;
      err.textContent = dist.message || 'Não foi possível distribuir';
      msg.hidden = true;
    }
  } catch (e) {
    aptoLoading = false;
    setAptoButtonsDisabled(false);
    err.hidden = false;
    err.textContent = 'Falha na distribuição: ' + e.message;
    if (msg) msg.hidden = true;
    if (APTO) renderApontamentos();
    else {
      const wrap = document.getElementById('aptoTableWrap');
      if (wrap) wrap.innerHTML = '<div class="empty">Falha na distribuição. Tente novamente.</div>';
    }
  }
}

async function confirmarApontamentos() {
  const err = document.getElementById('aptoErr');
  const msg = document.getElementById('aptoMsg');
  const rows = collectSelectedRows();
  if (!rows.length) {
    err.hidden = false;
    err.textContent = 'Selecione ao menos uma linha.';
    return;
  }
  if (!confirm(`Confirmar ${rows.length} apontamento(s)?`)) return;
  showAptoLoading('Confirmando apontamentos…');
  try {
    const res = await fetch('/api/apontamentos/confirmar', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rows }),
    });
    const data = await res.json();
    err.hidden = !(data.errors && data.errors.length);
    err.textContent = (data.errors || []).join(' | ');
    msg.hidden = false;
    if (data.dry_run) {
      msg.textContent = (data.message || '') + ' — nada foi gravado no LAS.';
    } else if (data.ok) {
      msg.textContent = data.message || 'Apontamento gravado no LAS.';
    } else {
      msg.textContent = data.message || 'Falha ao gravar';
    }
    if (data.ok) {
      setTimeout(() => { msg.hidden = true; }, 4000);
      aptoLocked = false;
      await loadApontamentos(true, 'Atualizando assuntos…');
    } else {
      renderApontamentos();
    }
  } catch (e) {
    err.hidden = false;
    err.textContent = 'Falha ao confirmar: ' + e.message;
    renderApontamentos();
  }
}

async function loadData(force) {
  const err = document.getElementById('errBox');
  try {
    const res = await fetch('/api/data?t=' + Date.now(), { cache: 'no-store' });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    DATA = await res.json();
    err.hidden = true;
    renderStatus();
    ensureDays();
    renderDay(selectedDay || DATA.today);
    if (force) await loadApontamentos(true, 'Carregando assuntos…');
    else await loadApontamentos();
  } catch (e) {
    err.hidden = false;
    err.textContent = 'Falha ao ler dados ao vivo: ' + e.message;
  }
}

loadData(true);
setInterval(() => loadData(false), REFRESH_MS);
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        if args and str(args[0]).startswith(("4", "5")):
            super().log_message(fmt, *args)

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8") or "{}")

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        if path in ("/", "/index.html", "/dashboard"):
            body = LIVE_HTML.encode("utf-8")
            self._send(200, body, "text/html; charset=utf-8")
            return
        if path == "/api/data":
            try:
                data = bd.build_data()
                body = json.dumps(data, ensure_ascii=False).encode("utf-8")
                self._send(200, body, "application/json; charset=utf-8")
            except Exception as exc:
                body = json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8")
                self._send(500, body, "application/json; charset=utf-8")
            return
        if path == "/api/apontamentos":
            try:
                import apontamentos as ap

                qs = parse_qs(parsed.query)
                day_s = (qs.get("day") or [None])[0]
                day = date.fromisoformat(day_s) if day_s else datetime.now().astimezone().date()
                data = ap.build_drafts_for_day(day)
                body = json.dumps(data, ensure_ascii=False).encode("utf-8")
                self._send(200, body, "application/json; charset=utf-8")
            except Exception as exc:
                body = json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8")
                self._send(500, body, "application/json; charset=utf-8")
            return
        if path == "/api/apontamentos/buscar":
            try:
                import apontamentos as ap

                qs = parse_qs(parsed.query)
                q = (qs.get("q") or [""])[0]
                data = {"items": ap.buscar_chamados(q)}
                body = json.dumps(data, ensure_ascii=False).encode("utf-8")
                self._send(200, body, "application/json; charset=utf-8")
            except Exception as exc:
                body = json.dumps({"error": str(exc), "items": []}, ensure_ascii=False).encode("utf-8")
                self._send(400, body, "application/json; charset=utf-8")
            return
        self._send(404, b'{"error":"not found"}', "application/json; charset=utf-8")

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/almoco":
            try:
                import apontamentos as ap

                payload = self._read_json()
                day_s = payload.get("day")
                day = date.fromisoformat(day_s) if day_s else datetime.now().astimezone().date()
                result = ap.save_almoco_dia(day, payload.get("inicio") or "", payload.get("fim") or "")
                body = json.dumps(result, ensure_ascii=False).encode("utf-8")
                self._send(200, body, "application/json; charset=utf-8")
            except Exception as exc:
                body = json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8")
                self._send(400, body, "application/json; charset=utf-8")
            return
        if path == "/api/wifi-presenca":
            try:
                payload = self._read_json()
                day_s = payload.get("day")
                day = date.fromisoformat(day_s) if day_s else datetime.now().astimezone().date()
                if payload.get("clear"):
                    result = bd.clear_wifi_presenca_dia(day)
                elif payload.get("intervalos") is not None:
                    result = bd.save_wifi_presenca_dia(
                        day, intervalos=payload.get("intervalos") or []
                    )
                else:
                    result = bd.save_wifi_presenca_dia(
                        day, payload.get("inicio") or "", payload.get("fim") or ""
                    )
                body = json.dumps(result, ensure_ascii=False).encode("utf-8")
                self._send(200, body, "application/json; charset=utf-8")
            except Exception as exc:
                body = json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8")
                self._send(400, body, "application/json; charset=utf-8")
            return
        if path == "/api/assuntos-edits":
            try:
                payload = self._read_json()
                day_s = payload.get("day")
                day = date.fromisoformat(day_s) if day_s else datetime.now().astimezone().date()
                action = str(payload.get("action") or "").strip().lower()
                if action == "rename":
                    result = bd.rename_assunto_auto(
                        day, payload.get("from") or "", payload.get("to") or ""
                    )
                elif action == "delete":
                    result = bd.delete_assunto_auto(
                        day, payload.get("label") or "", payload.get("id") or ""
                    )
                elif action == "unify":
                    result = bd.unify_assuntos_auto(
                        day,
                        payload.get("labels") or [],
                        payload.get("to") or "",
                        payload.get("codigo_chamado"),
                    )
                else:
                    raise ValueError("action inválida (rename|delete|unify)")
                body = json.dumps(result, ensure_ascii=False).encode("utf-8")
                self._send(200, body, "application/json; charset=utf-8")
            except Exception as exc:
                body = json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8")
                self._send(400, body, "application/json; charset=utf-8")
            return
        if path == "/api/assuntos-manuais":
            try:
                payload = self._read_json()
                day_s = payload.get("day")
                day = date.fromisoformat(day_s) if day_s else datetime.now().astimezone().date()
                if payload.get("delete"):
                    result = bd.delete_assunto_manual(day, payload.get("id") or "")
                else:
                    result = bd.add_assunto_manual(
                        day,
                        payload.get("inicio") or "",
                        payload.get("fim") or "",
                        payload.get("assunto") or "",
                        payload.get("codigo_chamado"),
                    )
                body = json.dumps(result, ensure_ascii=False).encode("utf-8")
                self._send(200, body, "application/json; charset=utf-8")
            except Exception as exc:
                body = json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8")
                self._send(400, body, "application/json; charset=utf-8")
            return
        if path == "/api/apontamentos/distribuir":
            try:
                import apontamentos as ap

                payload = self._read_json()
                day_s = payload.get("day")
                day = date.fromisoformat(day_s) if day_s else datetime.now().astimezone().date()
                result = ap.distribuir_tempo_wifi(day)
                body = json.dumps(result, ensure_ascii=False).encode("utf-8")
                self._send(200, body, "application/json; charset=utf-8")
            except Exception as exc:
                body = json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8")
                self._send(500, body, "application/json; charset=utf-8")
            return
        if path == "/api/apontamentos/confirmar":
            try:
                import apontamentos as ap

                payload = self._read_json()
                rows = payload.get("rows") or []
                result = ap.confirmar(rows)
                code = 200 if result.get("ok") else 400
                body = json.dumps(result, ensure_ascii=False).encode("utf-8")
                self._send(code, body, "application/json; charset=utf-8")
            except Exception as exc:
                body = json.dumps({"ok": False, "message": str(exc), "errors": [str(exc)]}, ensure_ascii=False).encode("utf-8")
                self._send(500, body, "application/json; charset=utf-8")
            return
        self._send(404, b'{"error":"not found"}', "application/json; charset=utf-8")


def write_redirect_html(port: int) -> None:
    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8" />
  <meta http-equiv="refresh" content="0;url=http://127.0.0.1:{port}/" />
  <title>Worklog → ao vivo</title>
  <script>location.replace('http://127.0.0.1:{port}/');</script>
</head>
<body style="font-family:sans-serif;background:#0f1419;color:#e8eef6;padding:2rem">
  <p>Abrindo painel ao vivo…</p>
  <p>Se não abrir: <a style="color:#7d00fe" href="http://127.0.0.1:{port}/">http://127.0.0.1:{port}/</a></p>
</body>
</html>
"""
    (WORKLOG_DIR / "dashboard.html").write_text(html, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Painel Worklog ao vivo")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--open", action="store_true", help="abre o navegador")
    args = parser.parse_args()

    write_redirect_html(args.port)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}/"
    print(f"[ok] Worklog ao vivo em {url}", flush=True)
    print(f"     atalho: {WORKLOG_DIR / 'dashboard.html'}", flush=True)

    if args.open:
        subprocess.run(["open", url], check=False)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[stop] servidor encerrado")
    return 0


if __name__ == "__main__":
    sys.exit(main())
