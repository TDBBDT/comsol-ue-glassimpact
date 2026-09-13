"""Convert explicitly mapped single-time COMSOL tables to the strict CSV contract.

This adapter does not solve physics, invent damage, deduplicate mesh corners, or
accept COMSOL's multi-time wide tables. All fields must already be SI quantities.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Dict, List, Tuple

COLUMNS = ("x_m", "y_m", "z_m", "u_m", "v_m", "w_m", "sigma1_Pa",
           "von_mises_Pa", "damage", "strain_energy_J_m3")
Point = Tuple[float, float, float]


def read_frame(path: Path, columns: List[str], delimiter: str,
               z_offset: float) -> Dict[Point, List[float]]:
    """Use stable reference sample IDs; reject duplicate / mixed-surface points."""
    if len(columns) != len(COLUMNS) or set(columns) != set(COLUMNS):
        raise ValueError("Manifest columns must contain each of the ten SI fields exactly once.")
    if delimiter not in ("whitespace", "comma", "tab"):
        raise ValueError("delimiter must be whitespace, comma, or tab.")
    result: Dict[Point, List[float]] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith(("%", "#")):
            continue
        tokens = (line.split() if delimiter == "whitespace" else
                  next(csv.reader([line], delimiter="," if delimiter == "comma" else "\t")))
        if len(tokens) != len(COLUMNS):
            raise ValueError(f"{path}:{line_number}: expected ten numeric columns; export one time per file.")
        try:
            data = dict(zip(columns, map(float, tokens)))
        except ValueError as exc:
            raise ValueError(f"{path}:{line_number}: not numeric SI data; comment headers with %.") from exc
        if not all(math.isfinite(v) for v in data.values()):
            raise ValueError(f"{path}:{line_number}: nonfinite physical field.")
        if abs(data["z_m"] + z_offset) > 1e-10:
            raise ValueError(f"{path}:{line_number}: wrong reference Z or mixed surface layers.")
        point = (round(data["x_m"], 12), round(data["y_m"], 12), 0.0)
        if point in result:
            raise ValueError(f"{path}:{line_number}: duplicate reference sample {point}; export unique points.")
        result[point] = [data[name] for name in COLUMNS[3:]]
    if len(result) < 3:
        raise ValueError(f"{path}: fewer than three samples.")
    return result


def convert(manifest_path: Path, output: Path) -> Path:
    """Validate all frames before creating a new output directory."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    base = manifest_path.parent
    sidecar_path = base / manifest["source_sidecar"]
    source = json.loads(sidecar_path.read_text(encoding="utf-8-sig"))
    if source.get("template_only", False):
        raise ValueError("Complete source.json provenance and remove template_only before conversion.")
    if source.get("source_kind") not in ("comsol", "synthetic"):
        raise ValueError("source_kind must explicitly be comsol or synthetic.")
    if source.get("domain_topology") != "single_convex_plate_without_holes":
        raise ValueError("This surface exporter targets one convex, unperforated plate only.")
    if not set(COLUMNS[3:]).issubset(source.get("field_definitions", {})):
        raise ValueError("source.json must define all seven physical fields.")
    if not source.get("coordinate_provenance"):
        raise ValueError("source.json must identify the reference surface.")
    records = manifest["frames"]
    times = [float(record["time_s"]) for record in records]
    if len(times) < 2 or times[0] != 0 or not all(math.isfinite(t) for t in times):
        raise ValueError("At least two finite times starting at zero are required.")
    if any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError("Manifest times must be strictly increasing.")
    z_offset = float(manifest.get("z_offset_m", 0))
    if not math.isfinite(z_offset):
        raise ValueError("z_offset_m must be finite.")
    frames = []
    hashes = {}
    for record in records:
        path = base / record["file"]
        frames.append(read_frame(path, manifest["columns"], manifest.get("delimiter", "whitespace"), z_offset))
        hashes[record["file"]] = hashlib.sha256(path.read_bytes()).hexdigest()
    points = sorted(frames[0])
    if any(set(frame) != set(points) for frame in frames[1:]):
        raise ValueError("Reference sample coordinates change across time; use fixed reference sampling.")
    if output.exists():
        raise ValueError(f"Refusing to overwrite existing output directory: {output}")
    output.mkdir(parents=True)
    target = output / "surface.csv"
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("time_s", "node_id") + COLUMNS)
        for time, frame in zip(times, frames):
            for node_id, point in enumerate(points):
                writer.writerow((time, node_id, *point, *frame[point]))
    source["export_adapter"] = {
        "name": "canonicalize_export_v1", "reference_rounding_decimals": 12,
        "raw_z_offset_m": z_offset, "source_file_sha256": hashes,
        "node_id_semantics": "sorted_reference_export_point_id_not_solver_node_id"
    }
    (output / "source.json").write_text(json.dumps(source, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        print(convert(args.manifest, args.output))
    except (ValueError, KeyError, OSError) as exc:
        parser.exit(2, f"Export mapping failed: {exc}\n")


if __name__ == "__main__":
    main()
