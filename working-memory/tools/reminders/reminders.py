"""Offline reminder digest. Only the CLI performs I/O; projection/rules are pure."""
from __future__ import annotations

import argparse
import calendar
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

# Configuration: all reminder thresholds and presentation defaults live here.
DEFAULT_CONFIG = {
    "soon_days": 3, "stalled_days": 21, "no_due_days": 45,
    "waiting_days": 7, "completed_days": 3, "cooldown_days": 3,
    "overdue_daily_limit": 5, "max_entries": 15,
    "title_chars": 160, "source_chars": 120, "condition_chars": 140,
    "state_filename": "reminders-state.json", "owner": "Gleb",
    "archive_glob": "Library/Application Support/Dashboard Job Backup/archives/dashboard-*.tar.gz",
}
RULES = ("overdue", "due_soon", "waiting", "stalled", "no_due", "unclear_due", "completed")
LABELS = {
    "overdue": "überfällig", "due_soon": "bald fällig", "waiting": "nachfassen",
    "stalled": "Stillstand", "no_due": "Frist klären oder schließen",
    "unclear_due": "Frist unklar", "completed": "aktuell erledigt",
}
SOURCE_FIELDS = ("id", "source_id", "content_hash", "event_date", "title", "transcript", "observed_at")
MONTHS = dict(zip(("januar", "februar", "märz", "april", "mai", "juni", "juli", "august", "september", "oktober", "november", "dezember"), range(1, 13)))
WEEKDAYS = dict(zip(("montag", "dienstag", "mittwoch", "donnerstag", "freitag", "samstag", "sonntag"), range(7)))


@dataclass(frozen=True)
class Due:
    value: date | None
    status: str


@dataclass(frozen=True)
class DigestResult:
    text: str
    state: dict
    counts: dict
    shown: int
    omitted: int


def as_date(value):
    if type(value) is date:
        return value
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def parse_due(text, reference_date=None):
    """Recognize only complete, unambiguous expressions, anchored to source date."""
    if text is None or text == "" or (isinstance(text, str) and not text.strip()):
        return Due(None, "missing")
    if not isinstance(text, str):
        return Due(None, "unclear")
    raw = " ".join(text.casefold().strip().split())
    raw = re.sub(r"^(?:spätestens bis|bis zum|bis|zum|am)\s+", "", raw)
    iso = as_date(raw)
    if iso:
        return Due(iso, "parsed")
    ref = as_date(reference_date)
    match = re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", raw)
    if match:
        try:
            return Due(date(int(match[3]), int(match[2]), int(match[1])), "parsed")
        except ValueError:
            return Due(None, "unclear")
    match = re.fullmatch(r"ende (" + "|".join(MONTHS) + r")(?: (\d{4}))?", raw)
    if match and (match[2] or ref):
        year = int(match[2]) if match[2] else ref.year
        month = MONTHS[match[1]]
        try:
            return Due(date(year, month, calendar.monthrange(year, month)[1]), "parsed")
        except ValueError:
            return Due(None, "unclear")
    if ref:
        try:
            if raw in WEEKDAYS:
                return Due(ref + timedelta(days=(WEEKDAYS[raw] - ref.weekday()) % 7), "parsed")
            if raw in ("heute", "morgen", "übermorgen"):
                return Due(ref + timedelta(days=("heute", "morgen", "übermorgen").index(raw)), "parsed")
            match = re.fullmatch(r"in (\d{1,3}) tagen", raw)
            if match:
                return Due(ref + timedelta(days=int(match[1])), "parsed")
        except OverflowError:
            pass
    return Due(None, "unclear")


def owner_matches(actual, expected):
    def norm(s):
        return " ".join(re.findall(r"\w+", (s or "").casefold()))
    a, b = norm(actual), norm(expected)
    aliases = {"gleb", "gleb komzin", "komzin gleb"}
    return bool(a and b) and (a == b or a in aliases and b in aliases)


def rule_matches(task, today, owner, config=DEFAULT_CONFIG):
    due = parse_due(task.get("due_text"), task.get("due_reference_date"))
    first, last = as_date(task.get("first_changed")), as_date(task.get("last_changed"))
    age = (today - first).days if first else None
    idle = (today - last).days if last else None
    if task.get("status") == "done":
        return ["completed"] if idle is not None and 0 <= idle <= config["completed_days"] else []
    if task.get("status") not in ("open", "waiting"):
        return []
    hits = []
    if due.value and due.value < today:
        hits.append("overdue")
    if due.value and 0 <= (due.value - today).days <= config["soon_days"]:
        hits.append("due_soon")
    if idle is not None and idle > config["stalled_days"] and (due.status != "missing" or owner_matches(task.get("owner"), owner)):
        hits.append("stalled")
    if due.status == "missing" and age is not None and age > config["no_due_days"]:
        hits.append("no_due")
    if task.get("status") == "waiting" and idle is not None and idle > config["waiting_days"]:
        hits.append("waiting")
    if due.status == "unclear":
        hits.append("unclear_due")
    return hits


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _logical(entry):
    if entry["kind"] == "source":
        return {"kind": "source", "source": {k: entry["source"][k] for k in SOURCE_FIELDS}, "payload": deepcopy(entry["payload"])}
    if entry["kind"] == "human":
        return {k: deepcopy(entry[k]) for k in ("kind", "command_id", "actor_id", "payload")}
    raise ValueError("Unbekannte Journalart")


def normalize_record(row):
    """Support both canonical direct records and exported record_json envelopes."""
    if "record_json" not in row:
        return deepcopy(row)
    result = json.loads(row["record_json"]) if isinstance(row["record_json"], str) else deepcopy(row["record_json"])
    if not isinstance(result, dict):
        raise ValueError("Ungültiger Datensatz")
    result.setdefault("kind", row.get("kind"))
    result.setdefault("revision", row.get("sequence"))
    return result


def expand_journal(journal):
    """Apply the archive's accepted compact replacement generations exactly."""
    logical = []
    seen = set()
    rows = sorted((normalize_record(r) for r in journal), key=lambda r: r.get("revision", r.get("sequence", 0)))
    for row in rows:
        revision = row.get("revision", row.get("sequence"))
        if revision is None or revision in seen:
            raise ValueError("Fehlende oder doppelte Journalsequenz")
        seen.add(revision)
        if row["kind"] != "generation":
            logical.append(_logical(row))
            continue
        prior = {_hash(e): e for e in logical}
        following = []
        for packed in row["payload"]["entries"]:
            if set(packed) == {"new"}:
                entry = deepcopy(packed["new"])
            elif set(packed) == {"ref", "changes"} and packed["ref"] in prior:
                entry = deepcopy(prior[packed["ref"]])
                for change in packed["changes"]:
                    path = change["path"]
                    if not path:
                        entry = deepcopy(change["value"])
                        continue
                    parent = entry
                    for key in path[:-1]:
                        parent = parent[key]
                    if change.get("remove") is True:
                        del parent[path[-1]]
                    else:
                        parent[path[-1]] = deepcopy(change["value"])
            else:
                raise ValueError("Unbekannte Generationsreferenz")
            following.append(_logical(entry))
        logical = following
    return logical


def _change(item, observation, action, event_date):
    item["claim"] = observation.get("claim", item.get("claim", ""))
    if action == "owner_changed":
        item["owner"] = observation.get("owner")
    if action == "date_changed":
        item["due_text"] = observation.get("due_text")
        item["due_reference_date"] = event_date
    if action == "done":
        item["status"] = "done"
    elif action == "reopened":
        item["status"] = "waiting" if observation.get("work_state") == "waiting" else "open"
    elif action == "progress" and item["status"] not in ("done", "aborted"):
        if observation.get("work_state") in ("open", "waiting"):
            item["status"] = observation["work_state"]
    elif action == "condition_met" and item["status"] not in ("done", "aborted"):
        item["condition_text"], item["status"] = None, "open"


def reconstruct_tasks(journal, notes=(), today=None):
    """Read-only projection, source lifecycle plus explicit planning/decisions."""
    tasks, observations, protections, rejected = {}, {}, {}, {}
    source_metadata = {}
    for raw in notes:
        note = normalize_record(raw)
        note_data = note.get("note_json", {})
        if isinstance(note_data, str):
            note_data = json.loads(note_data)
        legacy = note_data.get("legacy_record", {})
        source_metadata[str(legacy.get("id", ""))] = (legacy.get("title"), legacy.get("meeting_date"))

    def new_task(wid, o, src, event_date):
        meta = source_metadata.get(str(src.get("source_id", "")), (None, None))
        return {
            "id": wid, "title": o.get("title", ""), "claim": o.get("claim", ""),
            "owner": o.get("owner"), "status": o.get("work_state") if o.get("work_state") in ("waiting", "done") else "open",
            "due_text": o.get("due_text"), "due_reference_date": event_date if o.get("due_text") else None,
            "condition_text": o.get("condition_text"), "matter": o.get("matter", o.get("subject", "")),
            "source_title": src.get("title") or meta[0] or "Quelle unbekannt",
            "source_date": src.get("event_date") or meta[1], "source_id": src.get("source_id"),
            "first_changed": event_date, "last_changed": event_date,
        }

    def patch_task(item, patch, when):
        for field, value in patch.items():
            if field == "due_date":
                item["due_text"], item["due_reference_date"] = value, None
            elif field in ("title", "owner", "status", "claim", "condition_text", "matter"):
                item[field] = "aborted" if field == "status" and value in ("cancelled", "dismissed", "aborted") else value
            elif field == "note" and not item.get("source_id"):
                item["claim"] = value
        item["last_changed"] = when

    def mutations(o):
        a = o.get("update")
        if a == "owner_changed": return {"owner": o.get("owner")}
        if a == "date_changed": return {"due_date": o.get("due_text")}
        if a == "done": return {"status": "done"}
        if a in ("progress", "reopened", "condition_met"):
            return {"status": "waiting" if a != "condition_met" and o.get("work_state") == "waiting" else "open"}
        return {}

    def equivalent(a, b):
        return " ".join(a.split()).casefold() == " ".join(b.split()).casefold() if isinstance(a, str) and isinstance(b, str) else a == b

    for entry in expand_journal(journal):
        payload = entry["payload"]
        if entry["kind"] == "source":
            src = entry["source"]
            when = src["event_date"]
            if today and when > today.isoformat():
                continue
            job = hashlib.sha256((src["id"] + ":" + payload["pipeline"]).encode()).hexdigest()
            for index, original in enumerate(payload["proposal"]["observations"]):
                o = deepcopy(original)
                oid = hashlib.sha256((job + ":observation:" + str(index)).encode()).hexdigest()
                wid = o.get("update_target") or oid
                observations[oid] = (o, src, when, wid)
                changes = mutations(o)
                blocked = any((k in protections.get(wid, {}) and not equivalent(v, protections[wid][k])) or (k in rejected.get(wid, {}) and equivalent(v, rejected[wid][k])) for k, v in changes.items())
                if payload.get("human_guard", "legacy") == "legacy" and wid in protections and changes:
                    blocked = True
                creates = (o.get("kind") == "commitment" and o.get("commitment_strength") in ("explicit", "accepted_request") and o.get("owner") and not o.get("update_target"))
                action = "created" if creates else o.get("update", "none")
                anonymous = re.fullmatch(r"(?:Speaker|Sprecher|Unknown Speaker|Unknown|Unbekannt)\s*\d*", o.get("owner") or "", re.I)
                if blocked or anonymous or o.get("required_review") or o.get("action_uncertainty", o.get("uncertainty")) or o.get("work_gate", {}).get("verdict", "supported") not in ("supported", "already_done"):
                    action = "none"
                if action == "none" or (action != "created" and not o.get("update_target")):
                    continue
                if wid not in tasks:
                    if action != "created":
                        raise ValueError("Unbekanntes Aufgabenänderungsziel")
                    tasks[wid] = new_task(wid, o, src, when)
                else:
                    _change(tasks[wid], o, action, when)
                    if "claim" in protections.get(wid, {}):
                        tasks[wid]["claim"] = protections[wid]["claim"]
                    tasks[wid]["last_changed"] = when
                    tasks[wid]["source_title"], tasks[wid]["source_date"] = src["title"], when
                    tasks[wid]["source_id"] = src["source_id"]
        else:
            when = payload["event_date"]
            if today and when > today.isoformat():
                continue
            action, target, patch = payload["action"], payload["target_id"], payload["patch"]
            if action in ("configure_team", "create_memory", "update_memory", "delete_memory", "confirm_knowledge"):
                continue
            if action == "create_task":
                tasks[target] = new_task(target, {"title": "", "owner": "Komzin, Gleb", "matter": "Eigene Planung"}, {"title": "Eigene Planung", "event_date": when}, when)
            if action in ("create_task", "update_task", "plan_task"):
                if target not in tasks:
                    raise ValueError("Unbekanntes Planungsziel")
                patch_task(tasks[target], patch, when)
                for k, v in patch.items():
                    if k in ("owner", "due_date") or k == "status" and action == "update_task":
                        protections.setdefault(target, {})[k] = v
                continue
            observation = observations.get(target)
            if observation is None:
                observation = next((v for v in observations.values() if v[3] == target), None)
            if observation is None:
                raise ValueError("Unbekanntes Entscheidungsziel")
            o, src, observed, wid = observation
            if action == "correct_confirm" and not (o.get("kind") == "commitment" or o.get("update_target")):
                continue  # Knowledge corrections do not create tasks.
            if action in ("approve", "correct_confirm"):
                if wid not in tasks:
                    tasks[wid] = new_task(wid, o, src, observed)
                elif o.get("update_target"):
                    _change(tasks[wid], o, o.get("update"), observed)
                    if "claim" in protections.get(wid, {}):
                        tasks[wid]["claim"] = protections[wid]["claim"]
                    tasks[wid]["source_title"], tasks[wid]["source_date"] = src["title"], observed
                    tasks[wid]["source_id"] = src["source_id"]
                for k, v in mutations(o).items():
                    protections.setdefault(wid, {})[k] = v
                    rejected.get(wid, {}).pop(k, None)
            if action == "reject":
                if not o.get("update_target") and wid in tasks:
                    tasks[wid]["status"] = "aborted"
                    tasks[wid]["last_changed"] = when
                rejected.setdefault(wid, {}).update(mutations(o))
            elif wid in tasks:
                patch_task(tasks[wid], patch, when)
                protections.setdefault(wid, {}).update(patch)
                for k in patch:
                    rejected.get(wid, {}).pop(k, None)
    return list(tasks.values())


def validate_state(state):
    if not isinstance(state, dict) or state.get("version") != 1 or not isinstance(state.get("last_sent"), dict):
        raise ValueError("Ungültige Zustandsdatei")
    for task_id, rules in state["last_sent"].items():
        if not isinstance(task_id, str) or not isinstance(rules, dict) or any(rule not in RULES or as_date(when) is None for rule, when in rules.items()):
            raise ValueError("Ungültige Zustandsdatei")


def _short(value, limit):
    text = " ".join(str(value or "").split())
    text = re.sub(r"([\\`*_\[\]<>#|])", r"\\\1", text)
    return text if len(text) <= limit else text[:limit - 1] + "…"


def build_digest(tasks, today, owner, state, config=DEFAULT_CONFIG):
    validate_state(state)
    updated = deepcopy(state)
    counts = dict.fromkeys(RULES, 0)
    candidates = []
    ids = set()
    for task in tasks:
        if task["id"] in ids:
            raise ValueError("Doppelte Aufgabenidentität")
        ids.add(task["id"])
        hits = rule_matches(task, today, owner, config)
        for rule in hits:
            counts[rule] += 1
        if hits:
            candidates.append((task, hits))
    # Slicing the sorted list makes the five oldest deterministic.
    overdue_order = sorted((t for t, h in candidates if "overdue" in h), key=lambda t: (parse_due(t.get("due_text"), t.get("due_reference_date")).value, t["id"]))
    daily_ids = {t["id"] for t in overdue_order[:config["overdue_daily_limit"]]}
    eligible = []
    for task, hits in candidates:
        fresh = []
        for rule in hits:
            previous = as_date(state["last_sent"].get(task["id"], {}).get(rule))
            cooldown = 1 if rule == "overdue" and task["id"] in daily_ids else max(1, config["cooldown_days"])
            if previous is None or (today - previous).days >= cooldown:
                fresh.append(rule)
        if fresh:
            due = parse_due(task.get("due_text"), task.get("due_reference_date"))
            eligible.append((min(RULES.index(r) for r in fresh), due.value or date.max, task.get("first_changed") or "9999-12-31", task["id"], task, fresh))
    eligible.sort(key=lambda row: row[:4])
    selected = eligible[:config["max_entries"]]
    omitted = len(eligible) - len(selected)
    lines = [f"# Arbeits-Memory · {today.isoformat()}", "", f"{len(selected)} Einträge · {omitted} weitere · {len(candidates) - len(eligible)} durch Sperrfrist zurückgestellt", ""]
    for _, _, _, _, task, hits in selected:
        due = parse_due(task.get("due_text"), task.get("due_reference_date"))
        first = as_date(task.get("first_changed"))
        age = f"{(today - first).days} Tage alt" if first and first <= today else "Alter unbekannt"
        deadline = due.value.isoformat() if due.value else "Frist unklar" if due.status == "unclear" else "ohne Frist"
        reasons = ", ".join(LABELS[r] for r in RULES if r in hits)
        if "waiting" in hits:
            reasons += ": " + _short(task.get("condition_text") or "Bedingung / wartende Person unbekannt", config["condition_chars"])
        lines.append(f"- **{_short(task['title'], config['title_chars'])}** · Besitzer: {_short(task.get('owner') or 'unbekannt', 80)} · {deadline}; {age} · Grund: {reasons} · Quelle: {_short(task.get('source_title') or 'unbekannt', config['source_chars'])}, {as_date(task.get('source_date')) or 'Datum unbekannt'}")
        updated["last_sent"].setdefault(task["id"], {}).update({r: today.isoformat() for r in hits})
    if not selected:
        lines.append("Keine neuen Meldungen.")
    if omitted:
        lines.extend(["", f"Weitere meldbare Aufgaben: {omitted}."])
    return DigestResult("\n".join(lines) + "\n", updated, counts, len(selected), omitted)


def load_state(path):
    path = Path(path)
    if not path.exists():
        return {"version": 1, "last_sent": {}}
    state = json.loads(path.read_text(encoding="utf-8"))
    validate_state(state)
    return state


def atomic_write(path, text):
    path = Path(path)
    fd, temp = tempfile.mkstemp(prefix=".reminders-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def save_state(path, state):
    validate_state(state)
    atomic_write(path, json.dumps(state, sort_keys=True, ensure_ascii=False, indent=2) + "\n")


def read_archive(path):
    """Stream both members in one tar invocation; never extract archive files."""
    journal, notes = [], []
    with tempfile.TemporaryFile(mode="w+t", dir=Path(__file__).resolve().parent) as errors:
        proc = subprocess.Popen(["tar", "-xzOf", str(path), "canonical/journal.jsonl", "canonical/notes.jsonl"], stdout=subprocess.PIPE, stderr=errors, text=True, encoding="utf-8")
        try:
            for line in proc.stdout:
                if not line.strip():
                    continue
                row = json.loads(line)
                value = normalize_record(row)
                if value.get("kind") in ("source", "human", "generation", "redaction"):
                    journal.append(value)
                elif "note_json" in value:
                    notes.append(value)
                else:
                    raise ValueError("Unbekanntes Archivschema")
            if proc.wait() != 0:
                raise ValueError("Archivstream fehlgeschlagen")
        finally:
            proc.stdout.close()
            if proc.poll() is None:
                proc.terminate()
                proc.wait()
    if not journal:
        raise ValueError("Leeres Journal")
    return journal, notes


def main(argv=None):
    parser = argparse.ArgumentParser(description="Lokaler Arbeits-Memory-Digest; keine Zustellung.")
    parser.add_argument("--archive", default="auto")
    parser.add_argument("--today", required=True)
    parser.add_argument("--owner", default=DEFAULT_CONFIG["owner"])
    parser.add_argument("--out", required=True)
    parser.add_argument("--cooldown-days", type=int, default=DEFAULT_CONFIG["cooldown_days"])
    args = parser.parse_args(argv)
    started = time.perf_counter()
    today = as_date(args.today)
    if today is None or args.cooldown_days < 1:
        parser.error("Datum oder Sperrfrist ungültig")
    root = Path(__file__).resolve().parent
    out = Path(args.out).resolve()
    if not out.is_relative_to(root) or out == root:
        parser.error("Ausgabe muss innerhalb tools/reminders liegen")
    state_path = out.parent / DEFAULT_CONFIG["state_filename"]
    if state_path.resolve() == out or not state_path.resolve().is_relative_to(root):
        parser.error("Ungültiger Zustandspfad")
    try:
        if args.archive == "auto":
            archives = list(Path.home().glob(DEFAULT_CONFIG["archive_glob"]))
            if not archives:
                raise ValueError("Kein Archiv")
            archive = max(archives, key=lambda p: p.name)
        else:
            archive = Path(args.archive).expanduser().resolve()
        state = load_state(state_path)
        journal, notes = read_archive(archive)
        tasks = reconstruct_tasks(journal, notes, today)
        config = {**DEFAULT_CONFIG, "cooldown_days": args.cooldown_days}
        result = build_digest(tasks, today, args.owner, state, config)
        out.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        atomic_write(out, result.text)
        save_state(state_path, result.state)
        metrics = {"counts": result.counts, "digest_entries": result.shown, "digest_characters": len(result.text), "digest_bytes": len(result.text.encode()), "remaining": result.omitted, "tasks": len(tasks), "runtime_seconds": round(time.perf_counter() - started, 3)}
        print(json.dumps(metrics, ensure_ascii=False, sort_keys=True))
        return 0
    except (ValueError, OSError, KeyError, TypeError, IndexError, AttributeError):
        # Never echo archive contents, titles, malformed JSON or tar diagnostics.
        print("Fehler: Archiv, Rekonstruktion, Zustand oder Ausgabe ungültig.", file=__import__("sys").stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
