#!/usr/bin/env python3
"""Rascunho e envio de apontamentos (opção A: revisar → confirmar)."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
WORKLOG_DIR = SCRIPT_DIR.parent
SENT_LOG = WORKLOG_DIR / "logs" / "apontamentos_enviados.jsonl"
ALMOCO_PATH = WORKLOG_DIR / "logs" / "almoco.json"

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import build_dashboard as bd  # noqa: E402
import daily_summary as ds  # noqa: E402


def load_config() -> Dict[str, Any]:
    return ds.load_config()


def apontamento_cfg(cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cfg = cfg or load_config()
    return cfg.get("apontamento") or {}


def _parse_hm(value: str) -> Optional[Tuple[int, int]]:
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


def default_almoco(cfg: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    cfg = cfg or load_config()
    bloco = cfg.get("almoco") or {}
    inicio = str(bloco.get("inicio") or "12:10")
    fim = str(bloco.get("fim") or "13:00")
    if not _parse_hm(inicio):
        inicio = "12:10"
    if not _parse_hm(fim):
        fim = "13:00"
    return {"inicio": inicio, "fim": fim}


def load_almoco_overrides() -> Dict[str, Any]:
    if not ALMOCO_PATH.exists():
        return {}
    try:
        return json.loads(ALMOCO_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_almoco_dia(day: date, inicio: str, fim: str) -> Dict[str, Any]:
    pi = _parse_hm(inicio)
    pf = _parse_hm(fim)
    if not pi or not pf:
        raise ValueError("Horário de almoço inválido (use HH:MM)")
    ini_s = _fmt_hm(*pi)
    fim_s = _fmt_hm(*pf)
    if (pi[0], pi[1]) >= (pf[0], pf[1]):
        raise ValueError("Fim do almoço deve ser maior que o início")
    data = load_almoco_overrides()
    data[day.isoformat()] = {"inicio": ini_s, "fim": fim_s}
    ALMOCO_PATH.parent.mkdir(parents=True, exist_ok=True)
    ALMOCO_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"day": day.isoformat(), "inicio": ini_s, "fim": fim_s}


def almoco_do_dia(day: date, cfg: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    base = default_almoco(cfg)
    ov = load_almoco_overrides().get(day.isoformat()) or {}
    inicio = str(ov.get("inicio") or base["inicio"])
    fim = str(ov.get("fim") or base["fim"])
    if not _parse_hm(inicio):
        inicio = base["inicio"]
    if not _parse_hm(fim):
        fim = base["fim"]
    return {"inicio": inicio, "fim": fim, "padrao": default_almoco(cfg)}


def almoco_bounds(day: date, cfg: Optional[Dict[str, Any]] = None) -> Tuple[datetime, datetime]:
    a = almoco_do_dia(day, cfg)
    hi, mi = _parse_hm(a["inicio"]) or (12, 10)
    hf, mf = _parse_hm(a["fim"]) or (13, 0)
    ini = datetime(day.year, day.month, day.day, hi, mi, 0)
    fim = datetime(day.year, day.month, day.day, hf, mf, 0)
    return ini, fim


def _overlap_seconds(a0: datetime, a1: datetime, b0: datetime, b1: datetime) -> int:
    start = max(a0, b0)
    end = min(a1, b1)
    return max(0, int((end - start).total_seconds()))


def wifi_seconds_uteis(
    wifi_intervals: List[Dict[str, Any]], day: date, cfg: Optional[Dict[str, Any]] = None
) -> Tuple[int, int, int]:
    """Retorna (wifi_bruto, almoco_sobreposto, wifi_util)."""
    lunch0, lunch1 = almoco_bounds(day, cfg)
    bruto = 0
    almoco = 0
    for w in wifi_intervals or []:
        try:
            ws = _as_naive(ds.parse_ts(w["start"]))
            we = _as_naive(ds.parse_ts(w["end"]))
        except Exception:
            continue
        if we <= ws:
            continue
        sec = int((we - ws).total_seconds())
        bruto += sec
        almoco += _overlap_seconds(ws, we, lunch0, lunch1)
    util = max(0, bruto - almoco)
    return bruto, almoco, util


def colocar_duracao_pulando_almoco(
    cursor: datetime,
    duration_sec: int,
    lunch0: datetime,
    lunch1: datetime,
    min_minutes: int = 5,
) -> Tuple[datetime, datetime]:
    """Coloca um bloco contínuo sem invadir o almoço."""
    if lunch0 <= cursor < lunch1:
        cursor = lunch1
    cursor = arredondar_hora_cinco_minutos(cursor)
    duration_sec = max(min_minutes * 60, int(duration_sec))

    # se cabe inteiro antes do almoço
    if cursor < lunch0:
        room = int((lunch0 - cursor).total_seconds())
        if room >= duration_sec:
            fim = arredondar_hora_cinco_minutos(cursor + timedelta(seconds=duration_sec))
            if fim <= cursor:
                fim = cursor + timedelta(minutes=min_minutes)
            return cursor, fim
        # não cabe: joga o bloco inteiro para depois do almoço
        cursor = arredondar_hora_cinco_minutos(lunch1)

    if lunch0 <= cursor < lunch1:
        cursor = arredondar_hora_cinco_minutos(lunch1)

    fim = arredondar_hora_cinco_minutos(cursor + timedelta(seconds=duration_sec))
    if fim <= cursor:
        fim = cursor + timedelta(minutes=min_minutes)
    return cursor, fim


def normalize_codigo(value: Any) -> Optional[str]:
    """Normaliza para CHA-XXXX (número do código, não o id interno)."""
    if value is None:
        return None
    s = str(value).strip().upper()
    if not s:
        return None
    m = re.search(r"(?:CHA[\s\-_]*)?(\d{1,6})", s)
    if not m:
        return None
    num = int(m.group(1))
    # Liber costuma padear a 4 dígitos nos códigos menores
    if num < 1000:
        return f"CHA-{num:04d}"
    return f"CHA-{num}"


def parse_codigo_from_text(text: str) -> Optional[str]:
    if not text:
        return None
    patterns = [
        r"\bCHA[\s\-_]*(\d{1,6})\b",
        r"#\s*(\d{2,6})\b",
        r"\bchamado\s*[#:\-]?\s*(?:CHA[\s\-_]*)?(\d{1,6})\b",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return normalize_codigo(m.group(1))
    return None


def round_dt(dt: datetime) -> datetime:
    return dt.replace(second=0, microsecond=0)


def arredondar_hora_cinco_minutos(dt: datetime) -> datetime:
    """Espelha GESTAO_CHA_001_playPauseHoras::arredondarHoraParaCincoMinutosMaisProximo."""
    dt = round_dt(dt)
    hora = dt.hour
    minuto = dt.minute
    minuto_arredondado = int(round(minuto / 5.0) * 5)
    if minuto_arredondado >= 60:
        minuto_arredondado = 0
        hora = (hora + 1) % 24
        if hora == 0:
            # mesmo comportamento do PHP no virada 23:xx → 00
            return dt.replace(hour=23, minute=59, second=0, microsecond=0)
    return dt.replace(hour=hora, minute=minuto_arredondado, second=0, microsecond=0)


def aplicar_regras_horas_las(
    start: datetime, end: datetime, min_minutes: int = 5
) -> Tuple[Optional[datetime], Optional[datetime], Optional[str]]:
    """
    Aplica arredondamento LAS (múltiplo de 5 min) e mínimo de duração.
    Retorna (inicio, fim, motivo_skip). Se skip, inicio/fim podem ser None.
    """
    if end <= start:
        return None, None, "hora fim deve ser maior que início"

    ini = arredondar_hora_cinco_minutos(start)
    fim = arredondar_hora_cinco_minutos(end)

    # Após arredondar, fim precisa ser estritamente maior (regra play/pause LAS)
    if fim <= ini:
        return None, None, f"mínimo {min_minutes} min após arredondar p/ 5 min (LAS)"

    minutos = int((fim - ini).total_seconds() // 60)
    if minutos < min_minutes:
        return None, None, f"mínimo {min_minutes} min (regra LAS)"

    return ini, fim, None


def draft_key(row: Dict[str, Any]) -> str:
    raw = "|".join(
        [
            str(row.get("data_trabalho") or ""),
            str(row.get("hora_inicio") or ""),
            str(row.get("hora_fim") or ""),
            str(row.get("codigo_chamado") or row.get("id_chamado") or ""),
            str(row.get("usuario_gestao_id") or ""),
        ]
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def append_sent(row: Dict[str, Any]) -> None:
    SENT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(SENT_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def overlaps(a_ini: str, a_fim: str, b_ini: str, b_fim: str) -> bool:
    return a_ini < b_fim and a_fim > b_ini


def _norm_hora(h: Any) -> str:
    h = str(h or "")
    if len(h) == 5:
        return h + ":00"
    return h[:8] if len(h) >= 8 else h


def _iter_sent_log() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not SENT_LOG.exists():
        return rows
    for line in SENT_LOG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def _las_hora_id_of(entry: Dict[str, Any]) -> Optional[int]:
    for key in ("las_hora_id", "id_hora", "insert_id"):
        if entry.get(key) is not None:
            try:
                return int(entry[key])
            except Exception:
                pass
    payload = entry.get("payload") or {}
    for key in ("las_hora_id", "id_hora"):
        if payload.get(key) is not None:
            try:
                return int(payload[key])
            except Exception:
                pass
    return None


def _purged_refs(log_rows: Optional[List[Dict[str, Any]]] = None) -> Tuple[set, set]:
    """Retorna (keys purgadas, las_hora_ids purgados)."""
    keys: set = set()
    ids: set = set()
    for row in log_rows if log_rows is not None else _iter_sent_log():
        if row.get("status") not in ("purged", "deleted", "missing_in_las"):
            continue
        if row.get("key"):
            keys.add(row["key"])
        lid = _las_hora_id_of(row)
        if lid is not None:
            ids.add(lid)
        payload = row.get("payload") or {}
        if payload:
            keys.add(draft_key(payload))
    return keys, ids


def _legacy_match_exists(conn, payload: Dict[str, Any]) -> bool:
    try:
        usuario = int(payload.get("usuario_gestao_id") or 0)
        data_trabalho = str(payload.get("data_trabalho") or "")
        hi = _norm_hora(payload.get("hora_inicio"))
        hf = _norm_hora(payload.get("hora_fim"))
    except Exception:
        return False
    if not (usuario and data_trabalho and hi and hf):
        return False
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id
              FROM las_gestao_chamado_horas
             WHERE usuario_lancamento = %s
               AND data_trabalho = %s
               AND hora_inicio = %s
               AND hora_fim = %s
             LIMIT 1
            """,
            (usuario, data_trabalho, hi, hf),
        )
        hit = cur.fetchone()
        return bool(hit)


def _ids_exist_in_las(conn, ids: List[int]) -> set:
    if not ids:
        return set()
    uniq = sorted({int(i) for i in ids})
    found: set = set()
    # chunks pequenos para IN
    with conn.cursor() as cur:
        for i in range(0, len(uniq), 100):
            chunk = uniq[i : i + 100]
            placeholders = ",".join(["%s"] * len(chunk))
            cur.execute(
                f"SELECT id FROM las_gestao_chamado_horas WHERE id IN ({placeholders})",
                chunk,
            )
            for row in cur.fetchall() or []:
                found.add(int(row["id"]))
    return found


def reconcile_sent_with_las(ap: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Fonte da verdade = LAS.
    Se um envio local (ok) não existir mais no banco (id apagado na gestão),
    marca como purged e deixa de bloquear o rascunho.
    """
    ap = ap or apontamento_cfg()
    log_rows = _iter_sent_log()
    purged_keys, purged_ids = _purged_refs(log_rows)

    candidates: List[Dict[str, Any]] = []
    for row in log_rows:
        if row.get("status") != "ok":
            continue
        payload = row.get("payload") or {}
        if not payload:
            continue
        key = row.get("key") or draft_key(payload)
        lid = _las_hora_id_of(row)
        if key in purged_keys or (lid is not None and lid in purged_ids):
            continue
        candidates.append(row)

    if not candidates:
        return {"checked": 0, "alive": 0, "purged": 0, "offline": False}

    try:
        conn = db_connect(ap)
    except Exception:
        # sem DB: mantém log local (não purgeia)
        return {"checked": len(candidates), "alive": len(candidates), "purged": 0, "offline": True}

    alive_payloads: List[Dict[str, Any]] = []
    purged_now = 0
    try:
        id_list = [i for i in (_las_hora_id_of(r) for r in candidates) if i is not None]
        existing_ids = _ids_exist_in_las(conn, id_list)

        for row in candidates:
            payload = dict(row.get("payload") or {})
            key = row.get("key") or draft_key(payload)
            lid = _las_hora_id_of(row)
            still = False
            if lid is not None:
                still = lid in existing_ids
                if still:
                    payload["las_hora_id"] = lid
            else:
                # legado sem id: confere pelo intervalo
                still = _legacy_match_exists(conn, payload)
                if still:
                    # tenta capturar o id atual para próximas reconciliações
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            SELECT id
                              FROM las_gestao_chamado_horas
                             WHERE usuario_lancamento = %s
                               AND data_trabalho = %s
                               AND hora_inicio = %s
                               AND hora_fim = %s
                             LIMIT 1
                            """,
                            (
                                int(payload.get("usuario_gestao_id") or 0),
                                str(payload.get("data_trabalho") or ""),
                                _norm_hora(payload.get("hora_inicio")),
                                _norm_hora(payload.get("hora_fim")),
                            ),
                        )
                        hit = cur.fetchone()
                        if hit:
                            payload["las_hora_id"] = int(hit["id"])
                            append_sent(
                                {
                                    "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
                                    "status": "linked",
                                    "key": key,
                                    "las_hora_id": int(hit["id"]),
                                    "payload": payload,
                                }
                            )

            if still:
                alive_payloads.append(payload)
            else:
                purged_now += 1
                append_sent(
                    {
                        "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
                        "status": "purged",
                        "key": key,
                        "las_hora_id": lid,
                        "reason": "id/intervalo não encontrado em las_gestao_chamado_horas",
                        "payload": payload,
                    }
                )
    finally:
        try:
            conn.close()
        except Exception:
            pass

    return {
        "checked": len(candidates),
        "alive": len(alive_payloads),
        "purged": purged_now,
        "offline": False,
        "payloads": alive_payloads,
    }


def read_sent_ok(ap: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Payloads ainda válidos no LAS (reconcilia e purgeia órfãos)."""
    result = reconcile_sent_with_las(ap)
    if "payloads" in result:
        return list(result.get("payloads") or [])
    # offline: fallback ao log local bruto
    rows: List[Dict[str, Any]] = []
    purged_keys, purged_ids = _purged_refs()
    for row in _iter_sent_log():
        if row.get("status") != "ok":
            continue
        payload = row.get("payload") or {}
        if not payload:
            continue
        key = row.get("key") or draft_key(payload)
        lid = _las_hora_id_of(row)
        if key in purged_keys or (lid is not None and lid in purged_ids):
            continue
        if lid is not None:
            payload = dict(payload)
            payload["las_hora_id"] = lid
        rows.append(payload)
    return rows


def read_sent_keys(ap: Optional[Dict[str, Any]] = None) -> set:
    keys = set()
    for payload in read_sent_ok(ap):
        keys.add(draft_key(payload))
    return keys


def sent_blockers_for_day(
    day: date, usuario_id: int, ap: Optional[Dict[str, Any]] = None
) -> List[Tuple[datetime, datetime]]:
    day_s = day.isoformat()
    blockers: List[Tuple[datetime, datetime]] = []
    for payload in read_sent_ok(ap):
        if str(payload.get("data_trabalho")) != day_s:
            continue
        try:
            if int(payload.get("usuario_gestao_id") or 0) != int(usuario_id):
                continue
        except Exception:
            continue
        hi = _norm_hora(payload.get("hora_inicio"))
        hf = _norm_hora(payload.get("hora_fim"))
        try:
            a0 = datetime.fromisoformat(f"{day_s}T{hi}")
            a1 = datetime.fromisoformat(f"{day_s}T{hf}")
        except Exception:
            continue
        if a1 > a0:
            blockers.append((a0, a1))
    return blockers


def db_blockers_for_day(day: date, usuario_id: int, ap: Dict[str, Any]) -> List[Tuple[datetime, datetime]]:
    blockers: List[Tuple[datetime, datetime]] = []
    try:
        conn = db_connect(ap)
    except Exception:
        return blockers
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT hora_inicio, hora_fim
                  FROM las_gestao_chamado_horas
                 WHERE usuario_lancamento = %s
                   AND data_trabalho = %s
                   AND hora_fim IS NOT NULL
                """,
                (usuario_id, day.isoformat()),
            )
            for row in cur.fetchall() or []:
                hi = _norm_hora(row.get("hora_inicio"))
                hf = _norm_hora(row.get("hora_fim"))
                try:
                    a0 = datetime.fromisoformat(f"{day.isoformat()}T{hi}")
                    a1 = datetime.fromisoformat(f"{day.isoformat()}T{hf}")
                except Exception:
                    continue
                if a1 > a0:
                    blockers.append((a0, a1))
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return blockers


def merge_blockers(blocks: List[Tuple[datetime, datetime]]) -> List[Tuple[datetime, datetime]]:
    if not blocks:
        return []
    blocks = sorted(blocks, key=lambda x: x[0])
    out = [blocks[0]]
    for a0, a1 in blocks[1:]:
        p0, p1 = out[-1]
        if a0 <= p1:
            out[-1] = (p0, max(p1, a1))
        else:
            out.append((a0, a1))
    return out


def subtract_blockers(
    start: datetime, end: datetime, blockers: List[Tuple[datetime, datetime]]
) -> List[Tuple[datetime, datetime]]:
    free = [(start, end)]
    for b0, b1 in merge_blockers(blockers):
        nxt: List[Tuple[datetime, datetime]] = []
        for f0, f1 in free:
            if b1 <= f0 or b0 >= f1:
                nxt.append((f0, f1))
                continue
            if f0 < b0:
                nxt.append((f0, b0))
            if b1 < f1:
                nxt.append((b1, f1))
        free = nxt
    return [(a, b) for a, b in free if b > a]


def intersect_blockers(
    start: datetime, end: datetime, blockers: List[Tuple[datetime, datetime]]
) -> List[Tuple[datetime, datetime]]:
    out: List[Tuple[datetime, datetime]] = []
    for b0, b1 in merge_blockers(blockers):
        a0, a1 = max(start, b0), min(end, b1)
        if a1 > a0:
            out.append((a0, a1))
    return out


def split_by_lunch(
    start: datetime, end: datetime, lunch0: datetime, lunch1: datetime
) -> List[Tuple[datetime, datetime]]:
    if end <= start:
        return []
    if end <= lunch0 or start >= lunch1:
        return [(start, end)]
    parts: List[Tuple[datetime, datetime]] = []
    if start < lunch0:
        parts.append((start, min(end, lunch0)))
    if end > lunch1:
        parts.append((max(start, lunch1), end))
    return [(a, b) for a, b in parts if b > a]


def colocar_duracao_dividindo_almoco(
    cursor: datetime,
    duration_sec: int,
    lunch0: datetime,
    lunch1: datetime,
    min_minutes: int = 5,
    hard_end: Optional[datetime] = None,
) -> List[Tuple[datetime, datetime]]:
    """Coloca duração; se atravessar o almoço, divide em dois blocos (manhã + tarde)."""
    remaining = max(min_minutes * 60, int(duration_sec))
    cursor = arredondar_hora_cinco_minutos(cursor)
    if lunch0 <= cursor < lunch1:
        cursor = arredondar_hora_cinco_minutos(lunch1)

    parts: List[Tuple[datetime, datetime]] = []

    if cursor < lunch0:
        room = int((lunch0 - cursor).total_seconds())
        take = min(remaining, room)
        take = max(0, int(round((take / 60.0) / 5.0) * 5) * 60)
        if take >= min_minutes * 60:
            fim = arredondar_hora_cinco_minutos(cursor + timedelta(seconds=take))
            if fim > lunch0:
                fim = lunch0
            if fim > cursor:
                parts.append((cursor, fim))
                remaining -= int((fim - cursor).total_seconds())
        cursor = arredondar_hora_cinco_minutos(lunch1)

    if remaining >= min_minutes * 60:
        if lunch0 <= cursor < lunch1:
            cursor = arredondar_hora_cinco_minutos(lunch1)
        fim = arredondar_hora_cinco_minutos(cursor + timedelta(seconds=remaining))
        if hard_end is not None and fim > hard_end:
            fim = hard_end
        if fim > cursor and int((fim - cursor).total_seconds()) >= min_minutes * 60:
            parts.append((cursor, fim))
        elif fim > cursor:
            # abaixo do mínimo: descarta resto
            pass

    return parts


def week_bounds(today: date) -> Tuple[date, date]:
    weekday = (today.weekday() + 1) % 7
    start = today - timedelta(days=weekday)
    end = start + timedelta(days=6)
    return start, end


def db_connect(ap: Dict[str, Any]):
    import pymysql

    db = ap.get("db") or {}
    host = db.get("host")
    user = db.get("user")
    password = db.get("password")
    database = db.get("database")
    port = int(db.get("port") or 3306)
    if not all([host, user, password, database]):
        raise RuntimeError(
            "Configure apontamento.db.password em config.json para consultar/gravar no LAS"
        )
    return pymysql.connect(
        host=host,
        user=user,
        password=password,
        database=database,
        port=port,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=10,
        read_timeout=20,
        write_timeout=20,
    )


def resolve_id_by_codigo(conn, codigo: str) -> Optional[int]:
    codigo = normalize_codigo(codigo)
    if not codigo:
        return None
    candidates = {codigo}
    m = re.search(r"(\d+)$", codigo)
    if m:
        n = int(m.group(1))
        candidates.add(f"CHA-{n}")
        candidates.add(f"CHA-{n:04d}")
    with conn.cursor() as cur:
        for cod in candidates:
            cur.execute(
                "SELECT id, codigo, LEFT(assunto, 80) AS assunto FROM las_gestao_chamado WHERE codigo = %s LIMIT 1",
                (cod,),
            )
            hit = cur.fetchone()
            if hit:
                return int(hit["id"])
    return None


def buscar_chamados(q: str, limit: int = 12) -> List[Dict[str, Any]]:
    ap = apontamento_cfg()
    q = (q or "").strip()
    if len(q) < 1:
        return []
    conn = db_connect(ap)
    try:
        codigo = normalize_codigo(q)
        with conn.cursor() as cur:
            if codigo:
                cur.execute(
                    """
                    SELECT id, codigo, LEFT(assunto, 100) AS assunto
                      FROM las_gestao_chamado
                     WHERE codigo LIKE %s
                     ORDER BY id DESC
                     LIMIT %s
                    """,
                    (f"%{codigo.replace('CHA-', '')}%", limit),
                )
            else:
                cur.execute(
                    """
                    SELECT id, codigo, LEFT(assunto, 100) AS assunto
                      FROM las_gestao_chamado
                     WHERE assunto LIKE %s OR codigo LIKE %s
                     ORDER BY id DESC
                     LIMIT %s
                    """,
                    (f"%{q}%", f"%{q}%", limit),
                )
            rows = cur.fetchall() or []
        out = []
        for r in rows:
            out.append(
                {
                    "id": int(r["id"]),
                    "codigo": r["codigo"],
                    "assunto": r.get("assunto") or "",
                    "label": f"{r['codigo']} — {r.get('assunto') or ''}",
                }
            )
        return out
    finally:
        conn.close()


def build_drafts_for_day(day: date, cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cfg = cfg or load_config()
    ap = apontamento_cfg(cfg)
    data = bd.build_data()
    day_s = day.isoformat()
    day_data = data.get("by_day", {}).get(day_s) or {"topics": [], "wifi": [], "date": day_s}

    default_codigo = normalize_codigo(
        ap.get("default_codigo_chamado") or ap.get("default_id_chamado")
    )
    usuario_id = int(ap.get("usuario_gestao_id") or 14)
    usuario_label = ap.get("usuario_label") or f"{usuario_id} - Vanderson Meska"
    min_minutes = int(ap.get("min_minutes", 5))
    mappings = ap.get("mappings") or []
    sent_keys = read_sent_keys(ap)
    lunch0, lunch1 = almoco_bounds(day, cfg)

    blockers = merge_blockers(
        sent_blockers_for_day(day, usuario_id, ap) + db_blockers_for_day(day, usuario_id, ap)
    )

    drafts: List[Dict[str, Any]] = []

    def resolve_codigo(label: str) -> Optional[str]:
        codigo = parse_codigo_from_text(label)
        if codigo is None:
            for m in mappings:
                needle = str(m.get("contains") or "").strip().lower()
                if needle and needle in label.lower():
                    codigo = normalize_codigo(m.get("codigo_chamado") or m.get("id_chamado"))
                    break
        if codigo is None and default_codigo:
            codigo = default_codigo
        return codigo

    def make_row(
        *,
        row_id: str,
        start: datetime,
        end: datetime,
        start_raw: datetime,
        end_raw: datetime,
        label: str,
        codigo: Optional[str],
        already_sent: bool,
        invalido_las: bool,
        skip_reason: Optional[str],
        manual: bool = False,
        manual_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        seconds = int((end - start).total_seconds())
        minutes = max(0, seconds // 60)
        row = {
            "id": row_id,
            "selected": False,
            "data_trabalho": day_s,
            "hora_inicio": start.strftime("%H:%M:%S"),
            "hora_fim": end.strftime("%H:%M:%S"),
            "hora_inicio_hm": start.strftime("%H:%M"),
            "hora_fim_hm": end.strftime("%H:%M"),
            "hora_inicio_raw": start_raw.strftime("%H:%M"),
            "hora_fim_raw": end_raw.strftime("%H:%M"),
            "dur": ds.fmt_dur(seconds),
            "seconds": seconds,
            "minutes": minutes,
            "assunto": label,
            "codigo_chamado": codigo,
            "usuario_gestao_id": usuario_id,
            "usuario_label": usuario_label,
            "skip_reason": skip_reason,
            "already_sent": already_sent,
            "invalido_las": invalido_las,
            "manual": bool(manual),
            "manual_id": manual_id if manual else None,
        }
        row["key"] = draft_key(row)
        if already_sent:
            row["selected"] = False
            row["skip_reason"] = skip_reason or "já apontado"
        elif invalido_las:
            row["selected"] = False
        else:
            reasons = []
            if not codigo:
                reasons.append("informe CHA-XXXX")
            if row["key"] in sent_keys:
                row["already_sent"] = True
                row["selected"] = False
                row["skip_reason"] = "já enviado ao LAS"
            else:
                row["skip_reason"] = "; ".join(reasons) if reasons else None
                row["selected"] = bool(codigo)
        return row

    for idx, topic in enumerate(day_data.get("topics") or []):
        start_raw = ds.parse_ts(topic["start"])
        end_raw = ds.parse_ts(topic["end"])
        if end_raw <= start_raw:
            end_raw = start_raw + timedelta(minutes=1)

        start_raw_n = _as_naive(start_raw)
        end_raw_n = _as_naive(end_raw)
        start, end, round_skip = aplicar_regras_horas_las(start_raw_n, end_raw_n, min_minutes)
        label = topic.get("label") or "Assunto"
        is_manual = bool(topic.get("manual"))
        row_id_base = str(topic.get("id") or f"{day_s}-{idx}")
        manual_id = row_id_base if is_manual else None
        codigo = normalize_codigo(topic.get("codigo_chamado")) if topic.get("codigo_chamado") else None
        if codigo is None:
            codigo = resolve_codigo(label)

        if start is None or end is None:
            start_show = arredondar_hora_cinco_minutos(start_raw_n)
            end_show = arredondar_hora_cinco_minutos(end_raw_n)
            if end_show <= start_show:
                end_show = start_show + timedelta(minutes=min_minutes)
            drafts.append(
                make_row(
                    row_id=row_id_base,
                    start=start_show,
                    end=end_show,
                    start_raw=start_raw_n,
                    end_raw=end_raw_n,
                    label=label,
                    codigo=None,
                    already_sent=False,
                    invalido_las=True,
                    skip_reason=round_skip,
                    manual=is_manual,
                    manual_id=manual_id,
                )
            )
            continue

        # Divide no almoço; o que já foi apontado fica fechado; o restante vira novo rascunho.
        lunch_parts = split_by_lunch(start, end, lunch0, lunch1)
        part_i = 0
        for p0, p1 in lunch_parts:
            for b0, b1 in intersect_blockers(p0, p1, blockers):
                bi, bf, bskip = aplicar_regras_horas_las(b0, b1, min_minutes)
                if bskip or bi is None or bf is None:
                    # ainda mostra o intervalo já lançado mesmo se < mínimo após round
                    bi, bf = b0, b1
                    if bf <= bi:
                        continue
                drafts.append(
                    make_row(
                        row_id=f"{row_id_base}-sent-{part_i}",
                        start=bi,
                        end=bf,
                        start_raw=start_raw_n,
                        end_raw=end_raw_n,
                        label=label,
                        codigo=codigo,
                        already_sent=True,
                        invalido_las=False,
                        skip_reason="já apontado",
                        manual=is_manual,
                        manual_id=manual_id,
                    )
                )
                part_i += 1

            for f0, f1 in subtract_blockers(p0, p1, blockers):
                fi, ff, fskip = aplicar_regras_horas_las(f0, f1, min_minutes)
                if fskip or fi is None or ff is None:
                    continue
                drafts.append(
                    make_row(
                        row_id=f"{row_id_base}-resto-{part_i}" if part_i else row_id_base,
                        start=fi,
                        end=ff,
                        start_raw=start_raw_n,
                        end_raw=end_raw_n,
                        label=label,
                        codigo=codigo,
                        already_sent=False,
                        invalido_las=False,
                        skip_reason=None,
                        manual=is_manual,
                        manual_id=manual_id,
                    )
                )
                part_i += 1

    drafts.sort(key=lambda d: (d.get("hora_inicio") or "", d.get("hora_fim") or "", d.get("id") or ""))

    return {
        "day": day_s,
        "dry_run": bool(ap.get("dry_run", True)),
        "enabled": bool(ap.get("enabled", False)),
        "min_minutes": min_minutes,
        "usuario_gestao_id": usuario_id,
        "usuario_label": usuario_label,
        "default_codigo_chamado": default_codigo,
        "almoco": almoco_do_dia(day, cfg),
        "drafts": drafts,
        "count": len(drafts),
        "selected_count": sum(1 for d in drafts if d.get("selected")),
    }



def _parse_draft_dt(day_s: str, hora: str) -> datetime:
    if len(hora) == 5:
        hora = hora + ":00"
    return datetime.fromisoformat(f"{day_s}T{hora}")


def _as_naive(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(second=0, microsecond=0)
    return dt.astimezone().replace(tzinfo=None, second=0, microsecond=0)


def _round_seconds_to_five_min(seconds: float, min_minutes: int = 5) -> int:
    mins = max(min_minutes, int(round((seconds / 60.0) / 5.0) * 5))
    return mins * 60


def colocar_duracao_evitando_bloqueios(
    cursor: datetime,
    duration_sec: int,
    lunch0: datetime,
    lunch1: datetime,
    blockers: List[Tuple[datetime, datetime]],
    min_minutes: int = 5,
    hard_end: Optional[datetime] = None,
) -> List[Tuple[datetime, datetime]]:
    """Coloca duração dividindo no almoço e pulando intervalos já apontados."""
    remaining = max(0, int(duration_sec))
    min_sec = min_minutes * 60
    parts: List[Tuple[datetime, datetime]] = []
    cursor = arredondar_hora_cinco_minutos(cursor)
    blocks = merge_blockers(blockers)

    def _skip_blocked(c: datetime) -> datetime:
        if lunch0 <= c < lunch1:
            c = arredondar_hora_cinco_minutos(lunch1)
        for b0, b1 in blocks:
            if b0 <= c < b1:
                c = arredondar_hora_cinco_minutos(b1)
        return c

    for _ in range(30):
        if remaining < min_sec:
            break
        cursor = _skip_blocked(cursor)
        if hard_end is not None and cursor >= hard_end:
            break

        # próximo obstáculo (almoço ou blocker) à frente
        limit = hard_end
        if cursor < lunch0:
            limit = lunch0 if limit is None else min(limit, lunch0)
        for b0, b1 in blocks:
            if b0 > cursor:
                limit = b0 if limit is None else min(limit, b0)

        if limit is not None and limit <= cursor:
            # empurra para depois do obstáculo colado
            if cursor < lunch1 and lunch0 <= cursor:
                cursor = arredondar_hora_cinco_minutos(lunch1)
            else:
                jumped = False
                for b0, b1 in blocks:
                    if b0 <= cursor < b1 or abs((b0 - cursor).total_seconds()) < 1:
                        cursor = arredondar_hora_cinco_minutos(b1)
                        jumped = True
                        break
                if not jumped:
                    break
            continue

        room = int((limit - cursor).total_seconds()) if limit is not None else remaining
        take = min(remaining, room)
        take = max(0, int(round((take / 60.0) / 5.0) * 5) * 60)
        if take < min_sec:
            # não cabe aqui — salta obstáculo
            if limit is None:
                break
            if limit == lunch0:
                cursor = arredondar_hora_cinco_minutos(lunch1)
            else:
                cursor = arredondar_hora_cinco_minutos(limit)
                for b0, b1 in blocks:
                    if b0 == limit:
                        cursor = arredondar_hora_cinco_minutos(b1)
                        break
            continue

        fim = arredondar_hora_cinco_minutos(cursor + timedelta(seconds=take))
        if limit is not None and fim > limit:
            fim = limit
        if hard_end is not None and fim > hard_end:
            fim = hard_end
        if fim <= cursor or int((fim - cursor).total_seconds()) < min_sec:
            break

        # segurança: não invadir blockers/almoço
        free = subtract_blockers(cursor, fim, blocks + [(lunch0, lunch1)])
        if not free:
            cursor = fim
            continue
        a0, a1 = free[0]
        ini3, fim3, skip = aplicar_regras_horas_las(a0, a1, min_minutes)
        if skip or ini3 is None or fim3 is None:
            cursor = a1
            continue
        parts.append((ini3, fim3))
        remaining -= int((fim3 - ini3).total_seconds())
        cursor = fim3

    return parts


def distribuir_tempo_wifi(day: date, cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Distribui o tempo de Wi‑Fi sem assunto de forma proporcional entre os assuntos.
    Só altera rascunhos editáveis (não enviados / não inválidos). Não grava no LAS.
    Se um assunto atravessar o almoço, é dividido em dois apontamentos.
    """
    cfg = cfg or load_config()
    ap = apontamento_cfg(cfg)
    min_minutes = int(ap.get("min_minutes", 5))
    usuario_id = int(ap.get("usuario_gestao_id") or 14)
    payload = build_drafts_for_day(day, cfg)
    day_s = payload["day"]

    data = bd.build_data()
    day_data = data.get("by_day", {}).get(day_s) or {}
    wifi_intervals = day_data.get("wifi") or []
    wifi_bruto, almoco_sec, wifi_sec = wifi_seconds_uteis(wifi_intervals, day, cfg)
    lunch0, lunch1 = almoco_bounds(day, cfg)
    almoco_info = almoco_do_dia(day, cfg)
    blockers = merge_blockers(
        sent_blockers_for_day(day, usuario_id, ap) + db_blockers_for_day(day, usuario_id, ap)
    )

    drafts = payload.get("drafts") or []
    cobertos = [d for d in drafts if not d.get("invalido_las")]
    editaveis = [d for d in drafts if (not d.get("invalido_las") and not d.get("already_sent"))]
    locked = [d for d in drafts if d.get("already_sent") or d.get("invalido_las")]

    assuntos_sec = int(sum(int(d.get("seconds") or 0) for d in cobertos))
    gap = max(0, wifi_sec - assuntos_sec)

    if wifi_sec <= 0:
        payload["distribuicao"] = {
            "ok": False,
            "message": "Sem tempo útil de Wi‑Fi no dia (após descontar almoço)",
            "wifi_total": ds.fmt_dur(wifi_bruto),
            "wifi_util": ds.fmt_dur(0),
            "almoco": ds.fmt_dur(almoco_sec),
            "assuntos_total": ds.fmt_dur(assuntos_sec),
            "ocioso": ds.fmt_dur(0),
        }
        return payload

    if not editaveis:
        payload["distribuicao"] = {
            "ok": False,
            "message": "Nenhum assunto editável para receber a distribuição",
            "wifi_total": ds.fmt_dur(wifi_bruto),
            "wifi_util": ds.fmt_dur(wifi_sec),
            "almoco": ds.fmt_dur(almoco_sec),
            "assuntos_total": ds.fmt_dur(assuntos_sec),
            "ocioso": ds.fmt_dur(gap),
        }
        return payload

    if gap <= 0:
        payload["distribuicao"] = {
            "ok": False,
            "message": "Não há tempo ocioso: assuntos já cobrem o Wi‑Fi útil (sem almoço)",
            "wifi_total": ds.fmt_dur(wifi_bruto),
            "wifi_util": ds.fmt_dur(wifi_sec),
            "almoco": ds.fmt_dur(almoco_sec),
            "assuntos_total": ds.fmt_dur(assuntos_sec),
            "ocioso": ds.fmt_dur(0),
        }
        return payload

    # Agrupa editáveis pelo assunto original (mesmo tópico pode já estar partido pelo almoço)
    grupos: Dict[str, Dict[str, Any]] = {}
    ordem_grupos: List[str] = []
    for d in sorted(editaveis, key=lambda x: x.get("hora_inicio") or ""):
        gkey = str(d.get("assunto") or d.get("id"))
        if gkey not in grupos:
            grupos[gkey] = {
                "seconds": 0,
                "template": d,
                "hora_inicio": d.get("hora_inicio"),
            }
            ordem_grupos.append(gkey)
        grupos[gkey]["seconds"] += max(1, int(d.get("seconds") or 0))

    base_total = sum(max(1, int(grupos[k]["seconds"])) for k in ordem_grupos)
    alvos: List[int] = []
    usado = 0
    for i, gkey in enumerate(ordem_grupos):
        base = max(1, int(grupos[gkey]["seconds"]))
        if i < len(ordem_grupos) - 1:
            extra = gap * (base / base_total)
            alvo = _round_seconds_to_five_min(base + extra, min_minutes)
            alvos.append(alvo)
            usado += alvo
        else:
            edit_base = sum(max(1, int(grupos[k]["seconds"])) for k in ordem_grupos)
            desejado = _round_seconds_to_five_min(edit_base + gap, min_minutes)
            resto = max(min_minutes * 60, desejado - usado)
            resto = _round_seconds_to_five_min(resto, min_minutes)
            alvos.append(resto)

    if wifi_intervals:
        cursor = arredondar_hora_cinco_minutos(_as_naive(ds.parse_ts(wifi_intervals[0]["start"])))
        wifi_end = arredondar_hora_cinco_minutos(_as_naive(ds.parse_ts(wifi_intervals[-1]["end"])))
        janela = wifi_sec
        soma_alvos = sum(alvos)
        if janela > 0 and soma_alvos > janela:
            escala = janela / soma_alvos
            alvos = [_round_seconds_to_five_min(a * escala, min_minutes) for a in alvos]
    else:
        cursor = arredondar_hora_cinco_minutos(
            _parse_draft_dt(day_s, grupos[ordem_grupos[0]]["hora_inicio"])
        )
        wifi_end = None

    # pula início se já estiver em intervalo apontado
    for b0, b1 in merge_blockers(blockers):
        if b0 <= cursor < b1:
            cursor = arredondar_hora_cinco_minutos(b1)

    expanded: List[Dict[str, Any]] = []
    for gkey, alvo_sec in zip(ordem_grupos, alvos):
        template = grupos[gkey]["template"]
        segs = colocar_duracao_evitando_bloqueios(
            cursor,
            alvo_sec,
            lunch0,
            lunch1,
            blockers,
            min_minutes,
            hard_end=wifi_end,
        )
        last_end = cursor
        for si, (ini3, fim3) in enumerate(segs):
            seconds = int((fim3 - ini3).total_seconds())
            row = dict(template)
            row["id"] = f"{template.get('id')}-dist-{si}"
            row["hora_inicio"] = ini3.strftime("%H:%M:%S")
            row["hora_fim"] = fim3.strftime("%H:%M:%S")
            row["hora_inicio_hm"] = ini3.strftime("%H:%M")
            row["hora_fim_hm"] = fim3.strftime("%H:%M")
            row["seconds"] = seconds
            row["minutes"] = max(1, seconds // 60)
            row["dur"] = ds.fmt_dur(seconds)
            row["distribuido"] = True
            row["already_sent"] = False
            row["invalido_las"] = False
            row["key"] = draft_key(row)
            if row.get("codigo_chamado"):
                row["selected"] = True
                row["skip_reason"] = None
            expanded.append(row)
            last_end = fim3
        cursor = last_end
        for b0, b1 in merge_blockers(blockers):
            if b0 <= cursor < b1:
                cursor = arredondar_hora_cinco_minutos(b1)

    merged = locked + expanded
    merged.sort(key=lambda d: (d.get("hora_inicio") or "", d.get("hora_fim") or "", d.get("id") or ""))
    payload["drafts"] = merged
    payload["selected_count"] = sum(1 for d in merged if d.get("selected"))
    payload["count"] = len(merged)
    payload["almoco"] = almoco_info
    novo_assuntos = int(sum(int(d.get("seconds") or 0) for d in merged if not d.get("invalido_las")))
    payload["distribuicao"] = {
        "ok": True,
        "message": (
            f"Distribuídos {ds.fmt_dur(gap)} ociosos "
            f"(Wi‑Fi {ds.fmt_dur(wifi_bruto)} − almoço {almoco_info['inicio']}–{almoco_info['fim']}) "
            f"em {len(ordem_grupos)} assunto(s) → {len(expanded)} bloco(s) "
            f"({ds.fmt_dur(assuntos_sec)} → {ds.fmt_dur(novo_assuntos)})"
        ),
        "wifi_total": ds.fmt_dur(wifi_bruto),
        "wifi_util": ds.fmt_dur(wifi_sec),
        "almoco": f"{almoco_info['inicio']}–{almoco_info['fim']}",
        "assuntos_antes": ds.fmt_dur(assuntos_sec),
        "assuntos_depois": ds.fmt_dur(novo_assuntos),
        "ocioso": ds.fmt_dur(gap),
    }
    return payload



def validate_rows(
    rows: List[Dict[str, Any]], ap: Dict[str, Any], now: Optional[datetime] = None
) -> Tuple[List[str], List[Dict[str, Any]]]:
    errors: List[str] = []
    now = now or datetime.now().astimezone()
    today = now.date()
    allow_other_weeks = bool(ap.get("permitir_outras_semanas", False))
    week_start, week_end = week_bounds(today)
    local_now = datetime.now()
    usuario_default = int(ap.get("usuario_gestao_id") or 14)

    cleaned: List[Dict[str, Any]] = []
    for i, row in enumerate(rows):
        prefix = f"Linha {i + 1}"
        codigo = normalize_codigo(row.get("codigo_chamado") or row.get("id_chamado"))
        try:
            usuario_id = int(row.get("usuario_gestao_id") or usuario_default)
        except Exception:
            errors.append(f"{prefix}: usuario_gestao_id inválido")
            continue

        if not codigo:
            errors.append(f"{prefix}: informe o chamado no formato CHA-XXXX")
            continue

        data_trabalho = str(row.get("data_trabalho") or "")
        hora_inicio = str(row.get("hora_inicio") or "")
        hora_fim = str(row.get("hora_fim") or "")
        if len(hora_inicio) == 5:
            hora_inicio += ":00"
        if len(hora_fim) == 5:
            hora_fim += ":00"

        if not data_trabalho or not hora_inicio or not hora_fim:
            errors.append(f"{prefix}: campos obrigatórios não preenchidos")
            continue

        try:
            day = date.fromisoformat(data_trabalho)
            dt_ini_raw = datetime.fromisoformat(f"{data_trabalho}T{hora_inicio}")
            dt_fim_raw = datetime.fromisoformat(f"{data_trabalho}T{hora_fim}")
        except Exception:
            errors.append(f"{prefix}: data/hora inválida")
            continue

        min_minutes = int(ap.get("min_minutes", 5))
        dt_ini, dt_fim, round_skip = aplicar_regras_horas_las(dt_ini_raw, dt_fim_raw, min_minutes)
        if round_skip or dt_ini is None or dt_fim is None:
            errors.append(f"{prefix}: {round_skip or 'horário inválido após arredondamento LAS (5 min)'}")
            continue

        hora_inicio = dt_ini.strftime("%H:%M:%S")
        hora_fim = dt_fim.strftime("%H:%M:%S")

        lunch0, lunch1 = almoco_bounds(day)
        if _overlap_seconds(dt_ini, dt_fim, lunch0, lunch1) > 0:
            errors.append(
                f"{prefix}: horário invade/atravessa o almoço "
                f"({lunch0.strftime('%H:%M')}–{lunch1.strftime('%H:%M')}) — divida em dois"
            )
            continue

        if day > today:
            errors.append(f"{prefix}: não é possível lançar data futura")
            continue
        if day == today and dt_fim > local_now + timedelta(minutes=15):
            errors.append(f"{prefix}: hora fim não pode ser > 15min à frente")
            continue
        if not allow_other_weeks and (day < week_start or day > week_end):
            errors.append(
                f"{prefix}: só semana atual ({week_start.isoformat()} a {week_end.isoformat()})"
            )
            continue

        cleaned.append(
            {
                "data_trabalho": data_trabalho,
                "hora_inicio": hora_inicio,
                "hora_fim": hora_fim,
                "codigo_chamado": codigo,
                "usuario_gestao_id": usuario_id,
                "assunto": row.get("assunto") or "",
            }
        )

    for i, a in enumerate(cleaned):
        for j, b in enumerate(cleaned):
            if j <= i:
                continue
            if a["usuario_gestao_id"] != b["usuario_gestao_id"]:
                continue
            if a["data_trabalho"] != b["data_trabalho"]:
                continue
            if overlaps(a["hora_inicio"], a["hora_fim"], b["hora_inicio"], b["hora_fim"]):
                errors.append(
                    f"Linhas {i + 1} e {j + 1}: horários se sobrepõem "
                    f"({a['hora_inicio'][:5]}–{a['hora_fim'][:5]} x {b['hora_inicio'][:5]}–{b['hora_fim'][:5]})"
                )

    return errors, cleaned


def resolve_rows_ids(conn, rows: List[Dict[str, Any]]) -> Tuple[List[str], List[Dict[str, Any]]]:
    errors: List[str] = []
    out: List[Dict[str, Any]] = []
    for i, row in enumerate(rows):
        codigo = row["codigo_chamado"]
        id_chamado = resolve_id_by_codigo(conn, codigo)
        if not id_chamado:
            errors.append(f"Linha {i + 1}: {codigo} não encontrado no LAS")
            continue
        item = dict(row)
        item["id_chamado"] = id_chamado
        out.append(item)
    return errors, out


def check_db_conflicts(conn, rows: List[Dict[str, Any]]) -> List[str]:
    errors: List[str] = []
    with conn.cursor() as cur:
        for i, row in enumerate(rows):
            cur.execute(
                """
                SELECT id, hora_inicio, hora_fim
                  FROM las_gestao_chamado_horas
                 WHERE usuario_lancamento = %s
                   AND data_trabalho = %s
                   AND hora_inicio < %s
                   AND hora_fim > %s
                """,
                (
                    row["usuario_gestao_id"],
                    row["data_trabalho"],
                    row["hora_fim"],
                    row["hora_inicio"],
                ),
            )
            hit = cur.fetchone()
            if hit:
                hi = str(hit["hora_inicio"])[:5]
                hf = str(hit["hora_fim"])[:5]
                errors.append(
                    f"Linha {i + 1}: já existe lançamento sobreposto no LAS ({hi}–{hf})"
                )
    return errors


def insert_rows(conn, rows: List[Dict[str, Any]]) -> int:
    saved = 0
    with conn.cursor() as cur:
        for row in rows:
            cur.execute(
                """
                INSERT INTO las_gestao_chamado_horas
                    (id_chamado, data_trabalho, hora_inicio, hora_fim, usuario_lancamento, data_lancamento)
                VALUES (%s, %s, %s, %s, %s, NOW())
                """,
                (
                    row["id_chamado"],
                    row["data_trabalho"],
                    row["hora_inicio"],
                    row["hora_fim"],
                    row["usuario_gestao_id"],
                ),
            )
            las_id = int(cur.lastrowid)
            row["las_hora_id"] = las_id
            saved += 1
    conn.commit()
    return saved


def confirmar(rows: List[Dict[str, Any]], force_dry_run: Optional[bool] = None) -> Dict[str, Any]:
    cfg = load_config()
    ap = apontamento_cfg(cfg)
    if not ap.get("enabled", False):
        return {
            "ok": False,
            "dry_run": True,
            "message": "Apontamento desabilitado. Em config.json: apontamento.enabled = true",
            "errors": [],
            "salvos": 0,
        }

    # força usuário fixo
    for row in rows:
        row["usuario_gestao_id"] = int(ap.get("usuario_gestao_id") or 14)
        row["codigo_chamado"] = normalize_codigo(row.get("codigo_chamado") or row.get("id_chamado"))

    errors, cleaned = validate_rows(rows, ap)
    if errors:
        return {"ok": False, "dry_run": True, "message": "Validação falhou", "errors": errors, "salvos": 0}
    if not cleaned:
        return {"ok": False, "dry_run": True, "message": "Nenhuma linha para enviar", "errors": [], "salvos": 0}

    sent_keys = read_sent_keys(ap)
    for i, row in enumerate(cleaned):
        key = draft_key(row)
        if key in sent_keys:
            errors.append(f"Linha {i + 1}: este intervalo já foi apontado (não reenviar)")
            continue
        day = date.fromisoformat(row["data_trabalho"])
        blockers = merge_blockers(
            sent_blockers_for_day(day, int(row["usuario_gestao_id"]), ap)
        )
        a0 = datetime.fromisoformat(f'{row["data_trabalho"]}T{_norm_hora(row["hora_inicio"])}')
        a1 = datetime.fromisoformat(f'{row["data_trabalho"]}T{_norm_hora(row["hora_fim"])}')
        if intersect_blockers(a0, a1, blockers):
            errors.append(
                f"Linha {i + 1}: sobrepõe apontamento já enviado "
                f"({row['hora_inicio'][:5]}–{row['hora_fim'][:5]})"
            )
    if errors:
        return {
            "ok": False,
            "dry_run": True,
            "message": "Já apontado / sobreposição com envio anterior",
            "errors": errors,
            "salvos": 0,
        }

    dry_run = bool(ap.get("dry_run", True)) if force_dry_run is None else bool(force_dry_run)

    if dry_run:
        for row in cleaned:
            append_sent(
                {
                    "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
                    "status": "dry_run",
                    "key": draft_key(row),
                    "payload": row,
                }
            )
        return {
            "ok": True,
            "dry_run": True,
            "message": f"DRY-RUN: {len(cleaned)} lançamento(s) válidos — nada gravado no LAS",
            "errors": [],
            "salvos": 0,
            "preview": cleaned,
        }

    try:
        conn = db_connect(ap)
    except Exception as exc:
        return {"ok": False, "dry_run": False, "message": str(exc), "errors": [str(exc)], "salvos": 0}

    try:
        resolve_errors, resolved = resolve_rows_ids(conn, cleaned)
        if resolve_errors:
            return {
                "ok": False,
                "dry_run": False,
                "message": "Chamado(s) não encontrados",
                "errors": resolve_errors,
                "salvos": 0,
            }
        db_errors = check_db_conflicts(conn, resolved)
        if db_errors:
            return {
                "ok": False,
                "dry_run": False,
                "message": "Conflito com horas já lançadas no LAS",
                "errors": db_errors,
                "salvos": 0,
            }
        saved = insert_rows(conn, resolved)
        for row in resolved:
            append_sent(
                {
                    "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
                    "status": "ok",
                    "key": draft_key(row),
                    "las_hora_id": row.get("las_hora_id"),
                    "payload": row,
                }
            )
        return {
            "ok": True,
            "dry_run": False,
            "message": f"{saved} lançamento(s) gravado(s) em las_gestao_chamado_horas",
            "errors": [],
            "salvos": saved,
            "preview": resolved,
        }
    finally:
        try:
            conn.close()
        except Exception:
            pass
