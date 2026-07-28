from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure


TRAFFIC_FIELDS = [
    "date",
    "views",
    "unique_views",
    "clones",
    "unique_clones",
]

CHART_DEFINITIONS = {
    "views": {
        "title": "Views",
        "filename": "views.svg",
    },
    "unique_views": {
        "title": "Daily unique views",
        "filename": "unique-views.svg",
    },
    "clones": {
        "title": "Clones",
        "filename": "clones.svg",
    },
    "unique_clones": {
        "title": "Daily unique clones",
        "filename": "unique-clones.svg",
    },
}


class RenderError(RuntimeError):
    """Raised when stored traffic cannot be rendered."""


@dataclass(frozen=True)
class TrafficRow:
    """One day of stored repository traffic."""

    day: date
    views: int
    unique_views: int
    clones: int
    unique_clones: int


def _read_non_negative_integer(
    value: str,
    field: str,
    traffic_file: Path,
) -> int:
    """Parse and validate a CSV integer."""

    try:
        number = int(value)
    except ValueError as exc:
        raise RenderError(
            f"Invalid {field} value in {traffic_file}: "
            f"{value!r}"
        ) from exc

    if number < 0:
        raise RenderError(
            f"Negative {field} value in {traffic_file}: "
            f"{number}"
        )

    return number


def read_traffic_rows(
    traffic_file: Path,
) -> list[TrafficRow]:
    """Read one repository's traffic.csv."""

    if not traffic_file.exists():
        raise RenderError(
            f"Traffic file not found: {traffic_file}"
        )

    rows: list[TrafficRow] = []

    with traffic_file.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        reader = csv.DictReader(handle)

        if reader.fieldnames != TRAFFIC_FIELDS:
            raise RenderError(
                f"Unexpected columns in {traffic_file}"
            )

        for item in reader:
            raw_date = item["date"].strip()

            try:
                parsed_date = datetime.strptime(
                    raw_date,
                    "%Y-%m-%d",
                ).date()
            except ValueError as exc:
                raise RenderError(
                    f"Invalid date in {traffic_file}: "
                    f"{raw_date!r}"
                ) from exc

            rows.append(
                TrafficRow(
                    day=parsed_date,
                    views=_read_non_negative_integer(
                        item["views"],
                        "views",
                        traffic_file,
                    ),
                    unique_views=_read_non_negative_integer(
                        item["unique_views"],
                        "unique_views",
                        traffic_file,
                    ),
                    clones=_read_non_negative_integer(
                        item["clones"],
                        "clones",
                        traffic_file,
                    ),
                    unique_clones=_read_non_negative_integer(
                        item["unique_clones"],
                        "unique_clones",
                        traffic_file,
                    ),
                )
            )

    rows.sort(
        key=lambda row: row.day
    )

    return rows


def moving_average(
    values: Iterable[int],
    window: int = 7,
) -> list[float]:
    """Return a trailing moving average."""

    numbers = list(values)
    averages: list[float] = []

    for index in range(len(numbers)):
        start = max(
            0,
            index - window + 1,
        )

        current_window = numbers[
            start:index + 1
        ]

        averages.append(
            sum(current_window)
            / len(current_window)
        )

    return averages


def _configure_axes(
    figure: Figure,
    axes: Axes,
) -> None:
    """Apply the private dashboard's dark appearance."""

    background = "#0d1117"
    panel = "#161b22"
    foreground = "#c9d1d9"
    muted = "#8b949e"
    grid = "#30363d"

    figure.patch.set_facecolor(
        background
    )

    axes.set_facecolor(
        panel
    )

    axes.tick_params(
        axis="both",
        colors=muted,
        labelsize=9,
    )

    axes.xaxis.label.set_color(
        foreground
    )

    axes.yaxis.label.set_color(
        foreground
    )

    axes.title.set_color(
        foreground
    )

    for spine in axes.spines.values():
        spine.set_color(grid)

    axes.grid(
        axis="y",
        alpha=0.35,
        linewidth=0.8,
        color=grid,
    )

    axes.set_axisbelow(True)


def _configure_date_axis(
    axes: Axes,
    dates: list[date],
) -> None:
    """Choose readable date labels for any history length."""

    history_length = len(dates)

    if history_length <= 31:
        locator = mdates.DayLocator(
            interval=max(
                1,
                history_length // 8,
            )
        )

        formatter = mdates.DateFormatter(
            "%d %b"
        )
    elif history_length <= 180:
        locator = mdates.WeekdayLocator(
            interval=max(
                1,
                history_length // 60,
            )
        )

        formatter = mdates.DateFormatter(
            "%d %b"
        )
    elif history_length <= 730:
        locator = mdates.MonthLocator()

        formatter = mdates.DateFormatter(
            "%b %Y"
        )
    else:
        locator = mdates.MonthLocator(
            interval=3
        )

        formatter = mdates.DateFormatter(
            "%b %Y"
        )

    axes.xaxis.set_major_locator(
        locator
    )

    axes.xaxis.set_major_formatter(
        formatter
    )

    axes.tick_params(
        axis="x",
        rotation=35,
    )


def render_metric_chart(
    repository_name: str,
    rows: list[TrafficRow],
    metric: str,
    output_file: Path,
) -> None:
    """Render one traffic metric as an SVG chart."""

    if metric not in CHART_DEFINITIONS:
        raise ValueError(
            f"Unsupported metric: {metric}"
        )

    if not rows:
        raise RenderError(
            f"No traffic rows exist for {repository_name}."
        )

    dates = [
        row.day
        for row in rows
    ]

    values = [
        int(getattr(row, metric))
        for row in rows
    ]

    averages = moving_average(
        values,
        window=7,
    )

    definition = CHART_DEFINITIONS[
        metric
    ]

    total = sum(values)

    matplotlib.rcParams[
        "svg.hashsalt"
    ] = "github-traffic-archive"

    figure, axes = plt.subplots(
        figsize=(12, 4.2),
        dpi=100,
    )

    _configure_axes(
        figure,
        axes,
    )

    axes.bar(
        dates,
        values,
        width=0.8,
        color="#2f81f7",
        alpha=0.72,
        label="Daily",
    )

    axes.plot(
        dates,
        averages,
        color="#f0883e",
        linewidth=2.2,
        label="7-day average",
    )

    axes.set_title(
        (
            f"{repository_name} — "
            f"{definition['title']} "
            f"— total {total:,}"
        ),
        loc="left",
        fontsize=14,
        fontweight="bold",
        color="#c9d1d9",
        pad=14,
    )

    axes.set_ylabel(
        "Count"
    )

    axes.set_ylim(
        bottom=0
    )

    _configure_date_axis(
        axes,
        dates,
    )

    legend = axes.legend(
        frameon=False,
        loc="upper left",
        ncols=2,
    )

    for text in legend.get_texts():
        text.set_color(
            "#c9d1d9"
        )

    figure.tight_layout(
        pad=1.4
    )

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    figure.savefig(
        output_file,
        format="svg",
        facecolor=figure.get_facecolor(),
        bbox_inches="tight",
        metadata={
            "Date": None,
            "Creator": "github-traffic-archive",
        },
    )

    plt.close(
        figure
    )


def render_repository_charts(
    repository_directory: Path,
    repository_name: str,
) -> list[Path]:
    """Generate all four charts for one repository."""

    traffic_file = (
        repository_directory
        / "traffic.csv"
    )

    rows = read_traffic_rows(
        traffic_file
    )

    generated_files: list[Path] = []

    for metric, definition in (
        CHART_DEFINITIONS.items()
    ):
        output_file = (
            repository_directory
            / "charts"
            / definition["filename"]
        )

        render_metric_chart(
            repository_name,
            rows,
            metric,
            output_file,
        )

        generated_files.append(
            output_file
        )

    return generated_files
