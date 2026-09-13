"""Strict CSV loading and optional meshio VTK loading."""
import csv
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import numpy as np

from .model import COLUMNS, FIELDS, SurfaceSeries


def read_source(directory: Path) -> Dict[str, Any]:
    path = directory / "source.json"
    if not path.is_file():
        raise ValueError(f"Missing source provenance: {path}. Synthetic data must be labeled.")
    source = json.loads(path.read_text(encoding="utf-8-sig"))
    if source.get("template_only") is True:
        raise ValueError("source.json is a template, not completed provenance. Fill it from an actual export and remove template_only only after verification.")
    if source.get("source_kind") not in ("synthetic", "comsol"):
        raise ValueError("source.json source_kind must be synthetic or comsol.")
    definitions = source.get("field_definitions")
    if not isinstance(definitions, dict) or not set(FIELDS).issubset(definitions):
        raise ValueError("source.json must define all seven exported physical fields.")
    if not source.get("coordinate_provenance"):
        raise ValueError("source.json needs coordinate_provenance identifying the reference surface.")
    if source.get("domain_topology") != "single_convex_plate_without_holes":
        raise ValueError("This CSV/VTK projection requires domain_topology=single_convex_plate_without_holes. Holes, cutouts and disconnected surfaces need topology-aware interpolation.")
    return source


def csv_rows(paths: List[Path]) -> Iterable[Tuple[float, int, List[float]]]:
    for path in paths:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(line for line in handle if not line.lstrip().startswith(("%", "#")))
            if reader.fieldnames is None or len(set(reader.fieldnames)) != len(reader.fieldnames):
                raise ValueError(f"{path}: missing or duplicated CSV header.")
            missing = set(COLUMNS) - set(reader.fieldnames)
            if missing:
                raise ValueError(f"{path}: missing required fields: {', '.join(sorted(missing))}")
            for row_number, row in enumerate(reader, 2):
                try:
                    if None in row or any(row[c] is None or row[c].strip() == "" for c in COLUMNS):
                        raise ValueError("empty field or extra column")
                    node_id = int(row["node_id"])
                    values = [float(row[c]) for c in COLUMNS if c != "node_id"]
                except (ValueError, TypeError) as exc:
                    raise ValueError(f"{path}:{row_number}: invalid numeric row ({exc}).") from exc
                if not np.isfinite(values).all():
                    raise ValueError(f"{path}:{row_number}: NaN or infinity is not permitted.")
                yield values[0], node_id, values[1:]


def vtk_rows(paths: List[Path]) -> Iterable[Tuple[float, int, List[float]]]:
    """One VTK per time, reference points + explicit point_data IDs/fields."""
    try:
        import meshio
    except ImportError as exc:
        raise ValueError("VTK requires the optional dependency: pip install '.[vtk]'.") from exc
    for path in paths:
        mesh = meshio.read(path)
        missing = set(FIELDS + ("node_id",)) - set(mesh.point_data)
        if missing or "time_s" not in mesh.field_data:
            raise ValueError(f"{path}: VTK needs point_data {FIELDS + ('node_id',)} and scalar field_data time_s.")
        time_values = np.asarray(mesh.field_data["time_s"]).ravel()
        if time_values.size != 1:
            raise ValueError(f"{path}: time_s must contain exactly one value.")
        arrays = [np.asarray(mesh.point_data[field]).reshape(-1) for field in FIELDS]
        ids = np.asarray(mesh.point_data["node_id"]).reshape(-1)
        if any(a.size != len(mesh.points) for a in arrays + [ids]):
            raise ValueError(f"{path}: every point field must be scalar and match point count.")
        for index, point in enumerate(mesh.points):
            node_id = ids[index]
            values = [*point, *(a[index] for a in arrays)]
            if not np.isfinite([time_values[0], node_id, *values]).all() or int(node_id) != node_id:
                raise ValueError(f"{path}: nonfinite value or invalid node ID.")
            yield float(time_values[0]), int(node_id), values


def load_series(input_path: Path, tolerance: float = 1e-8) -> SurfaceSeries:
    directory = input_path if input_path.is_dir() else input_path.parent
    source = read_source(directory)
    if input_path.is_file():
        files = [input_path]
    else:
        files = sorted(p for p in directory.iterdir() if p.suffix.lower() in (".csv", ".vtu", ".vtk"))
    if not files:
        raise ValueError(f"No CSV or VTK files found in {input_path}.")
    suffixes = {p.suffix.lower() for p in files}
    if ".csv" in suffixes and len(suffixes) > 1:
        raise ValueError("Do not mix CSV and VTK exports in one input directory.")
    rows = csv_rows(files) if suffixes == {".csv"} else vtk_rows(files)
    times: List[float] = []
    frames: List[np.ndarray] = []
    reference_ids = None
    reference_coordinates = None
    current_time = None
    current_rows: Dict[int, List[float]] = {}

    def finish_frame() -> None:
        nonlocal reference_ids, reference_coordinates
        ids = np.array(sorted(current_rows), dtype=np.int64)
        if len(ids) < 3:
            raise ValueError("Every frame needs at least three unique surface nodes.")
        matrix = np.array([current_rows[int(i)] for i in ids], dtype=float)
        coordinates = matrix[:, :3]
        if reference_ids is None:
            reference_ids, reference_coordinates = ids, coordinates
            if len(np.unique(coordinates[:, :2], axis=0)) != len(ids):
                raise ValueError("Duplicate XY coordinates: export one selected surface, not multiple thickness layers.")
            if not np.allclose(coordinates[:, 2], 0.0, atol=1e-10, rtol=0):
                raise ValueError("Reference mapping surface must have z_m=0; transform the selected surface first.")
        elif not np.array_equal(ids, reference_ids):
            raise ValueError(f"Node IDs/count changed at time {current_time}.")
        elif not np.allclose(coordinates, reference_coordinates, atol=1e-12, rtol=0):
            raise ValueError(f"Reference coordinates moved at time {current_time}; export X,Y,Z, not deformed x,y,z.")
        times.append(float(current_time))
        frames.append(matrix[:, 3:])

    for time, node_id, values in rows:
        if current_time is None:
            current_time = time
        elif time != current_time:
            if time <= current_time:
                raise ValueError("Time groups must be strictly increasing; repeated/out-of-order time group detected.")
            finish_frame()
            current_rows = {}
            current_time = time
        if node_id in current_rows:
            raise ValueError(f"Duplicate node_id {node_id} at time {time} (or duplicated time frame).")
        current_rows[node_id] = values
    if not current_rows:
        raise ValueError("No input data rows.")
    finish_frame()
    if len(times) < 2 or times[0] != 0.0:
        raise ValueError("At least two frames are required and the physics timeline must start exactly at 0 seconds.")
    values = np.stack(frames)
    damage = values[:, :, 5]
    if (damage < 0).any() or (damage > 1).any():
        raise ValueError("Damage must lie in [0,1]; conversion does not clip invalid physics.")
    minimum_increment = float(np.min(np.diff(damage, axis=0)))
    if minimum_increment < -tolerance:
        raise ValueError(f"Damage healing detected: minimum nodal increment {minimum_increment:.6g}. Fix the source model; no cumulative-max repair is applied.")
    if (values[:, :, 4] < -1e-8).any() or (values[:, :, 6] < -1e-8).any():
        raise ValueError("von Mises stress and strain energy density must be nonnegative.")
    return SurfaceSeries(np.array(times), reference_ids, reference_coordinates, values, source, files)
