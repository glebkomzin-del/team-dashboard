"""Offline calibration. W=wichtig, K=Klacks, U=unklar (excluded).

Only aggregate metrics and configuration proposals leave this module's CLI.
"""
from __future__ import annotations

import argparse
import copy
import html
import importlib.util
import json
import math
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
CLASSES = ("wichtig", "standard", "kleinigkeit")
LABELS = {"W": "wichtig", "K": "kleinigkeit"}


def relevance_module():
    spec = importlib.util.spec_from_file_location("relevance_core", ROOT / "relevance.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_labels(markdown):
    """Parse IDs from HTML comments, never join by mutable title or row number."""
    result = {}
    columns = None
    found = False
    for line in markdown.splitlines():
        if not line.strip().startswith("|"):
            columns = None
            continue
        cells = [html.unescape(c.strip()) for c in re.split(r"(?<!\\)\|", line.strip())[1:-1]]
        if "Bewertung" in cells:
            columns = cells.index("Bewertung")
            found = True
            continue
        if columns is None or all(re.fullmatch(r"[:\-\s]+", c) for c in cells):
            continue
        if len(cells) <= columns:
            raise ValueError("Ungültige Tabellenstruktur")
        label = cells[columns].strip().upper()
        if not label:
            continue
        if label not in ("W", "K", "U"):
            raise ValueError("Bewertung muss W, K oder U sein")
        match = re.search(r"task-id:([^;\s>]+)", line)
        if not match:
            raise ValueError("Bewertete Tabellenzeile ohne task-id")
        identifier = match.group(1)
        if identifier in result and result[identifier] != label:
            raise ValueError("Widersprüchliche doppelte Bewertung")
        result[identifier] = label
    if not found:
        raise ValueError("Keine Tabelle mit Bewertungsspalte")
    return result


def classify(points, config):
    limits = config["thresholds"]
    if points >= limits["wichtig"]:
        return "wichtig"
    if points >= limits["standard"]:
        return "standard"
    return "kleinigkeit"


def feature_points(record, weights):
    features = record.get("features")
    if not isinstance(features, dict):
        raise ValueError("Rastersuche benötigt gespeicherte Merkmale")
    total = 0.0
    for key, weight in weights.items():
        value = features.get(key, 0)
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError("Ungültiger Merkmalswert")
        total += value * weight
    return round(total, 4)


def evaluate(records, labels, config=None):
    """U is abstention, not standard; absent score IDs are reported separately."""
    matrix = {expected: {predicted: 0 for predicted in CLASSES} for expected in CLASSES}
    matched = correct = missing = uncertain = 0
    for identifier, label in labels.items():
        if label == "U":
            uncertain += 1
            continue
        record = records.get(identifier)
        if record is None:
            missing += 1
            continue
        expected = LABELS[label]
        predicted = (classify(feature_points(record, config["weights"]), config)
                     if config else record["klasse"])
        if predicted not in CLASSES:
            raise ValueError("Ungültige gespeicherte Klasse")
        matrix[expected][predicted] += 1
        matched += 1
        correct += expected == predicted
    recalls = []
    for expected in ("wichtig", "kleinigkeit"):
        support = sum(matrix[expected].values())
        if support:
            recalls.append(matrix[expected][expected] / support)
    return {
        "labels_verwertbar": matched, "labels_unklar": uncertain,
        "labels_ohne_treffer": missing, "korrekt": correct,
        "uebereinstimmung": correct / matched if matched else None,
        "macro_recall": sum(recalls) / len(recalls) if recalls else None,
        "konfusionsmatrix": matrix,
    }


def search(records, labels, config):
    """Small coordinate grid, in-sample only; no modification of config.json."""
    baseline = evaluate(records, labels, config)
    notice = "U ist unklar; die Klasse standard besitzt keinen menschlichen Positivmaßstab."
    if baseline["labels_verwertbar"] < 30:
        return {"baseline": baseline, "vorschlag": None, "kandidaten": 0,
                "hinweis": "Weniger als 30 verwertbare Labels: keine Rastersuche. " + notice}
    support = [sum(baseline["konfusionsmatrix"][c].values()) for c in ("wichtig", "kleinigkeit")]
    if not all(support):
        return {"baseline": baseline, "vorschlag": None, "kandidaten": 0,
                "hinweis": "Für einen Schwellenvergleich werden W und K benötigt. " + notice}
    if baseline["labels_ohne_treffer"]:
        return {"baseline": baseline, "vorschlag": None, "kandidaten": 0,
                "hinweis": "Bewertete IDs fehlen im Ergebnis: Quelle abgleichen. " + notice}
    variants = [(None, 1.0, copy.deepcopy(config["weights"]))]
    for key, weight in config["weights"].items():
        if weight:
            for factor in (0.75, 1.25):
                weights = dict(config["weights"])
                weights[key] = round(weight * factor, 4)
                variants.append((key, factor, weights))
    best_config = copy.deepcopy(config)
    best_metrics = baseline
    best_key = (baseline["macro_recall"], baseline["uebereinstimmung"], 0.0)
    candidates = 0
    for key, factor, weights in variants:
        # Five local offsets per boundary; tie-breaking prefers the original.
        for low_shift in (-2, -1, 0, 1, 2):
            for high_shift in (-2, -1, 0, 1, 2):
                low = config["thresholds"]["standard"] + low_shift
                high = config["thresholds"]["wichtig"] + high_shift
                if low >= high:
                    continue
                trial = {**config, "weights": weights,
                         "thresholds": {"standard": low, "wichtig": high}}
                metrics = evaluate(records, labels, trial)
                candidates += 1
                distance = abs(low_shift) + abs(high_shift) + (abs(factor - 1) if key else 0)
                rank = (metrics["macro_recall"], metrics["uebereinstimmung"], -distance)
                if rank > best_key:
                    best_config, best_metrics, best_key = trial, metrics, rank
    return {
        "baseline": baseline, "vorschlag": {"thresholds": best_config["thresholds"],
        "weights": best_config["weights"], "messung": best_metrics}, "kandidaten": candidates,
        "hinweis": "Nur Anpassung auf denselben Labels, keine unabhängige Qualitätsprüfung; "
                   "vor Übernahme weitere Labels und getrennte Prüfung verwenden. " + notice,
    }


def synthetic_example(config):
    """Sixty fabricated IDs, feature values only; no real meeting text."""
    records, labels = {}, {}
    keys = [k for k, w in config["weights"].items() if w > 0]
    if not keys:
        raise ValueError("Synthetischer Test benötigt ein positives Gewicht")
    key = keys[0]
    low, high = config["thresholds"]["standard"], config["thresholds"]["wichtig"]
    for i in range(60):
        identifier = "synthetic-%03d" % i
        important = i >= 30
        desired_points = high + 2 if important else low - 2
        records[identifier] = {"features": {key: desired_points / config["weights"][key]},
                               "klasse": "wichtig" if important else "kleinigkeit"}
        labels[identifier] = "W" if important else "K"
    return records, labels


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline-Kalibrierung, nur aggregierte Ausgabe")
    parser.add_argument("--ratings", type=Path, help="Ausgefüllte Markdown-Bewertungsliste")
    parser.add_argument("--scores", type=Path, default=ROOT / "relevance.jsonl")
    parser.add_argument("--config", type=Path, default=ROOT / "config.json")
    args = parser.parse_args(argv)
    try:
        config = relevance_module().load_config(args.config)
        if args.ratings is None:
            records, labels = synthetic_example(config)
            mode = "synthetisch"
        else:
            labels = parse_labels(args.ratings.read_text(encoding="utf-8"))
            records = {}
            for line in args.scores.read_text(encoding="utf-8").splitlines():
                record = json.loads(line)
                identifier = record["id"]
                if identifier in records:
                    raise ValueError("Doppelte Ergebnis-ID")
                records[identifier] = record
            mode = "bewertungsliste"
        output = {"modus": mode, "gespeicherte_klassen": evaluate(records, labels),
                  **search(records, labels, config)}
        print(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (OSError, ValueError, TypeError, KeyError):
        print("Kalibrierung fehlgeschlagen: Eingabeformat, Merkmale oder Pfade prüfen.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
