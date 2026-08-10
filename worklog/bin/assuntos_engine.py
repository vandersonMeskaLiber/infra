#!/usr/bin/env python3
"""
Assuntos sticky locais (só nesta máquina).

Regra: só por assunto/tema — sem corte por tempo (45 min etc.).
- prompt casa com tema X → continua/atualiza o assunto X
- mesma conversa/aba de um assunto → continua nele
- tema diferente → outro assunto
- título estável por tema (não copia o prompt)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
WORKLOG_DIR = SCRIPT_DIR.parent
STATE_PATH = WORKLOG_DIR / "logs" / "state" / "assuntos.json"

_WORD_RE = re.compile(r"[a-zà-ü0-9]{3,}", re.IGNORECASE)
_CHA_RE = re.compile(r"\bCHA[\s\-_]*(\d{1,6})\b", re.IGNORECASE)

_STOP = {
    "que", "com", "para", "pra", "por", "uma", "uns", "umas", "dos", "das", "nos", "nas",
    "como", "quando", "onde", "qual", "quais", "isso", "esse", "essa", "este", "esta",
    "aqui", "ali", "também", "tambem", "muito", "mais", "menos", "ainda", "depois",
    "antes", "sobre", "entre", "sem", "ser", "ter", "fazer", "esta", "está", "estou",
    "voce", "você", "pode", "quero", "vamos", "hoje", "agora", "nao", "não", "sim",
    "ok", "correto", "certo", "tem", "foi", "era", "são", "sao", "ele", "ela", "eles",
    "the", "and", "for", "with", "from", "this", "that", "have", "plan", "itself",
    "do", "not", "edit", "file", "attached", "reference", "implement", "specified",
}

THEMES: List[Dict[str, Any]] = [
    {
        "id": "worklog_apontamento",
        "title": "gerar monitoramento de trabalho e apontamento de horas",
        "keywords": {
            "worklog",
            "apontamento",
            "apontamentos",
            "apontar",
            "wifi",
            "assunto",
            "assuntos",
            "almoco",
            "almoço",
            "dashboard",
            "presenca",
            "presença",
            "cursor",
            "horas",
            "chamado",
            "chamados",
            "monitoramento",
            "distribuir",
            "distribuicao",
            "distribuição",
            "overlap",
            "sobrepostas",
            "sobreposto",
            "infra",
            "chegada",
            "saida",
            "saída",
            "rascunho",
            "confirmar",
            "launchd",
            "painel",
            "gravando",
            "usabilidade",
        },
        "strong": {
            "worklog",
            "apontamento",
            "apontamentos",
            "assunto",
            "assuntos",
            "wifi",
            "monitoramento",
        },
        "path_hints": ("/worklog", "/.worklog", "/infra/worklog"),
    },
    {
        "id": "ia_rotina_operacional",
        "title": "estudo IA na rotina operacional do encarregado",
        "keywords": {
            "ia",
            "inteligência",
            "inteligencia",
            "encarregado",
            "rotina",
            "operacional",
            "erp",
            "erps",
            "chão",
            "chao",
            "fábrica",
            "fabrica",
            "fila",
            "sla",
            "ack",
            "oee",
            "kanban",
            "parada",
            "paradas",
            "direcionando",
            "controlando",
            "efetuando",
            "escalonamento",
            "insight",
        },
        "strong": {
            "encarregado",
            "operacional",
            "erp",
            "erps",
            "ia",
            "kanban",
            "oee",
        },
        "path_hints": (),
    },
]


@dataclass
class Subject:
    id: str
    title: str
    start: str
    end: str
    theme_id: Optional[str] = None
    keywords: List[str] = field(default_factory=list)
    conversation_ids: List[str] = field(default_factory=list)
    prompt_count: int = 0
    chas: List[str] = field(default_factory=list)

    def start_dt(self) -> datetime:
        return datetime.fromisoformat(self.start)

    def end_dt(self) -> datetime:
        return datetime.fromisoformat(self.end)


def _now() -> datetime:
    return datetime.now().astimezone()


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def tokens(text: str) -> Set[str]:
    words = {w.lower() for w in _WORD_RE.findall(text or "")}
    if re.search(r"(?i)(?<![a-zà-ü])ia(?![a-zà-ü])", text or ""):
        words.add("ia")
    return {w for w in words if w not in _STOP and not w.isdigit()}


def extract_chas(text: str) -> List[str]:
    out: List[str] = []
    seen = set()
    for m in _CHA_RE.finditer(text or ""):
        n = int(m.group(1))
        cod = f"CHA-{n:04d}" if n < 1000 else f"CHA-{n}"
        if cod not in seen:
            seen.add(cod)
            out.append(cod)
    return out


def theme_by_id(theme_id: Optional[str]) -> Optional[Dict[str, Any]]:
    if not theme_id:
        return None
    for t in THEMES:
        if t["id"] == theme_id:
            return t
    return None


def match_theme(prompt: str, workspace: str = "") -> Optional[Dict[str, Any]]:
    toks = tokens(prompt)
    ws = (workspace or "").lower()
    best = None
    best_score = 0
    for theme in THEMES:
        keys = set(theme["keywords"])
        strong = set(theme.get("strong") or [])
        score = len(toks & keys)
        score += 2 * len(toks & strong)
        for hint in theme.get("path_hints") or []:
            if hint.lower() in ws:
                score += 4
        if score > best_score:
            best_score = score
            best = theme
    if not best:
        return None
    # exige sinal forte o bastante (evita "tempo real" cair em IA)
    strong_hit = bool(toks & set(best.get("strong") or []))
    if best_score >= 4 or (best_score >= 3 and strong_hit) or (best_score >= 2 and strong_hit and len(toks & set(best["keywords"])) >= 2):
        return best
    return None


def compose_title(prompt: str, theme: Optional[Dict[str, Any]], previous: Optional[str] = None) -> str:
    if theme:
        return str(theme["title"])
    if previous and previous not in {"Assunto", "Assunto sem título", "trabalho em andamento"}:
        return previous
    toks = list(tokens(prompt))
    verbs = {"gerar", "montar", "criar", "ajustar", "melhorar", "implementar", "configurar", "validar", "estudar"}
    verb = next((t for t in toks if t in verbs), None)
    nouns = [t for t in toks if t not in verbs][:3]
    parts = ([verb] if verb else []) + nouns
    title = " ".join(parts).strip()
    return (title[:72] if len(title) >= 8 else (previous or "trabalho em andamento"))


def update_title(current: Subject, prompt: str, theme: Optional[Dict[str, Any]]) -> str:
    if theme:
        return str(theme["title"])
    if current.theme_id:
        t = theme_by_id(current.theme_id)
        if t:
            return str(t["title"])
    if current.title and len(tokens(current.title)) >= 3:
        return current.title
    return compose_title(prompt, theme, current.title)


def load_state() -> Dict[str, Any]:
    if not STATE_PATH.exists():
        return {"days": {}, "cid_theme": {}}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"days": {}, "cid_theme": {}}
        data.setdefault("days", {})
        data.setdefault("cid_theme", {})
        return data
    except Exception:
        return {"days": {}, "cid_theme": {}}


def save_state(data: Dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _subject_from_dict(row: Dict[str, Any]) -> Subject:
    return Subject(
        id=str(row.get("id") or ""),
        title=str(row.get("title") or "Assunto"),
        start=str(row.get("start") or _iso(_now())),
        end=str(row.get("end") or _iso(_now())),
        theme_id=row.get("theme_id"),
        keywords=list(row.get("keywords") or []),
        conversation_ids=list(row.get("conversation_ids") or []),
        prompt_count=int(row.get("prompt_count") or 0),
        chas=list(row.get("chas") or []),
    )


def subjects_for_day(day: date) -> List[Subject]:
    data = load_state()
    rows = (data.get("days") or {}).get(day.isoformat()) or []
    return [_subject_from_dict(r) for r in rows if isinstance(r, dict)]


def save_subjects_for_day(day: date, subjects: Sequence[Subject]) -> None:
    data = load_state()
    data.setdefault("days", {})
    data["days"][day.isoformat()] = [asdict(s) for s in subjects]
    save_state(data)


def _new_subject(
    ts: datetime,
    prompt: str,
    conversation_id: Optional[str],
    workspace: str,
    theme: Optional[Dict[str, Any]] = None,
) -> Subject:
    theme = theme or match_theme(prompt, workspace)
    title = compose_title(prompt, theme)
    kws = tokens(prompt)
    if theme:
        kws |= set(list(theme["keywords"])[:10])
    return Subject(
        id=f"{ts.strftime('%H%M%S')}-{abs(hash((title, conversation_id))) % 10000:04d}",
        title=title,
        start=_iso(ts),
        end=_iso(ts),
        theme_id=theme["id"] if theme else None,
        keywords=sorted(kws)[:40],
        conversation_ids=[conversation_id] if conversation_id else [],
        prompt_count=1 if prompt else 0,
        chas=extract_chas(prompt),
    )


def _resolve_theme(
    prompt: str,
    workspace: str,
    conversation_id: Optional[str],
    cid_theme: Dict[str, str],
) -> Optional[Dict[str, Any]]:
    theme = match_theme(prompt, workspace)
    if theme:
        if conversation_id:
            cid_theme[conversation_id] = theme["id"]
        return theme
    if conversation_id and conversation_id in cid_theme:
        return theme_by_id(cid_theme[conversation_id])
    return None


def _find_subject(
    subjects: List[Subject],
    *,
    theme: Optional[Dict[str, Any]],
    conversation_id: Optional[str],
) -> Optional[Subject]:
    if theme:
        for s in subjects:
            if s.theme_id == theme["id"]:
                return s
    if conversation_id:
        for s in subjects:
            if conversation_id in s.conversation_ids:
                return s
    return None


def apply_event(
    *,
    ts: Optional[datetime] = None,
    prompt: Optional[str],
    conversation_id: Optional[str],
    workspace: str = "",
    event: str = "beforeSubmitPrompt",
    gap_minutes: int = 0,
) -> Optional[Subject]:
    """Atualiza estado local no hook. Sem regra de tempo."""
    ts = ts or _now()
    day = ts.date()
    data = load_state()
    cid_theme: Dict[str, str] = dict(data.get("cid_theme") or {})
    subjects = subjects_for_day(day)
    event_l = (event or "").lower()

    if event_l in {"stop", "sessionend"} and not prompt:
        target = None
        if conversation_id:
            target = _find_subject(subjects, theme=None, conversation_id=conversation_id)
        if target is None and subjects:
            target = subjects[-1]
        if target is not None and ts >= target.start_dt():
            target.end = _iso(max(ts, target.end_dt()))
            # rewrite list
            subjects = [target if s.id == target.id else s for s in subjects]
            save_subjects_for_day(day, subjects)
            data = load_state()
            data["cid_theme"] = cid_theme
            save_state(data)
            return target
        return None

    if not prompt:
        return subjects[-1] if subjects else None

    theme = _resolve_theme(prompt, workspace, conversation_id, cid_theme)
    target = _find_subject(subjects, theme=theme, conversation_id=conversation_id)

    if target is None and not subjects:
        sub = _new_subject(ts, prompt, conversation_id, workspace, theme)
        save_subjects_for_day(day, [sub])
        data = load_state()
        data["cid_theme"] = cid_theme
        save_state(data)
        return sub

    if target is None:
        # assunto novo
        if subjects:
            cur = subjects[-1]
            if ts >= cur.start_dt():
                cur.end = _iso(ts)
                subjects[-1] = cur
        sub = _new_subject(ts, prompt, conversation_id, workspace, theme)
        subjects.append(sub)
        save_subjects_for_day(day, subjects)
        data = load_state()
        data["cid_theme"] = cid_theme
        save_state(data)
        return sub

    # continua o mesmo assunto (por tema ou conversa)
    if subjects and subjects[-1].id != target.id:
        # troca de aba/assunto: fecha o anterior neste instante
        prev = subjects[-1]
        if ts >= prev.start_dt():
            prev.end = _iso(ts)
        subjects = [prev if s.id == prev.id else s for s in subjects]

    target.end = _iso(max(ts, target.end_dt()))
    target.prompt_count += 1
    target.keywords = sorted(set(target.keywords) | tokens(prompt))[:50]
    if conversation_id and conversation_id not in target.conversation_ids:
        target.conversation_ids.append(conversation_id)
    for c in extract_chas(prompt):
        if c not in target.chas:
            target.chas.append(c)
    if theme and not target.theme_id:
        target.theme_id = theme["id"]
    target.title = update_title(target, prompt, theme or theme_by_id(target.theme_id))

    out: List[Subject] = []
    replaced = False
    for s in subjects:
        if s.id == target.id:
            out.append(target)
            replaced = True
        else:
            out.append(s)
    if not replaced:
        out.append(target)
    # assunto ativo vai para o fim
    out = [s for s in out if s.id != target.id] + [target]
    save_subjects_for_day(day, out)
    data = load_state()
    data["cid_theme"] = cid_theme
    save_state(data)
    return target


def rebuild_day_from_prompts(
    rows: Sequence[Dict[str, Any]],
    day: date,
    *,
    gap_minutes: int = 0,
    fallback_end: Optional[datetime] = None,
) -> List[Subject]:
    """
    Reconstrói assuntos do dia:
    - só por tema/conversa (sem regra de 45 min)
    - cada assunto tem janela própria (1º prompt → último stop/prompt daquela conversa/tema)
    - abas simultâneas NÃO se roubam o relógio
    - no final empacota 1 linha por tema sem overlap (para apontamento LAS)
    """
    del gap_minutes  # mantido na assinatura; regra de gap removida
    fallback_end = fallback_end or _now()
    events: List[Tuple[datetime, str, Optional[str], str, str]] = []
    for row in rows:
        try:
            ts = datetime.fromisoformat(str(row.get("ts")))
            if ts.tzinfo is None:
                ts = ts.astimezone()
        except Exception:
            continue
        if ts.date() != day:
            continue
        prompt = row.get("prompt")
        event = str(row.get("event") or "")
        cid = str(row.get("conversation_id")) if row.get("conversation_id") else None
        ws = str(row.get("workspace") or "")
        if prompt:
            events.append((ts, str(prompt), cid, ws, "prompt"))
        elif event.lower() in {"stop", "sessionend", "sessionstart"}:
            events.append((ts, "", cid, ws, event.lower()))

    events.sort(key=lambda x: x[0])
    cid_theme: Dict[str, str] = {}
    order: List[str] = []
    buckets: Dict[str, Dict[str, Any]] = {}

    def ensure_bucket(key: str, prompt: str, cid: Optional[str], theme: Optional[Dict[str, Any]]) -> None:
        if key in buckets:
            return
        order.append(key)
        buckets[key] = {
            "title": (str(theme["title"]) if theme else compose_title(prompt, None)),
            "theme_id": theme["id"] if theme else None,
            "keywords": set(tokens(prompt)) if prompt else set(),
            "conversation_ids": set([cid] if cid else []),
            "prompt_count": 0,
            "chas": set(extract_chas(prompt)) if prompt else set(),
            "first": None,
            "last": None,
        }

    def touch(key: str, ts: datetime) -> None:
        b = buckets[key]
        if b["first"] is None or ts < b["first"]:
            b["first"] = ts
        if b["last"] is None or ts > b["last"]:
            b["last"] = ts

    def absorb_cid_into_theme(cid: str, theme_key: str) -> None:
        old_key = f"cid:{cid}"
        if old_key not in buckets or old_key == theme_key:
            return
        old = buckets.pop(old_key)
        b = buckets[theme_key]
        b["prompt_count"] += int(old.get("prompt_count") or 0)
        b["keywords"] |= set(old.get("keywords") or [])
        b["conversation_ids"] |= set(old.get("conversation_ids") or [])
        b["chas"] |= set(old.get("chas") or [])
        if old.get("first") is not None:
            touch(theme_key, old["first"])
        if old.get("last") is not None:
            touch(theme_key, old["last"])
        if old_key in order:
            order[:] = [k for k in order if k != old_key]

    for ts, prompt, cid, ws, kind in events:
        if kind == "prompt":
            theme = _resolve_theme(prompt, ws, cid, cid_theme)
            if theme:
                key = f"theme:{theme['id']}"
            elif cid and cid in cid_theme:
                key = f"theme:{cid_theme[cid]}"
                theme = theme_by_id(cid_theme[cid])
            elif cid:
                key = f"cid:{cid}"
                theme = None
            else:
                key = f"anon:{ts.isoformat()}"
                theme = None

            ensure_bucket(key, prompt, cid, theme)
            if theme and cid:
                absorb_cid_into_theme(cid, key)

            b = buckets[key]
            b["prompt_count"] += 1
            b["keywords"] |= tokens(prompt)
            if cid:
                b["conversation_ids"].add(cid)
            b["chas"] |= set(extract_chas(prompt))
            if theme:
                b["title"] = str(theme["title"])
                b["theme_id"] = theme["id"]
            touch(key, ts)
        else:
            # stop/session: estica o fim daquele assunto (mesmo com outra aba ativa)
            if not cid:
                continue
            theme_id = cid_theme.get(cid)
            key = f"theme:{theme_id}" if theme_id else f"cid:{cid}"
            if key not in buckets:
                if theme_id:
                    ensure_bucket(key, "", cid, theme_by_id(theme_id))
                else:
                    continue
            touch(key, ts)

    # 1 linha por assunto; duração = janela própria; empacota em sequência (sem overlap LAS)
    packed: List[Subject] = []
    if not order:
        save_subjects_for_day(day, [])
        return []

    usable: List[Tuple[str, datetime, int]] = []
    for key in order:
        b = buckets[key]
        first = b.get("first")
        last = b.get("last")
        if first is None or last is None:
            continue
        sec = max(0, int((last - first).total_seconds()))
        if sec < 60:
            continue
        usable.append((key, first, sec))

    if not usable:
        save_subjects_for_day(day, [])
        return []

    usable.sort(key=lambda x: x[1])
    cursor = usable[0][1]
    fb = fallback_end
    # alinha tz para comparar com os timestamps dos prompts
    if cursor.tzinfo is not None and fb.tzinfo is None:
        fb = fb.replace(tzinfo=cursor.tzinfo)
    elif fb.tzinfo is not None and cursor.tzinfo is None:
        cursor = cursor.replace(tzinfo=fb.tzinfo)

    wall_sec = max(0, int((fb - cursor).total_seconds()))
    if wall_sec < 60:
        save_subjects_for_day(day, [])
        return []

    total_sec = sum(sec for _, _, sec in usable)
    # Temas em abas paralelas geram janelas (last-first) que se sobrepõem no relógio.
    # Somar e empilhar em sequência empurrava o fim para o futuro (ex.: 14:25 às 13:00).
    # Comprime proporcionalmente para caber em [1º prompt, fallback_end] (= agora no dia corrente).
    alloc: List[Tuple[str, int]] = []
    if total_sec > wall_sec:
        remaining = wall_sec
        for i, (key, _first, sec) in enumerate(usable):
            if i == len(usable) - 1:
                part = remaining
            else:
                part = min(remaining, int(sec * wall_sec / total_sec))
            alloc.append((key, part))
            remaining -= part
        if alloc and remaining:
            k, p = alloc[-1]
            alloc[-1] = (k, max(0, p + remaining))
    else:
        alloc = [(key, sec) for key, _first, sec in usable]

    for key, sec in alloc:
        if sec < 60:
            continue
        b = buckets[key]
        start = cursor
        if start >= fb:
            break
        end = min(start + timedelta(seconds=sec), fb)
        if int((end - start).total_seconds()) < 60:
            break
        packed.append(
            Subject(
                id=f"pack-{abs(hash(key)) % 100000:05d}",
                title=str(b["title"]),
                start=_iso(start),
                end=_iso(end),
                theme_id=b.get("theme_id"),
                keywords=sorted(b["keywords"])[:40],
                conversation_ids=sorted(b["conversation_ids"]),
                prompt_count=int(b["prompt_count"]),
                chas=sorted(b["chas"]),
            )
        )
        cursor = end

    save_subjects_for_day(day, packed)
    data = load_state()
    data["cid_theme"] = cid_theme
    data.setdefault("day_slices", {})
    data["day_slices"][day.isoformat()] = [asdict(s) for s in packed]
    save_state(data)
    return packed


def subjects_slices_for_day(day: date) -> List[Subject]:
    data = load_state()
    rows = (data.get("day_slices") or {}).get(day.isoformat())
    if rows:
        return [_subject_from_dict(r) for r in rows]
    return subjects_for_day(day)
