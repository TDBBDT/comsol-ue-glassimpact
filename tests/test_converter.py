import csv
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from converter.interpolation import SurfaceProjector, normalize
from converter.model import COLUMNS, FIELDS, read_config
from converter.pipeline import convert, sha256
from converter.readers import load_series


class InputFixture(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.raw = self.root / "raw"
        self.raw.mkdir()
        source = {"source_kind": "synthetic", "coordinate_provenance": "unit-test reference coordinates",
                  "domain_topology": "single_convex_plate_without_holes",
                  "field_definitions": {field: "unit-test fixture" for field in FIELDS}}
        (self.raw / "source.json").write_text(json.dumps(source), encoding="utf-8")
        self.coordinates = [(-0.5, -0.5), (0.5, -0.5), (-0.5, 0.5), (0.5, 0.5), (0, 0)]
        self.rows = []
        for frame, time in enumerate([0, 0.001, 0.005]):
            for node, (x, y) in enumerate(self.coordinates):
                self.rows.append([time, node, x, y, 0, (frame - 1) * 0.001 + x * 0.0001,
                                  y * 0.0002, -frame * 0.001, 10 + frame * 10 + x * 2,
                                  5 + frame * 5, 0.1 * frame, 2 + frame])
        self.write_rows()
        self.config = self.root / "config.yaml"
        self.config.write_text(json.dumps({"texture_resolution": [8, 6], "plate_size_m": [1, 1],
                                           "plate_origin_m": [-0.5, -0.5], "write_damage_png16": True}), encoding="utf-8")

    def tearDown(self):
        self.temporary.cleanup()

    def write_rows(self, header=COLUMNS):
        with (self.raw / "surface.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(header)
            writer.writerows(self.rows)

    def test_valid_nonuniform_times(self):
        series = load_series(self.raw)
        np.testing.assert_array_equal(series.times, [0, 0.001, 0.005])
        self.assertEqual(series.values.shape, (3, 5, 7))

    def test_missing_field(self):
        self.write_rows(COLUMNS[:-1])
        with self.assertRaisesRegex(ValueError, "missing required fields"):
            load_series(self.raw)

    def test_duplicate_header(self):
        self.write_rows(list(COLUMNS[:-1]) + ["damage"])
        with self.assertRaisesRegex(ValueError, "duplicated CSV header"):
            load_series(self.raw)

    def test_nan_rejected(self):
        self.rows[0][5] = "NaN"
        self.write_rows()
        with self.assertRaisesRegex(ValueError, "NaN or infinity"):
            load_series(self.raw)

    def test_duplicate_node_or_time_frame(self):
        self.rows.insert(1, self.rows[0].copy())
        self.write_rows()
        with self.assertRaisesRegex(ValueError, "Duplicate node_id"):
            load_series(self.raw)

    def test_out_of_order_time(self):
        self.rows = self.rows[5:10] + self.rows[:5] + self.rows[10:]
        self.write_rows()
        with self.assertRaisesRegex(ValueError, "strictly increasing"):
            load_series(self.raw)

    def test_missing_node(self):
        self.rows.pop(5)
        self.write_rows()
        with self.assertRaisesRegex(ValueError, "Node IDs/count changed"):
            load_series(self.raw)

    def test_moving_coordinates(self):
        self.rows[5][2] += 0.001
        self.write_rows()
        with self.assertRaisesRegex(ValueError, "Reference coordinates moved"):
            load_series(self.raw)

    def test_multilayer_duplicate_xy(self):
        self.rows[1][2:4] = self.rows[0][2:4]
        self.write_rows()
        with self.assertRaisesRegex(ValueError, "Duplicate XY"):
            load_series(self.raw)

    def test_damage_healing_rejected(self):
        self.rows[10][10] = 0.09
        self.write_rows()
        with self.assertRaisesRegex(ValueError, "Damage healing"):
            load_series(self.raw)

    def test_damage_out_of_range(self):
        self.rows[-1][10] = 1.01
        self.write_rows()
        with self.assertRaisesRegex(ValueError, "Damage must lie"):
            load_series(self.raw)

    def test_provenance_required(self):
        (self.raw / "source.json").unlink()
        with self.assertRaisesRegex(ValueError, "Missing source provenance"):
            load_series(self.raw)

    def test_template_is_not_real_provenance(self):
        path = self.raw / "source.json"
        source = json.loads(path.read_text())
        source.update(source_kind="comsol", template_only=True)
        path.write_text(json.dumps(source))
        with self.assertRaisesRegex(ValueError, "is a template"):
            load_series(self.raw)

    def test_topology_not_silently_bridged(self):
        path = self.raw / "source.json"
        source = json.loads(path.read_text())
        source["domain_topology"] = "plate_with_hole"
        path.write_text(json.dumps(source))
        with self.assertRaisesRegex(ValueError, "topology-aware"):
            load_series(self.raw)

    def test_binary_decode_time_coordinates_and_hash(self):
        output = self.root / "output"
        metadata = convert(self.raw, output, self.config, make_preview=False)
        self.assertEqual(metadata["times_seconds"], [0, 0.001, 0.005])
        self.assertEqual(metadata["duration_seconds"], 0.005)
        self.assertEqual(metadata["shape"], [3, 6, 8, 4])
        self.assertEqual(metadata["frame_bytes"], 8 * 6 * 8)
        self.assertEqual(metadata["source_kind"], "synthetic")
        self.assertEqual(metadata["row_zero"], "y_min")
        self.assertEqual(metadata["max_damage_per_frame"][2], float(np.float16(0.2)))
        array = np.fromfile(output / "displacement.rgba16f", dtype="<f2").reshape(3, 6, 8, 4)
        mins = np.array(metadata["displacement_min_m"])
        spans = np.array(metadata["displacement_max_m"]) - mins
        decoded = array[:, :, :, :3].astype(float) * spans + mins
        self.assertLess(decoded[1, 0, 0, 1], 0)  # row zero is y_min
        self.assertGreater(decoded[1, -1, 0, 1], 0)
        self.assertLess(decoded[-1, 2, 2, 2], 0)  # local W sign is retained
        np.testing.assert_allclose(decoded[-1, :, :, 2], -0.002, atol=1e-6)
        self.assertEqual(metadata["hashes"]["state.rgba16f"], sha256(output / "state.rgba16f"))
        state = np.fromfile(output / "state.rgba16f", dtype="<f2").reshape(3, 6, 8, 4)
        self.assertTrue((np.diff(state[:, :, :, 0].astype(float), axis=0) >= 0).all())
        from PIL import Image
        png = np.asarray(Image.open(output / "damage_png16" / "damage_0002.png"))
        np.testing.assert_array_equal(png, np.full((6, 8), 13107))

    def test_normalization_global_not_each_frame(self):
        output = self.root / "output"
        metadata = convert(self.raw, output, self.config, make_preview=False)
        state = np.fromfile(output / "state.rgba16f", dtype="<f2").reshape(3, 6, 8, 4)
        self.assertLess(float(state[0, :, :, 1].max()), 0.1)
        self.assertGreater(float(state[2, :, :, 1].min()), 0.9)
        self.assertEqual(metadata["stress1_range_Pa"], [9.0, 31.0])

    def test_existing_output_not_overwritten(self):
        output = self.root / "output"
        output.mkdir()
        keep = output / "keep.txt"
        keep.write_text("user work")
        with self.assertRaisesRegex(ValueError, "not empty"):
            convert(self.raw, output, self.config, make_preview=False)
        self.assertEqual(keep.read_text(), "user work")

    def test_float16_healing_amplification_rejected(self):
        midpoint = (float(np.float16(0.5)) + float(np.nextafter(np.float16(0.5), np.float16(1)))) / 2
        for index, row in enumerate(self.rows):
            row[10] = [0, midpoint + 1e-9, midpoint - 1e-9][index // 5]
        self.write_rows()
        load_series(self.raw)  # raw decrease is within configured tolerance
        with self.assertRaisesRegex(ValueError, "Encoded damage decreases"):
            convert(self.raw, self.root / "output", self.config, make_preview=False)

    def test_processed_validator_detects_tampering(self):
        from validator.processed import validate_processed
        output = self.root / "output"
        convert(self.raw, output, self.config, make_preview=False)
        self.assertTrue(validate_processed(output)["encoded_damage_monotonic"])
        path = output / "state.rgba16f"
        with path.open("r+b") as handle:
            handle.write(b"\x01\x01")
        with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
            validate_processed(output)

    def test_processed_validator_detects_truncation(self):
        from validator.processed import validate_processed
        output = self.root / "output"
        convert(self.raw, output, self.config, make_preview=False)
        path = output / "displacement.rgba16f"
        with path.open("r+b") as handle:
            handle.truncate(12)
        with self.assertRaisesRegex(ValueError, "Invalid byte size"):
            validate_processed(output)


class InterpolationTests(unittest.TestCase):
    def test_exact_linear_field_at_texel_centers(self):
        xy = np.array([[-0.5, -0.5], [0.5, -0.5], [-0.5, 0.5], [0.5, 0.5], [0.13, -0.09]])
        projector = SurfaceProjector.build(xy, [7, 5], [-0.5, -0.5], [1, 1])
        result = projector.interpolate((2 * xy[:, 0] - 3 * xy[:, 1] + 4)[:, None])[:, :, 0]
        xx, yy = np.meshgrid(-0.5 + (np.arange(7) + 0.5) / 7, -0.5 + (np.arange(5) + 0.5) / 5)
        np.testing.assert_allclose(result, 2 * xx - 3 * yy + 4, rtol=0, atol=1e-12)

    def test_outside_hull_zero_no_extrapolation(self):
        xy = np.array([[-0.5, -0.5], [0.5, -0.5], [-0.5, 0.5]])
        projector = SurfaceProjector.build(xy, [8, 8], [-0.5, -0.5], [1, 1])
        field = projector.interpolate(np.ones((3, 1)))[:, :, 0]
        self.assertFalse(projector.coverage[-1, -1])
        self.assertEqual(field[-1, -1], 0)
        self.assertEqual(field[0, 0], 1)

    def test_degenerate_range(self):
        actual = normalize(np.full((2, 3), 7.0), np.full(3, 7.0), np.full(3, 7.0))
        np.testing.assert_array_equal(actual, 0)


if __name__ == "__main__":
    unittest.main()
