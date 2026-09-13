"""Verify on-disk binary shape, hashes and decoded playback invariants."""
import json
from pathlib import Path
from typing import Any, Dict

import numpy as np

from converter.pipeline import sha256


def validate_processed(directory: Path) -> Dict[str, Any]:
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    if metadata.get("version") != 1 or metadata.get("dtype") != "float16" or metadata.get("byte_order") != "little":
        raise ValueError("Unsupported processed version/dtype/endianness.")
    count = metadata["frame_count"]
    width, height = metadata["texture_resolution"]
    shape = (count, height, width, 4)
    if list(shape) != metadata["shape"]:
        raise ValueError("Metadata shape does not agree with frame_count/resolution.")
    times = np.asarray(metadata["times_seconds"], dtype=float)
    if len(times) != count or not np.isfinite(times).all() or times[0] != 0 or not (np.diff(times) > 0).all():
        raise ValueError("Invalid processed physics timeline.")
    if not np.isclose(times[-1], metadata["duration_seconds"], atol=1e-12, rtol=0):
        raise ValueError("duration_seconds disagrees with final timestamp.")
    arrays = []
    try:
        for field in ("state_file", "displacement_file"):
            filename = metadata[field]
            if Path(filename).name != filename:
                raise ValueError("Texture files must be basenames within the package.")
            path = directory / filename
            if path.stat().st_size != int(np.prod(shape)) * 2:
                raise ValueError(f"Invalid byte size: {filename}.")
            if sha256(path) != metadata["hashes"][filename]:
                raise ValueError(f"SHA256 mismatch: {filename}.")
            arrays.append(np.memmap(path, mode="r", dtype="<f2", shape=shape))
        state, displacement = arrays
        previous = None
        coverage = None
        maxima = []
        for index in range(count):
            frame = np.asarray(state[index], dtype=float)
            disp = np.asarray(displacement[index], dtype=float)
            if not np.isfinite(frame).all() or not np.isfinite(disp).all():
                raise ValueError("Nonfinite encoded field.")
            if (frame < 0).any() or (frame > 1).any() or (disp < 0).any() or (disp > 1).any():
                raise ValueError("Encoded normalized channels must be in [0,1].")
            current_coverage = disp[:, :, 3]
            if not np.isin(current_coverage, [0, 1]).all():
                raise ValueError("Coverage must contain binary 0 or 1 values.")
            if coverage is not None and not np.array_equal(current_coverage, coverage):
                raise ValueError("Coverage changed across frames.")
            coverage = current_coverage.copy()
            outside = coverage == 0
            if (frame[outside] != 0).any() or (disp[outside] != 0).any():
                raise ValueError("Fields outside the interpolation hull must be encoded zero.")
            damage = frame[:, :, 0]
            if previous is not None and (damage < previous - 1e-8).any():
                raise ValueError("Encoded damage healing detected.")
            previous = damage.copy()
            maxima.append(float(damage.max()))
        if not np.array_equal(maxima, metadata["max_damage_per_frame"]):
            raise ValueError("max_damage_per_frame disagrees with encoded damage.")
        return {"valid": True, "source_kind": metadata["source_kind"], "frames": count,
                "resolution": [width, height], "binary_bytes": int(np.prod(shape)) * 4,
                "hashes_verified": True, "encoded_damage_monotonic": True, "physics_validated": False}
    finally:
        # Release Windows file mappings so callers can rename/delete a checked package.
        for array in arrays:
            array._mmap.close()
