"""Synthetic fixtures for the COMSOL table adapter, not physical results."""
import csv
import json
from pathlib import Path
import tempfile
import unittest

from canonicalize_export import COLUMNS, convert


class ExportMappingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.source = {
            "source_kind": "synthetic",
            "domain_topology": "single_convex_plate_without_holes",
            "field_definitions": {name: "synthetic adapter unit-test fixture" for name in COLUMNS[3:]},
            "coordinate_provenance": "bottom reference face Z=-0.004; fixture only"
        }
        (self.base / "source.json").write_text(json.dumps(self.source), encoding="utf-8")
        self.rows = ["-.5 -.5 -.004 0 0 0 0 0 0 0", ".5 -.5 -.004 0 0 0 0 0 0 0", "-.5 .5 -.004 0 0 0 0 0 0 0"]
        (self.base / "frame0.txt").write_text("% fixture\n" + "\n".join(self.rows), encoding="utf-8")
        (self.base / "frame1.txt").write_text("\n".join(reversed(self.rows)), encoding="utf-8")
        self.manifest = {"columns": list(COLUMNS), "source_sidecar": "source.json", "z_offset_m": .004,
                         "frames": [{"time_s": 0, "file": "frame0.txt"}, {"time_s": .01, "file": "frame1.txt"}]}
        (self.base / "manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")

    def test_reordering_keeps_ids_and_maps_reference_surface(self):
        path = convert(self.base / "manifest.json", self.base / "out")
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual([r["node_id"] for r in rows], ["0", "1", "2", "0", "1", "2"])
        self.assertEqual({r["z_m"] for r in rows}, {"0.0"})
        source = json.loads((self.base / "out/source.json").read_text())
        self.assertEqual(source["source_kind"], "synthetic")
        self.assertEqual(len(source["export_adapter"]["source_file_sha256"]), 2)

    def test_duplicate_points_are_not_silently_averaged(self):
        (self.base / "frame1.txt").write_text("\n".join(self.rows + [self.rows[0]]))
        with self.assertRaisesRegex(ValueError, "duplicate reference"):
            convert(self.base / "manifest.json", self.base / "out")
        self.assertFalse((self.base / "out").exists())

    def test_template_cannot_be_mistaken_for_completed_provenance(self):
        self.source["template_only"] = True
        (self.base / "source.json").write_text(json.dumps(self.source))
        with self.assertRaisesRegex(ValueError, "template_only"):
            convert(self.base / "manifest.json", self.base / "out")

    def test_mixed_top_bottom_rejected(self):
        (self.base / "frame1.txt").write_text("\n".join(self.rows).replace("-.004", ".004", 1))
        with self.assertRaisesRegex(ValueError, "mixed surface"):
            convert(self.base / "manifest.json", self.base / "out")


if __name__ == "__main__":
    unittest.main()
