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
  .wrap { max-width: 1100px; margin: 0 auto; padding: 28px 20px 48px; }
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
  .timeline {
    position: relative; height: 54px; border-radius: 10px;
    background: repeating-linear-gradient(
      90deg, var(--bg2) 0, var(--bg2) calc(100%/24 - 1px), var(--line) calc(100%/24 - 1px), var(--line) calc(100%/24)
    );
    overflow: hidden; margin-bottom: 10px;
  }
  .seg {
    position: absolute; top: 10px; height: 34px; border-radius: 8px; opacity: .92;
    min-width: 3px;
  }
  .seg.wifi { background: linear-gradient(90deg, #2563eb, #60a5fa); }
  .seg.topic { background: linear-gradient(90deg, #d97706, #fbbf24); top: 14px; height: 26px; opacity: .85; }
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
      <div style="display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-top:12px">
        <span class="meta">Presença</span>
        <input id="wifiChegada" type="time" style="background:var(--bg2);color:var(--text);border:1px solid var(--line);border-radius:8px;padding:8px 10px;font-family:var(--mono)" />
        <span class="meta">até</span>
        <input id="wifiSaida" type="time" style="background:var(--bg2);color:var(--text);border:1px solid var(--line);border-radius:8px;padding:8px 10px;font-family:var(--mono)" />
        <button type="button" id="btnSalvarWifi">Salvar presença</button>
        <button type="button" id="btnWifiAuto">Usar automático</button>
        <span class="meta" id="wifiPresencaMsg"></span>
      </div>
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
          <button type="button" id="btnDistribuirWifi">Distribuir tempo Wi‑Fi</button>
          <button type="button" id="btnConfirmApto">Confirmar apontamentos</button>
        </div>
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
  const ids = ['btnConfirmApto', 'btnDistribuirWifi'];
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

function minutesOfDay(iso) {
  const d = new Date(iso);
  return d.getHours() * 60 + d.getMinutes() + d.getSeconds() / 60;
}

function pct(min) {
  return Math.max(0, Math.min(100, (min / (24 * 60)) * 100));
}

function renderStatus() {
  const on = !!DATA.at_office;
  document.getElementById('statusDot').classList.toggle('on', on);
  document.getElementById('statusText').textContent = on
    ? 'No escritório agora'
    : 'Fora do escritório';
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
    document.getElementById('btnSalvarAlmoco').addEventListener('click', () => salvarAlmoco());
    document.getElementById('btnSalvarWifi').addEventListener('click', () => salvarWifiPresenca());
    document.getElementById('btnWifiAuto').addEventListener('click', () => limparWifiPresenca());
    daysWired = true;
  }
}

function renderDay(day) {
  const d = DATA.by_day[day];
  if (!d) return;

  document.getElementById('kpis').innerHTML = `
    <div class="kpi"><div class="label">Wi‑Fi</div><div class="value">${esc(d.wifi_label || '—')}</div><div class="sub">${esc(d.first_in || '—')} → ${esc(d.last_out || '—')}</div></div>
    <div class="kpi"><div class="label">Tempo conectado</div><div class="value">${esc(d.wifi_total || '0min')}</div><div class="sub">${d.wifi.length} intervalo(s)</div></div>
    <div class="kpi"><div class="label">Assuntos</div><div class="value">${d.topics.length}</div><div class="sub">total ${esc(d.topic_total || '0min')}</div></div>
    <div class="kpi"><div class="label">Gateway</div><div class="value" style="font-size:1rem;font-family:var(--mono)">${esc(DATA.last_gateway || '—')}</div><div class="sub">último check ${esc((DATA.last_check || '').slice(11,19) || '—')}</div></div>
  `;

  const tl = document.getElementById('timeline');
  tl.innerHTML = '';
  (d.wifi || []).forEach(iv => {
    const a = minutesOfDay(iv.start);
    const b = minutesOfDay(iv.end);
    const el = document.createElement('div');
    el.className = 'seg wifi';
    el.style.left = pct(a) + '%';
    el.style.width = Math.max(0.35, pct(b) - pct(a)) + '%';
    el.title = `${iv.start_hm}–${iv.end_hm} (${iv.dur})`;
    tl.appendChild(el);
  });
  (d.topics || []).forEach(iv => {
    const a = minutesOfDay(iv.start);
    const b = minutesOfDay(iv.end);
    const el = document.createElement('div');
    el.className = 'seg topic';
    el.style.left = pct(a) + '%';
    el.style.width = Math.max(0.35, pct(b) - pct(a)) + '%';
    el.title = `${iv.start_hm}–${iv.end_hm} · ${iv.label}`;
    tl.appendChild(el);
  });

  const wifiList = document.getElementById('wifiList');
  if (!d.wifi.length) {
    wifiList.innerHTML = '<li class="empty">Sem registros de presença neste dia.</li>';
  } else {
    wifiList.innerHTML = d.wifi.map(iv => `
      <li>
        <span class="time">${esc(iv.start_hm)}–${esc(iv.end_hm)}</span>
        <span class="dur">${esc(iv.dur)}</span>
        <span>${esc(iv.label || d.wifi_label || '')}</span>
      </li>`).join('');
  }
  fillWifiPresencaInputs(d);
}

function fillWifiPresencaInputs(dayData) {
  const wp = (dayData && dayData.wifi_presenca) || {};
  const det = wp.detectado || {};
  const ini = document.getElementById('wifiChegada');
  const fim = document.getElementById('wifiSaida');
  const msg = document.getElementById('wifiPresencaMsg');
  if (ini) ini.value = wp.inicio || det.inicio || '';
  if (fim) fim.value = wp.fim || det.fim || '';
  if (msg) {
    if (wp.manual) {
      msg.textContent = `manual ${wp.inicio || '—'}–${wp.fim || '—'} (auto: ${det.inicio || '—'}→${det.fim || '—'})`;
    } else if (det.inicio || det.fim) {
      msg.textContent = `automático ${det.inicio || '—'}→${det.fim || '—'}`;
    } else {
      msg.textContent = 'sem detecção — informe chegada/saída';
    }
  }
}

async function salvarWifiPresenca() {
  const err = document.getElementById('errBox');
  const info = document.getElementById('wifiPresencaMsg');
  const day = selectedDay || (DATA && DATA.today);
  const inicio = document.getElementById('wifiChegada').value;
  const fim = document.getElementById('wifiSaida').value;
  if (!day) return;
  try {
    const res = await fetch('/api/wifi-presenca', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ day, inicio, fim }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || ('HTTP ' + res.status));
    aptoLocked = false;
    info.textContent = `Salvo: ${data.inicio}–${data.fim}`;
    if (err) err.hidden = true;
    await loadData(true);
  } catch (e) {
    if (err) {
      err.hidden = false;
      err.textContent = 'Falha ao salvar presença: ' + e.message;
    }
  }
}

async function limparWifiPresenca() {
  const err = document.getElementById('errBox');
  const info = document.getElementById('wifiPresencaMsg');
  const day = selectedDay || (DATA && DATA.today);
  if (!day) return;
  if (!confirm('Voltar à presença detectada pelo Wi‑Fi neste dia?')) return;
  try {
    const res = await fetch('/api/wifi-presenca', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ day, clear: true }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || ('HTTP ' + res.status));
    aptoLocked = false;
    info.textContent = 'Usando detecção automática';
    if (err) err.hidden = true;
    await loadData(true);
  } catch (e) {
    if (err) {
      err.hidden = false;
      err.textContent = 'Falha ao limpar presença: ' + e.message;
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
    await loadApontamentos(true);
  } catch (e) {
    err.hidden = false;
    err.textContent = 'Falha ao salvar almoço: ' + e.message;
  }
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

  wrap.innerHTML = `
    <table style="width:100%;border-collapse:collapse;font-size:.92rem">
      <thead>
        <tr style="text-align:left;color:var(--muted)">
          <th style="padding:8px 6px;width:44px">OK</th>
          <th style="padding:8px 6px;width:120px">Horário</th>
          <th style="padding:8px 6px;width:70px">Dur</th>
          <th style="padding:8px 6px">Assunto</th>
          <th style="padding:8px 6px;width:150px">Chamado</th>
        </tr>
      </thead>
      <tbody>
        ${APTO.drafts.map((r, i) => {
          const digits = (r.codigo_chamado || defDigits || '').replace(/^CHA-?/i,'');
          const bloqueado = !!(r.already_sent || r.invalido_las);
          const hint = r.already_sent
            ? ' <span class="meta">(já apontado)</span>'
            : (r.invalido_las
              ? ` <span class="meta">(${esc(r.skip_reason || 'inválido LAS')})</span>`
              : (String(r.id || '').includes('-resto-') ? ' <span class="meta">(restante)</span>' : ''));
          return `
          <tr style="border-top:1px solid var(--line);opacity:${bloqueado ? '.55' : '1'}">
            <td style="padding:10px 6px"><input type="checkbox" data-i="${i}" class="apto-sel" ${(!bloqueado && (r.selected || digits)) ? 'checked' : ''} ${bloqueado ? 'disabled' : ''}></td>
            <td style="padding:10px 6px;font-family:var(--mono)">${esc(r.hora_inicio_hm)}–${esc(r.hora_fim_hm)}</td>
            <td style="padding:10px 6px;color:var(--accent2);font-family:var(--mono)">${esc(r.dur)}</td>
            <td style="padding:10px 6px">${esc(r.assunto)}${hint}</td>
            <td style="padding:10px 6px">
              <div style="display:flex;align-items:center;background:var(--bg2);border:1px solid var(--line);border-radius:8px;overflow:hidden;max-width:150px">
                <span style="padding:7px 8px;color:var(--muted);font-family:var(--mono);font-size:.82rem;border-right:1px solid var(--line)">CHA-</span>
                <input data-i="${i}" class="apto-cha" type="text" inputmode="numeric" placeholder="2761"
                  value="${esc(digits)}"
                  style="width:88px;background:transparent;color:var(--text);border:0;padding:8px 10px;font-family:var(--mono)" ${bloqueado ? 'disabled' : ''}>
              </div>
            </td>
          </tr>`;
        }).join('')}
      </tbody>
    </table>`;
  wireChaInputs();
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

function collectSelectedRows() {
  if (!APTO) return [];
  const rows = [];
  document.querySelectorAll('.apto-sel').forEach(cb => {
    if (!cb.checked) return;
    const i = Number(cb.getAttribute('data-i'));
    const base = APTO.drafts[i];
    const cha = document.querySelector(`.apto-cha[data-i="${i}"]`);
    const codigo = normalizeCodigoInput(cha ? cha.value : '');
    rows.push({
      data_trabalho: base.data_trabalho,
      hora_inicio: base.hora_inicio,
      hora_fim: base.hora_fim,
      codigo_chamado: codigo,
      usuario_gestao_id: APTO.usuario_gestao_id,
      assunto: base.assunto,
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
  if (!confirm('Distribuir o tempo de Wi‑Fi sem assunto proporcionalmente entre os assuntos?')) return;
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
    msg.hidden = false;
    if (dist.ok) {
      err.hidden = true;
      msg.textContent = dist.message || 'Distribuição aplicada';
    } else {
      err.hidden = false;
      err.textContent = dist.message || 'Não foi possível distribuir';
      msg.hidden = true;
    }
  } catch (e) {
    err.hidden = false;
    err.textContent = 'Falha na distribuição: ' + e.message;
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
