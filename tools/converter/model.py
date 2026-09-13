"""Shared strict input schema and configuration."""
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

FIELDS = ("u_m", "v_m", "w_m", "sigma1_Pa", "von_mises_Pa", "damage", "strain_energy_J_m3")
COLUMNS = ("time_s", "node_id", "x_m", "y_m", "z_m") + FIELDS
UNITS = ("m", "m", "m", "Pa", "Pa", "1", "J/m^3")


@dataclass
class SurfaceSeries:
    times: np.ndarray
    node_ids: np.ndarray
    coordinates: np.ndarray
    values: np.ndarray
    source: Dict[str, Any]
    source_files: List[Path]


def read_config(path: Path) -> Dict[str, Any]:
    """The shipped config uses the JSON subset of YAML; full YAML is optional."""
    raw = path.read_text(encoding="utf-8-sig")
    try:
        config = json.loads(raw)
    except json.JSONDecodeError:
        try:
            import yaml
        except ImportError as exc:
            raise ValueError("This YAML requires PyYAML; install it or use JSON-compatible YAML.") from exc
        config = yaml.safe_load(raw)
    if not isinstance(config, dict):
        raise ValueError("Configuration must be an object.")
    resolution = config.get("texture_resolution", [512, 512])
    if len(resolution) != 2 or any(type(v) is not int or v < 2 or v > 4096 for v in resolution):
        raise ValueError("texture_resolution must contain two integers in [2, 4096].")
    size = np.asarray(config.get("plate_size_m", [1, 1]), dtype=float)
    origin = np.asarray(config.get("plate_origin_m", [-0.5, -0.5]), dtype=float)
    impact = np.asarray(config.get("impact_uv", [0.5, 0.5]), dtype=float)
    if size.shape != (2,) or not np.isfinite(size).all() or (size <= 0).any():
        raise ValueError("plate_size_m must be two positive finite dimensions.")
    if origin.shape != (2,) or not np.isfinite(origin).all():
        raise ValueError("plate_origin_m must be two finite coordinates.")
    if impact.shape != (2,) or not np.isfinite(impact).all() or (impact < 0).any() or (impact > 1).any():
        raise ValueError("impact_uv must be two finite values in [0, 1].")
    tolerance = float(config.get("damage_monotonic_tolerance", 1e-8))
    preview_duration = float(config.get("preview_duration_seconds", 3.2))
    if not np.isfinite(tolerance) or not 0 <= tolerance <= 1e-6:
        raise ValueError("damage_monotonic_tolerance must be finite in [0, 1e-6].")
    if not np.isfinite(preview_duration) or preview_duration <= 0:
        raise ValueError("preview_duration_seconds must be finite and positive.")
    config.update(texture_resolution=resolution, plate_size_m=size.tolist(),
                  plate_origin_m=origin.tolist(), impact_uv=impact.tolist(),
                  damage_monotonic_tolerance=tolerance, preview_duration_seconds=preview_duration)
    return config
