"""Stream texture frames to a versioned, hashed UE interchange package."""
import hashlib
import json
from pathlib import Path
from typing import Any, Dict

import numpy as np
from PIL import Image

from .interpolation import SurfaceProjector, normalize
from .model import FIELDS, UNITS, read_config
from .readers import load_series


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def convert(input_path: Path, output_path: Path, config_path: Path, make_preview: bool = True) -> Dict[str, Any]:
    config = read_config(config_path)
    series = load_series(input_path, config["damage_monotonic_tolerance"])
    projector = SurfaceProjector.build(series.coordinates[:, :2], config["texture_resolution"],
                                       config["plate_origin_m"], config["plate_size_m"])
    if output_path.exists() and any(output_path.iterdir()):
        raise ValueError(f"Output directory is not empty: {output_path}. Choose a new run directory.")
    output_path.mkdir(parents=True, exist_ok=True)
    minimum = series.values.min(axis=(0, 1))
    maximum = series.values.max(axis=(0, 1))
    damage_maxima = []
    encoded_error = np.zeros(7)
    damage_png = output_path / "damage_png16"
    if config.get("write_damage_png16", True):
        damage_png.mkdir()
    state_path = output_path / "state.rgba16f"
    disp_path = output_path / "displacement.rgba16f"
    previous_damage = None
    previous_half_damage = None
    raster_min_increment = 0.0
    encoded_min_increment = 0.0
    with state_path.open("wb") as state_file, disp_path.open("wb") as displacement_file:
        for frame_index, nodal_fields in enumerate(series.values):
            field = projector.interpolate(nodal_fields)
            normalized = normalize(field, minimum, maximum)
            state = np.stack((field[:, :, 5], normalized[:, :, 3], normalized[:, :, 4], normalized[:, :, 6]), axis=-1)
            displacement = np.dstack((normalized[:, :, :3], projector.coverage.astype(float)))
            state[~projector.coverage] = 0.0
            displacement[~projector.coverage] = 0.0
            state_half = state.astype("<f2")
            displacement_half = displacement.astype("<f2")
            if previous_half_damage is not None:
                increment = float((state_half[:, :, 0].astype(float) - previous_half_damage).min())
                encoded_min_increment = min(encoded_min_increment, increment)
                if increment < -config["damage_monotonic_tolerance"]:
                    raise ValueError(f"Encoded damage decreases at frame {frame_index}: {increment}. Input numerical healing crosses a float16 quantization boundary; fix source output.")
            previous_half_damage = state_half[:, :, 0].astype(float)
            state_half.tofile(state_file)
            displacement_half.tofile(displacement_file)
            damage_maxima.append(float(state_half[:, :, 0].max()))
            if previous_damage is not None:
                raster_min_increment = min(raster_min_increment, float((state[:, :, 0] - previous_damage).min()))
            previous_damage = state[:, :, 0].copy()
            decoded = np.empty_like(field)
            decoded[:, :, :3] = displacement_half[:, :, :3].astype(float) * (maximum[:3] - minimum[:3]) + minimum[:3]
            for channel, physical in ((1, 3), (2, 4), (3, 6)):
                decoded[:, :, physical] = state_half[:, :, channel].astype(float) * (maximum[physical] - minimum[physical]) + minimum[physical]
            decoded[:, :, 5] = state_half[:, :, 0]
            encoded_error = np.maximum(encoded_error, np.abs(decoded[projector.coverage] - field[projector.coverage]).max(axis=0))
            if damage_png.exists():
                # Data PNG rows intentionally match binary upload rows (y-min first).
                Image.fromarray(np.rint(state[:, :, 0] * 65535).astype(np.uint16)).save(damage_png / f"damage_{frame_index:04d}.png")
    width, height = config["texture_resolution"]
    frame_count = len(series.times)
    expected_bytes = frame_count * width * height * 4 * 2
    if state_path.stat().st_size != expected_bytes or disp_path.stat().st_size != expected_bytes:
        raise ValueError("Internal error: binary texture size does not match [T,H,W,4].")
    physical_ranges = {name: {"minimum": float(minimum[i]), "maximum": float(maximum[i]), "unit": UNITS[i]}
                       for i, name in enumerate(FIELDS)}
    metadata = {
        "version": 1, "tool_version": "0.1.0", "source_kind": series.source["source_kind"],
        "source_provenance": series.source,
        "duration_seconds": float(series.times[-1] - series.times[0]), "frame_count": frame_count,
        "times_seconds": series.times.tolist(), "texture_resolution": [width, height],
        "plate_size_m": config["plate_size_m"], "plate_origin_m": config["plate_origin_m"],
        "source_units": "SI", "ue_units": "cm", "state_file": state_path.name,
        "displacement_file": disp_path.name,
        "displacement_min_m": minimum[:3].tolist(), "displacement_max_m": maximum[:3].tolist(),
        "stress1_range_Pa": [float(minimum[3]), float(maximum[3])],
        "von_mises_range_Pa": [float(minimum[4]), float(maximum[4])],
        "energy_range_J_m3": [float(minimum[6]), float(maximum[6])],
        "damage_range": [0.0, 1.0], "raw_physical_ranges": physical_ranges,
        "max_damage_per_frame": damage_maxima, "impact_uv": config["impact_uv"],
        "coordinate_mapping": "plate_local_xy_to_ue_local_xy_m_to_cm",
        "dtype": "float16", "byte_order": "little", "shape": [frame_count, height, width, 4],
        "storage_order": "C", "row_zero": "y_min", "uv_origin": "plate_origin_m",
        "texel_sampling": "centers", "normalization": "one affine range per field over all input nodes and all frames",
        "state_layout": ["damage", "sigma1_normalized", "von_mises_normalized", "energy_normalized"],
        "displacement_layout": ["u_normalized", "v_normalized", "w_normalized", "coverage"],
        "degenerate_range": "encode_zero_decode_minimum", "frame_bytes": width * height * 4 * 2,
        "hashes": {state_path.name: sha256(state_path), disp_path.name: sha256(disp_path)},
        "input_hashes": {p.name: sha256(p) for p in series.source_files + [series.source_files[0].parent / "source.json"]},
        "validation": {
            "node_count": len(series.node_ids), "strictly_increasing_time": True,
            "fixed_reference_coordinates": True, "damage_healing_repaired": False,
            "minimum_nodal_damage_increment": float(np.diff(series.values[:, :, 5], axis=0).min()),
            "minimum_raster_damage_increment": raster_min_increment,
            "minimum_encoded_damage_increment": encoded_min_increment,
            "damage_monotonic_tolerance": config["damage_monotonic_tolerance"],
            "coverage_fraction": float(projector.coverage.mean()), "outside_hull": "zero; never extrapolate",
            "max_half_encoding_error_SI": dict(zip(FIELDS, encoded_error.tolist())),
            "physics_validated": False,
            "physics_note": "Data checks are not fracture-model, contact, mesh, energy or experimental validation."
        },
        "preview": {"display_duration_seconds": config["preview_duration_seconds"], "vertical_flip_for_presentation_only": True,
                    "note": "Preview is slowed playback; binary timestamps remain physical SI seconds."}
    }
    (output_path / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if make_preview:
        from preview.render import render_preview
        render_preview(output_path)
    return metadata
