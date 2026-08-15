"""Server-side SVG geometry for the portal's curve.

The portal renders its chart as plain SVG in the template rather than shipping a
charting library: one series, no interaction beyond a tooltip, and a strict CSP
that forbids third-party script anyway. Computing the path here keeps the
template free of arithmetic.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

W = 760.0
H = 240.0
PAD_L, PAD_R, PAD_T, PAD_B = 46.0, 20.0, 16.0, 26.0
PLOT_W = W - PAD_L - PAD_R
PLOT_H = H - PAD_T - PAD_B


@dataclass
class Curve:
    line: str
    area: str
    ticks: list[tuple[float, float]]
    """(y position, value) for each horizontal gridline."""
    x_labels: list[tuple[float, str]]
    baseline_y: float
    end: tuple[float, float]
    width: float = W
    height: float = H
    empty: bool = False


def _nice_step(span: float) -> float:
    if span <= 0:
        return 1.0
    target = span / 4.0
    magnitude = 10.0 ** int(f"{target:e}".split("e")[1])
    for factor in (1, 2, 2.5, 5, 10):
        if factor * magnitude >= target:
            return factor * magnitude
    return magnitude * 10


def build_curve(points: Sequence[dict[str, Any]], baseline: float = 0.0) -> Curve:
    if not points:
        return Curve("", "", [], [], PAD_T + PLOT_H, (0.0, 0.0), empty=True)

    values = [float(p["v"]) for p in points]
    raw_min = min(values + [baseline])
    raw_max = max(values + [baseline])
    step = _nice_step(raw_max - raw_min)

    y_min = (raw_min // step) * step
    y_max = -((-raw_max) // step) * step
    if y_max == y_min:
        y_max = y_min + step

    def x_at(i: int) -> float:
        if len(points) == 1:
            return PAD_L + PLOT_W / 2
        return PAD_L + (i / (len(points) - 1)) * PLOT_W

    def y_at(v: float) -> float:
        return PAD_T + PLOT_H - ((v - y_min) / (y_max - y_min)) * PLOT_H

    line = " ".join(
        f"{'M' if i == 0 else 'L'}{x_at(i):.2f},{y_at(v):.2f}"
        for i, v in enumerate(values)
    )
    area = (
        f"{line} L{x_at(len(values) - 1):.2f},{y_at(y_min):.2f} "
        f"L{x_at(0):.2f},{y_at(y_min):.2f} Z"
    )

    ticks: list[tuple[float, float]] = []
    value = y_min
    while value <= y_max + step / 2:
        ticks.append((y_at(value), round(value, 4)))
        value += step

    # Label roughly every sixth point, and always the last one. The final
    # label is forced, so a stepped label sitting right next to it has to give
    # way or the two render on top of each other.
    every = max(1, -(-len(points) // 6))
    min_gap = 64.0
    last_x = x_at(len(points) - 1)
    x_labels = [
        (x_at(i), str(p["t"]))
        for i, p in enumerate(points)
        if i % every == 0 and last_x - x_at(i) >= min_gap
    ]
    x_labels.append((last_x, str(points[-1]["t"])))

    return Curve(
        line=line,
        area=area,
        ticks=ticks,
        x_labels=x_labels,
        baseline_y=y_at(baseline),
        end=(x_at(len(values) - 1), y_at(values[-1])),
    )
