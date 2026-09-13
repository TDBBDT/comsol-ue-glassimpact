"""Deterministic artificial radial pattern. NOT a mechanics/fracture simulation."""
import argparse
import csv
import json
from pathlib import Path

import numpy as np

from converter.model import COLUMNS, FIELDS


def generate(output: Path, frames: int = 32, grid: int = 65, seed: int = 163) -> None:
    if frames < 2 or grid < 5:
        raise ValueError("Need >=2 frames and >=5 grid nodes per edge.")
    if output.exists() and any(output.iterdir()):
        raise ValueError(f"Refusing to overwrite nonempty sample directory: {output}")
    output.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    axis = np.linspace(-0.5, 0.5, grid)
    xx, yy = np.meshgrid(axis, axis)
    xy = np.column_stack((xx.ravel(), yy.ravel()))
    interior = (np.abs(xy[:, 0]) < 0.5) & (np.abs(xy[:, 1]) < 0.5)
    center = np.linalg.norm(xy, axis=1) == 0
    xy[interior & ~center] += rng.uniform(-0.22 / (grid - 1), 0.22 / (grid - 1), (np.count_nonzero(interior & ~center), 2))
    x, y = xy.T
    radius = np.hypot(x, y)
    angle = np.arctan2(y, x)
    cracks = np.zeros(len(x))
    # These designer-chosen rays intentionally break symmetry; they predict no glass physics.
    for ray in [0.13, 0.83, 1.66, 2.38, 3.03, 3.86, 4.6, 5.5, 6.0]:
        delta = np.arctan2(np.sin(angle - ray), np.cos(angle - ray))
        distance = radius * np.abs(np.sin(delta))
        line = np.exp(-(distance / 0.009) ** 2) * (np.cos(delta) > 0)
        cracks = np.maximum(cracks, line)
    envelope = (np.maximum(0, 1 - (2 * x) ** 2) * np.maximum(0, 1 - (2 * y) ** 2)) ** 2
    times = np.linspace(0, 0.02, frames)
    with (output / "surface.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        for time in times:
            progress = time / times[-1]
            activation = 1 - np.exp(-progress * 15)
            front = np.clip((0.43 * progress - radius + 0.025) / 0.04, 0, 1)
            core = np.exp(-(radius / 0.034) ** 2)
            damage = 0.98 * activation * np.maximum(cracks * front, core) * np.minimum(1, envelope * 6)
            pulse = (1 - np.exp(-progress * 18)) * np.exp(-progress * 2.5)
            w = -0.0009 * pulse * np.sin(np.pi * (0.55 + progress)) * envelope * np.exp(-(radius / 0.3) ** 2)
            u = 0.00004 * pulse * x * envelope
            v = 0.00004 * pulse * y * envelope
            sigma1 = 32e6 * pulse * (0.2 + 0.8 * np.exp(-(radius / 0.23) ** 2)) * envelope * (1 - 0.7 * damage)
            vm = 0.82 * sigma1
            energy = sigma1 ** 2 / (2 * 70e9)
            fields = np.column_stack((u, v, w, sigma1, vm, damage, energy))
            for node_id, (point, field) in enumerate(zip(xy, fields)):
                writer.writerow([f"{time:.15g}", node_id, f"{point[0]:.15g}", f"{point[1]:.15g}", 0,
                                 *(f"{value:.15g}" for value in field)])
    source = {
        "source_kind": "synthetic", "generator": "tools/generate_synthetic.py", "seed": seed,
        "warning": "Artificial growing rays and analytic displacements. Not COMSOL, not a validated fracture solution.",
        "coordinate_provenance": "Fixed local reference plate midsurface z=0; irregular jittered interior nodes with exact clamped boundary nodes.",
        "domain_topology": "single_convex_plate_without_holes",
        "field_definitions": {field: f"Synthetic illustrative {field}; analytic designer pattern, no governing equation solved." for field in FIELDS},
        "frame_count": frames, "node_count": len(xy), "duration_seconds": 0.02,
        "plate_size_m": [1.0, 1.0], "plate_thickness_m": 0.008, "impact_uv": [0.5, 0.5],
        "physics_validated": False, "damage_irreversibility": "Nondecreasing analytical activation by construction.",
        "purpose": "Validate field interpolation, encoding, time playback, materials and camera presentation only."
    }
    (output / "source.json").write_text(json.dumps(source, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"source_kind": "synthetic", "frames": frames, "nodes": len(xy), "output": str(output)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frames", type=int, default=32)
    parser.add_argument("--grid", type=int, default=65)
    args = parser.parse_args()
    generate(args.output, args.frames, args.grid)
