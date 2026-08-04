from __future__ import annotations

from typing import Any

from game_pulse.contracts import CalibrationBin, GameDetail


def timeline_chart(game: GameDetail) -> dict[str, Any]:
    width, height = 1120, 430
    left, right, top, bottom = 58, 24, 28, 48
    plot_width = width - left - right
    plot_height = height - top - bottom
    maximum_elapsed = max(point.elapsed_seconds for point in game.timeline) or 1

    def x_position(elapsed: int) -> float:
        return left + plot_width * elapsed / maximum_elapsed

    def y_position(probability: float) -> float:
        return top + plot_height * (1 - probability)

    coordinates = [
        (x_position(point.elapsed_seconds), y_position(point.win_probability))
        for point in game.timeline
    ]
    path = " ".join(
        f"{'M' if index == 0 else 'L'} {x:.2f} {y:.2f}"
        for index, (x, y) in enumerate(coordinates)
    )
    point_by_possession = {
        point.possession_number: (point, coordinates[index])
        for index, point in enumerate(game.timeline)
    }
    markers = []
    for turning_point in game.turning_points:
        point, (x, y) = point_by_possession[turning_point.possession_number]
        markers.append(
            {
                "rank": turning_point.rank,
                "x": round(x, 2),
                "y": round(y, 2),
                "label": (
                    f"#{turning_point.rank} {point.period_label} {point.clock}: "
                    f"{turning_point.win_probability_added:+.1%}"
                ),
            }
        )
    boundaries = []
    for period_end in (600, 1200, 1800, 2400):
        if period_end < maximum_elapsed:
            boundaries.append(
                {
                    "x": round(x_position(period_end), 2),
                    "label": f"Q{period_end // 600 + 1}",
                }
            )
    y_ticks = [
        {
            "value": value,
            "y": round(y_position(value), 2),
            "label": f"{value:.0%}",
        }
        for value in (0.0, 0.25, 0.5, 0.75, 1.0)
    ]
    return {
        "width": width,
        "height": height,
        "left": left,
        "right": right,
        "top": top,
        "bottom": bottom,
        "plot_width": plot_width,
        "plot_height": plot_height,
        "path": path,
        "boundaries": boundaries,
        "markers": markers,
        "y_ticks": y_ticks,
        "opening_x": round(coordinates[0][0], 2),
        "opening_y": round(coordinates[0][1], 2),
        "final_x": round(coordinates[-1][0], 2),
        "final_y": round(coordinates[-1][1], 2),
    }


def calibration_chart(bins: list[CalibrationBin]) -> dict[str, Any]:
    width, height = 520, 330
    left, right, top, bottom = 48, 22, 22, 42
    plot_width = width - left - right
    plot_height = height - top - bottom

    def x_position(value: float) -> float:
        return left + plot_width * value

    def y_position(value: float) -> float:
        return top + plot_height * (1 - value)

    points = [
        {
            "x": round(x_position(item.mean_prediction), 2),
            "y": round(y_position(item.observed_win_rate), 2),
            "prediction": item.mean_prediction,
            "observed": item.observed_win_rate,
            "observations": item.observations,
        }
        for item in bins
    ]
    path = " ".join(
        f"{'M' if index == 0 else 'L'} {point['x']} {point['y']}"
        for index, point in enumerate(points)
    )
    return {
        "width": width,
        "height": height,
        "left": left,
        "top": top,
        "plot_width": plot_width,
        "plot_height": plot_height,
        "path": path,
        "points": points,
        "ticks": [0.0, 0.5, 1.0],
    }
