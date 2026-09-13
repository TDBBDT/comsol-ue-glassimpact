"""Reusable piecewise-linear barycentric interpolation on fixed reference XY."""
from dataclasses import dataclass
from typing import Sequence, Tuple

import matplotlib.tri as mtri
import numpy as np


@dataclass
class SurfaceProjector:
    shape: Tuple[int, int]
    indices: np.ndarray
    weights: np.ndarray
    coverage: np.ndarray

    @classmethod
    def build(cls, xy: np.ndarray, resolution: Sequence[int], origin: Sequence[float], size: Sequence[float]) -> "SurfaceProjector":
        width, height = resolution
        x = origin[0] + (np.arange(width) + 0.5) * size[0] / width
        y = origin[1] + (np.arange(height) + 0.5) * size[1] / height
        xx, yy = np.meshgrid(x, y)
        try:
            tri = mtri.Triangulation(xy[:, 0], xy[:, 1])
            triangle_ids = tri.get_trifinder()(xx.ravel(), yy.ravel())
        except (RuntimeError, ValueError) as exc:
            raise ValueError(f"Cannot triangulate selected surface: {exc}") from exc
        coverage = triangle_ids >= 0
        if not coverage.any():
            raise ValueError("The FEM surface does not cover any output texel centers.")
        indices = tri.triangles[np.maximum(triangle_ids, 0)]
        points = xy[indices]
        a, b, c = points[:, 0], points[:, 1], points[:, 2]
        query = np.column_stack((xx.ravel(), yy.ravel()))
        denominator = (b[:, 1] - c[:, 1]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (a[:, 1] - c[:, 1])
        w0 = ((b[:, 1] - c[:, 1]) * (query[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (query[:, 1] - c[:, 1])) / denominator
        w1 = ((c[:, 1] - a[:, 1]) * (query[:, 0] - c[:, 0]) + (a[:, 0] - c[:, 0]) * (query[:, 1] - c[:, 1])) / denominator
        weights = np.column_stack((w0, w1, 1.0 - w0 - w1))
        if (weights[coverage] < -1e-10).any():
            raise ValueError("Invalid negative barycentric weights in interpolation domain.")
        # Only roundoff in barycentric arithmetic is clipped; input damage is never repaired.
        weights = np.maximum(weights, 0)
        weights /= weights.sum(axis=1, keepdims=True)
        weights[~coverage] = 0
        return cls((height, width), indices, weights, coverage.reshape(height, width))

    def interpolate(self, nodal_values: np.ndarray) -> np.ndarray:
        result = np.einsum("pk,pkc->pc", self.weights, nodal_values[self.indices])
        return result.reshape(*self.shape, nodal_values.shape[-1])


def normalize(values: np.ndarray, minimum: np.ndarray, maximum: np.ndarray) -> np.ndarray:
    """Global affine ranges; constant channels encode zero and decode minimum."""
    span = maximum - minimum
    return np.divide(values - minimum, span, out=np.zeros_like(values), where=span != 0)
