#!/usr/bin/env python3
"""Consolida wifi.jsonl + cursor.jsonl em diario/YYYY-MM-DD.md."""

from __future__ import annotations

import argparse
import json
import re
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
    weight: int = 1  # qtd de prompts (prioridade em overlap)

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
    """Compat: título a partir de um único prompt."""
    return summarize_topic_title([prompt or ""])


_CHA_RE = re.compile(r"\bCHA[\s\-_]*(\d{1,6})\b", re.IGNORECASE)
_WORD_RE = re.compile(r"[a-zà-ü0-9]{3,}", re.IGNORECASE)

_STOP_PT = {
    "que", "com", "para", "pra", "por", "uma", "uns", "umas", "dos", "das", "nos", "nas",
    "como", "quando", "onde", "qual", "quais", "isso", "esse", "essa", "este", "esta",
    "aqui", "ali", "também", "tambem", "muito", "mais", "menos", "ainda", "depois",
    "antes", "sobre", "entre", "sem", "ser", "ter", "fazer", "esta", "está", "estou",
    "voce", "você", "voces", "nós", "eles", "elas", "meu", "minha", "seu", "sua",
    "the", "and", "for", "with", "from", "this", "that", "have", "has", "was", "are",
    "pode", "quero", "precisa", "precisamos", "vamos", "hoje", "agora", "aí", "ai",
    "nao", "não", "sim", "ok", "okay", "obrigado", "valeu", "correto", "certo",
    "dia", "html", "file", "http", "https", "users", "user",
}

_TASK_VERBS = {
    "implementar", "ajustar", "corrigir", "melhorar", "criar", "adicionar", "validar",
    "montar", "gerar", "gravar", "salvar", "aplicar", "refatorar", "revisar", "analisar",
    "distribuir", "apontar", "configurar", "instalar", "mover", "deslocar", "editar",
    "atualizar", "remover", "excluir", "testar", "debugar", "alinhar", "otimizar",
}

_NEW_TOPIC_PREFIX = re.compile(
    r"^(agora|outro assunto|mudando(?:\s+para)?|nova demanda|pr[oó]ximo(?:\s+assunto)?|"
    r"em seguida|aparte|mudança de contexto)\b",
    re.IGNORECASE,
)


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


def _tokens(text: str) -> set:
    words = {w.lower() for w in _WORD_RE.findall(text or "")}
    return {w for w in words if w not in _STOP_PT and not w.isdigit()}


def prompt_similarity(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 1.0  # follow-ups curtos não forçam split
    return len(ta & tb) / len(ta | tb)


def _clean_prompt_seed(text: str) -> str:
    text = " ".join((text or "").split()).strip()
    text = re.sub(
        r"^(pode|poderia|consegue|tem como|quero|preciso|precisamos|vamos|"
        r"me ajuda[r]?|ajuda[r]?|se eu|se|eu)\s+",
        "",
        text,
        flags=re.IGNORECASE,
    )
    # segunda passada comum: "precisar que..." após remover "se eu"
    text = re.sub(
        r"^(precisar|quero|preciso)\s+(que\s+)?",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = text.strip(" \t-–—:|")
    return text


def _looks_like_new_task(prompt: str) -> bool:
    raw = (prompt or "").strip()
    if not raw:
        return False
    if _NEW_TOPIC_PREFIX.search(raw):
        return True
    cleaned = _clean_prompt_seed(raw).lower()
    first = cleaned.split()[0] if cleaned else ""
    if first in _TASK_VERBS:
        return True
    return False


def _prompt_title_score(prompt: str) -> float:
    p = (prompt or "").strip()
    if not p:
        return -999.0
    cleaned = _clean_prompt_seed(p)
    toks = _tokens(cleaned)
    score = float(len(toks) * 4 + min(len(cleaned), 120) / 8.0)
    if extract_chas(p):
        score += 25
    if any(v in toks for v in _TASK_VERBS):
        score += 18
    if _looks_like_new_task(p):
        score += 10
    if p.endswith("?"):
        score -= 22
    if re.search(r"\b(correto|certo|ok|isso|funcionou)\b\??$", p, re.IGNORECASE):
        score -= 25
    if re.search(r"\b(misturar|esses são|com base no que)\b", p, re.IGNORECASE):
        score -= 15
    if len(p) < 35:
        score -= 12
    # penaliza títulos genéricos
    if toks <= {"melhorar", "isso", "assunto", "assuntos"}:
        score -= 20
    return score


def summarize_topic_title(prompts: List[str], max_len: int = 72) -> str:
    """
    Título estilo mensagem de commit: curto, objetivo, preferindo CHA + ação.
    Heurística local (sem IA online).
    """
    prompts = [p.strip() for p in prompts if (p or "").strip()]
    if not prompts:
        return "Assunto sem título"

    chas: List[str] = []
    seen = set()
    for p in prompts:
        for c in extract_chas(p):
            if c not in seen:
                seen.add(c)
                chas.append(c)

    # escolhe o prompt mais “commitável” (ação > pergunta)
    if len(prompts) >= 5:
        pool = prompts[-(max(4, len(prompts) // 2)) :]
    else:
        pool = prompts
    seed_raw = max(pool, key=_prompt_title_score)
    # se o melhor ainda for pergunta/fraco, sintetiza pelos tokens do grupo
    if _prompt_title_score(seed_raw) < 18 and len(prompts) > 1:
        alt = max(prompts, key=_prompt_title_score)
        if _prompt_title_score(alt) > _prompt_title_score(seed_raw):
            seed_raw = alt

    seed = _clean_prompt_seed(seed_raw)
    if len(_tokens(seed)) < 2 and len(prompts) > 1:
        seed = _clean_prompt_seed(max(prompts, key=_prompt_title_score))

    cut = seed
    for sep in [". ", "? ", "! ", " — ", " - "]:
        idx = seed.find(sep)
        if 12 <= idx <= max_len:
            cut = seed[:idx]
            break
    else:
        cut = seed[:max_len]

    cut = cut.rstrip(" ,;:?!")
    if seed_raw.strip().endswith("?") and not any(v in _tokens(cut) for v in _TASK_VERBS):
        cut = re.sub(
            r"^(se eu|se|o que|qual|quando|onde|por que|porque)\s+",
            "",
            cut,
            flags=re.IGNORECASE,
        ).strip()

    if cut and cut[0].isupper() and len(cut) > 1:
        first_word = cut.split()[0]
        if not (first_word.isupper() and len(first_word) <= 4):
            cut = cut[0].lower() + cut[1:]

    weak = (
        _prompt_title_score(seed_raw) < 16
        or _tokens(cut) <= {"melhorar", "isso", "assunto", "assuntos"}
        or len(_tokens(cut)) < 3
    )
    if weak and len(prompts) >= 3:
        freq: Dict[str, int] = {}
        for p in prompts:
            for t in _tokens(_clean_prompt_seed(p)):
                freq[t] = freq.get(t, 0) + 1
        verbs = [w for w, n in sorted(freq.items(), key=lambda x: (-x[1], x[0])) if w in _TASK_VERBS]
        nouns = [
            w
            for w, n in sorted(freq.items(), key=lambda x: (-x[1], x[0]))
            if w not in _TASK_VERBS and n >= 2
        ][:4]
        parts: List[str] = []
        if verbs:
            parts.append(verbs[0])
        parts.extend(nouns[:3])
        if parts:
            cut = " ".join(parts)

    # reforço só com tokens frequentes e “úteis”
    if len(prompts) >= 3 and not weak:
        freq = {}
        seed_toks = _tokens(cut)
        for p in prompts:
            for t in _tokens(p):
                if t not in seed_toks:
                    freq[t] = freq.get(t, 0) + 1
        extra = []
        for w, n in sorted(freq.items(), key=lambda x: (-x[1], x[0])):
            if n >= 4 or (n >= 3 and w in _TASK_VERBS):
                extra.append(w)
            if len(extra) >= 2:
                break
        if extra and len(cut) < max_len - 12:
            add = " / ".join(extra)
            if add.lower() not in cut.lower():
                cut = f"{cut} ({add})"

    if len(cut) > max_len:
        cut = cut[: max_len - 1].rstrip(" ,;:/") + "…"
    if not cut:
        cut = "Assunto sem título"

    if chas:
        head = chas[0] if len(chas) == 1 else f"{chas[0]}+{len(chas) - 1}"
        body = _CHA_RE.sub("", cut).strip(" -–—:|")
        body = " ".join(body.split())
        if body:
            return f"{head}: {body}"[: max_len + 12]
        return head

    return cut


def _should_split_topic(
    group_prompts: List[str],
    new_prompt: str,
    gap: timedelta,
    topic_gap: timedelta,
    *,
    split_on_cha: bool,
    split_on_similarity: bool,
    similarity_threshold: float,
) -> bool:
    if gap >= topic_gap:
        return True

    new_prompt = (new_prompt or "").strip()
    if not new_prompt:
        return False

    if split_on_cha:
        group_chas = set()
        for p in group_prompts:
            group_chas.update(extract_chas(p))
        new_chas = set(extract_chas(new_prompt))
        if group_chas and new_chas and new_chas.isdisjoint(group_chas):
            return True

    if len(new_prompt) < 50:
        return False

    if not split_on_similarity:
        return False

    new_toks = _tokens(new_prompt)
    if len(new_toks) < 5:
        return False

    group_toks: set = set()
    for p in group_prompts:
        group_toks |= _tokens(p)
    shared = group_toks & new_toks
    # mesma linha temática (ex.: assuntos/worklog/apontamento)
    if len(shared) >= 2:
        return False

    recent = group_prompts[-5:] if len(group_prompts) >= 5 else group_prompts
    best = max(prompt_similarity(p, new_prompt) for p in recent)
    is_new = _looks_like_new_task(new_prompt)
    is_question = new_prompt.endswith("?")

    # perguntas de continuidade quase nunca abrem assunto novo
    if is_question and not is_new:
        return False

    if is_new and best < (similarity_threshold + 0.08):
        return True

    # pedido afirmativo longo e bem diferente do grupo
    if (not is_question) and len(new_prompt) >= 70 and best < similarity_threshold:
        return True

    return False


def _subtract_time_ranges(
    start: datetime, end: datetime, blockers: List[Tuple[datetime, datetime]]
) -> List[Tuple[datetime, datetime]]:
    free = [(start, end)]
    for b0, b1 in sorted(blockers, key=lambda x: x[0]):
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


def resolve_topic_overlaps(
    topics: List[Interval], min_minutes: int = 5
) -> List[Interval]:
    """
    Remove sobreposição entre assuntos de conversas diferentes.
    Prioriza quem tem mais prompts (weight); sobras curtas demais são descartadas.
    """
    if not topics:
        return []
    min_sec = min_minutes * 60
    # reivindica tempo do mais “forte” para o mais fraco
    ordered = sorted(
        topics,
        key=lambda t: (-int(t.weight or 1), -t.seconds, t.start),
    )
    kept: List[Interval] = []
    for t in ordered:
        blockers = [(k.start, k.end) for k in kept]
        parts = _subtract_time_ranges(t.start, t.end, blockers)
        # se several parts, fica com o maior pedaço (evita fragmentar título)
        if not parts:
            continue
        parts.sort(key=lambda x: (x[1] - x[0]).total_seconds(), reverse=True)
        a0, a1 = parts[0]
        if int((a1 - a0).total_seconds()) < min_sec:
            continue
        kept.append(Interval(a0, a1, label=t.label, weight=t.weight))
    kept.sort(key=lambda t: t.start)
    return kept


def build_topics(
    rows: List[Dict[str, Any]],
    day_start: datetime,
    day_end: datetime,
    topic_gap_minutes: int,
    fallback_end: datetime,
    cfg: Optional[Dict[str, Any]] = None,
) -> List[Interval]:
    """
    Assuntos sticky locais (assuntos_engine):
    - ao longo do dia, verifica se o prompt/tarefa ainda é o mesmo tema
    - se for, estende e no máximo atualiza o título estável
    - se não for, fecha e abre outro
    - temas conhecidos (ex. worklog) usam título fixo, sem copiar o prompt
    """
    cfg = cfg or {}
    min_minutes = int(cfg.get("topic_min_minutes", 1))
    day = day_start.date()

    try:
        import assuntos_engine as ae
    except Exception:
        ae = None

    topics: List[Interval] = []
    if ae is not None:
        subjects = ae.rebuild_day_from_prompts(
            rows,
            day,
            gap_minutes=0,
            fallback_end=fallback_end,
        )
        for sub in subjects:
            try:
                start = sub.start_dt()
                end = sub.end_dt()
            except Exception:
                continue
            if end <= start:
                end = start + timedelta(minutes=1)
            if end <= day_start or start >= day_end:
                continue
            topics.append(
                Interval(
                    start=start,
                    end=end,
                    label=sub.title,
                    weight=max(1, int(sub.prompt_count or 1)),
                )
            )
    topics.sort(key=lambda i: i.start)
    topics = resolve_topic_overlaps(topics, min_minutes=min_minutes)
    # junta fatias consecutivas com o mesmo título
    merged: List[Interval] = []
    for t in topics:
        if merged and merged[-1].label == t.label and t.start <= merged[-1].end:
            prev = merged[-1]
            merged[-1] = Interval(
                start=prev.start,
                end=max(prev.end, t.end),
                label=prev.label,
                weight=prev.weight + t.weight,
            )
        else:
            merged.append(t)
    return merged


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

    topics = build_topics(cursor_rows, day_start, day_end, topic_gap, fallback_end, cfg)
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
