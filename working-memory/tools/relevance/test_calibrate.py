import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("calibration", Path(__file__).with_name("calibrate.py"))
cal = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cal)


class CalibrationTests(unittest.TestCase):
    config = {"weights": {"signal": 2}, "thresholds": {"standard": 2, "wichtig": 5}}

    def test_markdown_id_join_and_unclear(self):
        md = """| Nr | Titel | Bewertung | Kommentar |
| --- | --- | --- | --- |
| 1 <!-- task-id:a; first_changed:2026-01-01 --> | Beispiel \\| Artefakt | W | |
| 2 <!-- task-id:b; --> | Muster | K | |
| 3 <!-- task-id:c; --> | Muster | U | |
| 4 <!-- task-id:d; --> | Muster | | |
"""
        self.assertEqual(cal.parse_labels(md), {"a": "W", "b": "K", "c": "U"})

    def test_empty_rating_table_is_valid(self):
        self.assertEqual(cal.parse_labels("| Nr | Bewertung |\n| --- | --- |\n| 1 | |"), {})

    def test_invalid_labels_missing_ids_and_conflicts(self):
        for md in ("| Bewertung |\n| X |", "| Bewertung |\n| W |",
                   "| Bewertung |\n| W <!-- task-id:a; --> |"):
            with self.assertRaises(ValueError):
                cal.parse_labels(md)
        with self.assertRaises(ValueError):
            cal.parse_labels("| Nr | Bewertung |\n| <!-- task-id:a; --> | W |\n| <!-- task-id:a; --> | K |")

    def test_confusion_with_unclear_and_missing(self):
        records = {"a": {"klasse": "wichtig"}, "b": {"klasse": "standard"},
                   "c": {"klasse": "kleinigkeit"}}
        result = cal.evaluate(records, {"a": "W", "b": "K", "c": "U", "d": "K"})
        self.assertEqual(result["labels_verwertbar"], 2)
        self.assertEqual(result["labels_unklar"], 1)
        self.assertEqual(result["labels_ohne_treffer"], 1)
        self.assertEqual(result["uebereinstimmung"], 0.5)
        self.assertEqual(result["konfusionsmatrix"]["standard"], dict.fromkeys(cal.CLASSES, 0))
        self.assertEqual(result["konfusionsmatrix"]["kleinigkeit"]["standard"], 1)

    def test_less_than_thirty_only_notice(self):
        records, labels = cal.synthetic_example(self.config)
        result = cal.search(records, dict(list(labels.items())[:29]), self.config)
        self.assertIsNone(result["vorschlag"])
        self.assertEqual(result["kandidaten"], 0)

    def test_grid_improves_and_preserves_input(self):
        # Human W begins at 4, whereas initial important boundary is 5.
        records = {str(i): {"features": {"signal": 2 if i >= 30 else 0}} for i in range(60)}
        labels = {str(i): "W" if i >= 30 else "K" for i in range(60)}
        result = cal.search(records, labels, self.config)
        self.assertEqual(result["baseline"]["uebereinstimmung"], 0.5)
        self.assertEqual(result["vorschlag"]["messung"]["uebereinstimmung"], 1.0)
        self.assertEqual(self.config["thresholds"]["wichtig"], 5)
        self.assertEqual(self.config["weights"]["signal"], 2)

    def test_weight_search_has_observable_effect(self):
        records = {str(i): {"features": {"signal": 0.95 if i < 30 else 1.9}} for i in range(60)}
        labels = {str(i): "K" if i < 30 else "W" for i in range(60)}
        cfg = {"weights": {"signal": 20}, "thresholds": {"standard": 16, "wichtig": 27}}
        result = cal.search(records, labels, cfg)
        self.assertLess(result["baseline"]["uebereinstimmung"], 1)
        self.assertEqual(result["vorschlag"]["messung"]["uebereinstimmung"], 1)
        self.assertNotEqual(result["vorschlag"]["weights"]["signal"], 20)

    def test_no_fabricated_standard_labels_or_one_sided_tuning(self):
        records, labels = cal.synthetic_example(self.config)
        result = cal.search(records, {k: "U" for k in labels}, self.config)
        self.assertIsNone(result["baseline"]["uebereinstimmung"])
        self.assertIsNone(result["vorschlag"])
        result = cal.search(records, {k: "W" for k in labels}, self.config)
        self.assertIsNone(result["vorschlag"])

    def test_missing_scores_block_search(self):
        records, labels = cal.synthetic_example(self.config)
        records.pop("synthetic-000")
        result = cal.search(records, labels, self.config)
        self.assertIsNone(result["vorschlag"])
        self.assertEqual(result["baseline"]["labels_ohne_treffer"], 1)

    def test_boundaries_and_invalid_feature(self):
        self.assertEqual(cal.classify(2, self.config), "standard")
        self.assertEqual(cal.classify(5, self.config), "wichtig")
        self.assertEqual(cal.feature_points({"features": {}}, self.config["weights"]), 0)
        with self.assertRaises(ValueError):
            cal.feature_points({"features": {"signal": float("nan")}}, self.config["weights"])


if __name__ == "__main__":
    unittest.main()
