from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .render import (
    RenderError,
    TrafficRow,
    read_traffic_rows,
    render_metric_chart,
)


DATA_ROOT = Path("data/repos")
ROOT_CHART_DIRECTORY = Path("charts")
ROOT_README = Path("README.md")

ROOT_CHARTS = {
    "views": "total-views.svg",
    "unique_views": "total-unique-views.svg",
    "clones": "total-clones.svg",
    "unique_clones": "total-unique-clones.svg",
}


class AggregateError(RuntimeError):
    """Raised when the combined dashboard cannot be generated."""


def _escape_table_text(value: Any) -> str:
    """Escape text for a Markdown table."""

    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("\r", " ")
        .replace("\n", " ")
        .strip()
    )


def _metric_total(
    rows: list[TrafficRow],
    metric: str,
) -> int:
    """Sum one metric from traffic rows."""

    return sum(
        int(getattr(row, metric))
        for row in rows
    )


def _discover_repository_directories(
    data_root: Path,
) -> list[Path]:
    """Find repository folders containing traffic.csv."""

    if not data_root.exists():
        return []

    directories = [
        directory
        for directory in data_root.iterdir()
        if (
            directory.is_dir()
            and (
                directory
                / "traffic.csv"
            ).exists()
        )
    ]

    return sorted(
        directories,
        key=lambda directory: (
            directory.name.casefold()
        ),
    )


def _aggregate_daily_rows(
    repository_rows: dict[str, list[TrafficRow]],
) -> list[TrafficRow]:
    """Combine daily metrics across all repositories."""

    totals_by_date: dict[
        date,
        dict[str, int],
    ] = {}

    for rows in repository_rows.values():
        for row in rows:
            totals = totals_by_date.setdefault(
                row.day,
                {
                    "views": 0,
                    "unique_views": 0,
                    "clones": 0,
                    "unique_clones": 0,
                },
            )

            totals["views"] += row.views
            totals["unique_views"] += (
                row.unique_views
            )
            totals["clones"] += row.clones
            totals["unique_clones"] += (
                row.unique_clones
            )

    combined_rows: list[TrafficRow] = []

    for day in sorted(totals_by_date):
        totals = totals_by_date[day]

        combined_rows.append(
            TrafficRow(
                day=day,
                views=totals["views"],
                unique_views=(
                    totals["unique_views"]
                ),
                clones=totals["clones"],
                unique_clones=(
                    totals["unique_clones"]
                ),
            )
        )

    return combined_rows


def _read_latest_snapshot_items(
    snapshot_directory: Path,
) -> list[dict[str, Any]]:
    """Read the most recent snapshot in a folder."""

    if not snapshot_directory.exists():
        return []

    files = sorted(
        snapshot_directory.glob("*.json")
    )

    if not files:
        return []

    snapshot_file = files[-1]

    try:
        payload = json.loads(
            snapshot_file.read_text(
                encoding="utf-8",
            )
        )
    except (
        OSError,
        json.JSONDecodeError,
    ) as exc:
        raise AggregateError(
            f"Cannot read {snapshot_file}."
        ) from exc

    if not isinstance(payload, dict):
        raise AggregateError(
            f"{snapshot_file} is not a JSON object."
        )

    items = payload.get("items")

    if not isinstance(items, list):
        raise AggregateError(
            f"{snapshot_file} has no valid items list."
        )

    validated_items: list[dict[str, Any]] = []

    for item in items:
        if not isinstance(item, dict):
            raise AggregateError(
                f"{snapshot_file} contains "
                "an invalid snapshot item."
            )

        validated_items.append(item)

    return validated_items


def _combined_referrers(
    repository_directories: list[Path],
) -> list[dict[str, Any]]:
    """Combine the latest referrer snapshots."""

    totals: dict[
        str,
        dict[str, int],
    ] = defaultdict(
        lambda: {
            "count": 0,
            "uniques": 0,
        }
    )

    for directory in repository_directories:
        items = _read_latest_snapshot_items(
            directory
            / "referrers"
        )

        for item in items:
            referrer = str(
                item.get("referrer", "")
            ).strip()

            if not referrer:
                continue

            totals[referrer]["count"] += int(
                item.get("count", 0)
            )

            totals[referrer]["uniques"] += int(
                item.get("uniques", 0)
            )

    combined = [
        {
            "referrer": referrer,
            "count": values["count"],
            "uniques": values["uniques"],
        }
        for referrer, values in totals.items()
    ]

    combined.sort(
        key=lambda item: (
            -item["count"],
            item["referrer"].casefold(),
        )
    )

    return combined[:20]


def _combined_popular_paths(
    repository_directories: list[Path],
) -> list[dict[str, Any]]:
    """Collect the most-viewed paths across repositories."""

    paths: list[dict[str, Any]] = []

    for directory in repository_directories:
        items = _read_latest_snapshot_items(
            directory
            / "paths"
        )

        for item in items:
            path = str(
                item.get("path", "")
            ).strip()

            if not path:
                continue

            paths.append(
                {
                    "repository": directory.name,
                    "path": path,
                    "title": str(
                        item.get("title", "")
                    ).strip(),
                    "count": int(
                        item.get("count", 0)
                    ),
                    "uniques": int(
                        item.get("uniques", 0)
                    ),
                }
            )

    paths.sort(
        key=lambda item: (
            -item["count"],
            item["repository"].casefold(),
            item["path"].casefold(),
        )
    )

    return paths[:20]


def _render_summary_table(
    combined_rows: list[TrafficRow],
) -> list[str]:
    """Render global metric totals."""

    recent_rows = combined_rows[-14:]

    metrics = [
        (
            "Views",
            "views",
        ),
        (
            "Sum of daily unique-view counts",
            "unique_views",
        ),
        (
            "Clones",
            "clones",
        ),
        (
            "Sum of daily unique-clone counts",
            "unique_clones",
        ),
    ]

    lines = [
        "| Metric | Since tracking began | Latest 14 stored dates |",
        "|---|---:|---:|",
    ]

    for label, metric in metrics:
        all_time = _metric_total(
            combined_rows,
            metric,
        )

        recent = _metric_total(
            recent_rows,
            metric,
        )

        lines.append(
            f"| {label} "
            f"| {all_time:,} "
            f"| {recent:,} |"
        )

    return lines


def _render_repository_ranking(
    repository_rows: dict[str, list[TrafficRow]],
) -> list[str]:
    """Render a per-repository ranking table."""

    ranking = []

    for repository_name, rows in (
        repository_rows.items()
    ):
        ranking.append(
            {
                "name": repository_name,
                "views": _metric_total(
                    rows,
                    "views",
                ),
                "unique_views": _metric_total(
                    rows,
                    "unique_views",
                ),
                "clones": _metric_total(
                    rows,
                    "clones",
                ),
                "unique_clones": _metric_total(
                    rows,
                    "unique_clones",
                ),
                "first_date": rows[0].day.isoformat(),
                "last_date": rows[-1].day.isoformat(),
            }
        )

    ranking.sort(
        key=lambda item: (
            -item["views"],
            item["name"].casefold(),
        )
    )

    lines = [
        "| Repository | Views | Daily unique-view counts | Clones | Daily unique-clone counts | Stored period |",
        "|---|---:|---:|---:|---:|---|",
    ]

    for item in ranking:
        name = item["name"]

        lines.append(
            f"| [{_escape_table_text(name)}]"
            f"(data/repos/{name}/README.md) "
            f"| {item['views']:,} "
            f"| {item['unique_views']:,} "
            f"| {item['clones']:,} "
            f"| {item['unique_clones']:,} "
            f"| `{item['first_date']}` "
            f"to `{item['last_date']}` |"
        )

    return lines


def _render_referrer_table(
    items: list[dict[str, Any]],
) -> list[str]:
    """Render combined referring sites."""

    if not items:
        return [
            "_No referring sites were reported._"
        ]

    lines = [
        "| Referring site | Views | Summed unique counts |",
        "|---|---:|---:|",
    ]

    for item in items:
        lines.append(
            f"| {_escape_table_text(item['referrer'])} "
            f"| {item['count']:,} "
            f"| {item['uniques']:,} |"
        )

    return lines


def _render_path_table(
    items: list[dict[str, Any]],
) -> list[str]:
    """Render the globally highest-traffic paths."""

    if not items:
        return [
            "_No popular paths were reported._"
        ]

    lines = [
        "| Repository | Path | Page title | Views | Unique visitors |",
        "|---|---|---|---:|---:|",
    ]

    for item in items:
        repository = item["repository"]

        lines.append(
            f"| [{_escape_table_text(repository)}]"
            f"(data/repos/{repository}/README.md) "
            f"| `{_escape_table_text(item['path'])}` "
            f"| {_escape_table_text(item['title'])} "
            f"| {item['count']:,} "
            f"| {item['uniques']:,} |"
        )

    return lines


def _render_combined_charts(
    combined_rows: list[TrafficRow],
    chart_directory: Path,
) -> None:
    """Generate the four global SVG charts."""

    for metric, filename in ROOT_CHARTS.items():
        render_metric_chart(
            "All repositories",
            combined_rows,
            metric,
            chart_directory / filename,
        )


def render_global_dashboard(
    *,
    collected_at: datetime,
    data_root: Path = DATA_ROOT,
    chart_directory: Path = ROOT_CHART_DIRECTORY,
    readme_file: Path = ROOT_README,
) -> bool:
    """Generate combined charts and the root README.

    Returns True only when README.md changed.
    """

    if collected_at.tzinfo is None:
        raise ValueError(
            "collected_at must include "
            "timezone information."
        )

    repository_directories = (
        _discover_repository_directories(
            data_root
        )
    )

    if not repository_directories:
        raise AggregateError(
            "No stored repository traffic "
            "was found."
        )

    repository_rows: dict[
        str,
        list[TrafficRow],
    ] = {}

    for directory in repository_directories:
        rows = read_traffic_rows(
            directory
            / "traffic.csv"
        )

        if rows:
            repository_rows[
                directory.name
            ] = rows

    if not repository_rows:
        raise AggregateError(
            "Stored traffic files contain no rows."
        )

    combined_rows = _aggregate_daily_rows(
        repository_rows
    )

    try:
        _render_combined_charts(
            combined_rows,
            chart_directory,
        )
    except RenderError as exc:
        raise AggregateError(
            "Cannot generate combined charts."
        ) from exc

    referrers = _combined_referrers(
        repository_directories
    )

    popular_paths = _combined_popular_paths(
        repository_directories
    )

    first_date = (
        combined_rows[0]
        .day
        .isoformat()
    )

    last_date = (
        combined_rows[-1]
        .day
        .isoformat()
    )

    generated_date = (
        collected_at
        .astimezone(timezone.utc)
        .date()
        .isoformat()
    )

    lines = [
        "# GitHub Traffic Archive",
        "",
        "Private long-term analytics for all public "
        "repositories owned by this GitHub account.",
        "",
        "[Setup and maintenance guide](docs/SETUP.md)",
        "",
        f"**Repositories tracked:** "
        f"{len(repository_rows)}  ",
        f"**Stored period:** `{first_date}` "
        f"to `{last_date}`  ",
        f"**Last collection:** "
        f"`{generated_date} UTC`",
        "",
        "## Combined traffic summary",
        "",
        *_render_summary_table(
            combined_rows
        ),
        "",
        "> [!NOTE]",
        "> Unique counts are supplied per repository and per day. "
        "They cannot be deduplicated across different days or "
        "repositories because GitHub does not expose visitor identities.",
        "",
        "## Long-term views",
        "",
        "![Combined long-term views](charts/total-views.svg)",
        "",
        "## Long-term unique views",
        "",
        "![Combined long-term unique views](charts/total-unique-views.svg)",
        "",
        "## Long-term clones",
        "",
        "![Combined long-term clones](charts/total-clones.svg)",
        "",
        "## Long-term unique clones",
        "",
        "![Combined long-term unique clones](charts/total-unique-clones.svg)",
        "",
        "## Repository ranking",
        "",
        *_render_repository_ranking(
            repository_rows
        ),
        "",
        "## Combined top referring sites",
        "",
        "These values combine each repository's latest "
        "rolling traffic snapshot. They are not deduplicated.",
        "",
        *_render_referrer_table(
            referrers
        ),
        "",
        "## Most-viewed repository paths",
        "",
        "These are the highest reported paths from each "
        "repository's latest rolling traffic snapshot.",
        "",
        *_render_path_table(
            popular_paths
        ),
        "",
        "---",
        "",
        "[Setup and maintenance guide](docs/SETUP.md)",
        "",
        "_Generated automatically by "
        "`github-traffic-archive`._",
        "",
    ]

    content = "\n".join(lines)

    if (
        readme_file.exists()
        and readme_file.read_text(
            encoding="utf-8"
        )
        == content
    ):
        return False

    readme_file.write_text(
        content,
        encoding="utf-8",
    )

    return True
