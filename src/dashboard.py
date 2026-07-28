from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .github_api import Repository
from .render import TrafficRow, read_traffic_rows


class DashboardError(RuntimeError):
    """Raised when a Markdown dashboard cannot be generated."""


def _escape_table_text(value: Any) -> str:
    """Escape text for use inside a Markdown table."""

    text = str(value)

    return (
        text
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
    """Return the sum of one stored traffic metric."""

    return sum(
        int(getattr(row, metric))
        for row in rows
    )


def _latest_snapshot(
    snapshot_directory: Path,
) -> tuple[str | None, list[dict[str, Any]]]:
    """Read the latest dated JSON snapshot."""

    if not snapshot_directory.exists():
        return None, []

    snapshot_files = sorted(
        snapshot_directory.glob("*.json")
    )

    if not snapshot_files:
        return None, []

    snapshot_file = snapshot_files[-1]

    try:
        payload = json.loads(
            snapshot_file.read_text(
                encoding="utf-8",
            )
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise DashboardError(
            f"Cannot read snapshot {snapshot_file}."
        ) from exc

    if not isinstance(payload, dict):
        raise DashboardError(
            f"Snapshot {snapshot_file} "
            "must contain a JSON object."
        )

    items = payload.get("items")

    if not isinstance(items, list):
        raise DashboardError(
            f"Snapshot {snapshot_file} "
            "has no valid items list."
        )

    valid_items: list[dict[str, Any]] = []

    for item in items:
        if not isinstance(item, dict):
            raise DashboardError(
                f"Snapshot {snapshot_file} "
                "contains an invalid item."
            )

        valid_items.append(item)

    return snapshot_file.stem, valid_items


def _render_metric_summary(
    rows: list[TrafficRow],
) -> list[str]:
    """Render the traffic totals table."""

    recent_rows = rows[-14:]

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
        "| Metric | Since tracking began | Latest 14 stored days |",
        "|---|---:|---:|",
    ]

    for label, metric in metrics:
        all_time_total = _metric_total(
            rows,
            metric,
        )

        recent_total = _metric_total(
            recent_rows,
            metric,
        )

        lines.append(
            f"| {label} "
            f"| {all_time_total:,} "
            f"| {recent_total:,} |"
        )

    return lines


def _render_referrers(
    items: list[dict[str, Any]],
) -> list[str]:
    """Render a referring-sites table."""

    if not items:
        return [
            "_No referring sites were reported "
            "in the latest snapshot._"
        ]

    lines = [
        "| Referring site | Views | Unique visitors |",
        "|---|---:|---:|",
    ]

    for item in items:
        referrer = _escape_table_text(
            item.get("referrer", "")
        )

        count = int(
            item.get("count", 0)
        )

        uniques = int(
            item.get("uniques", 0)
        )

        lines.append(
            f"| {referrer} "
            f"| {count:,} "
            f"| {uniques:,} |"
        )

    return lines


def _render_popular_paths(
    items: list[dict[str, Any]],
) -> list[str]:
    """Render a popular repository-path table."""

    if not items:
        return [
            "_No popular paths were reported "
            "in the latest snapshot._"
        ]

    lines = [
        "| Repository path | Page title | Views | Unique visitors |",
        "|---|---|---:|---:|",
    ]

    for item in items:
        path = _escape_table_text(
            item.get("path", "")
        )

        title = _escape_table_text(
            item.get("title", "")
        )

        count = int(
            item.get("count", 0)
        )

        uniques = int(
            item.get("uniques", 0)
        )

        lines.append(
            f"| `{path}` "
            f"| {title} "
            f"| {count:,} "
            f"| {uniques:,} |"
        )

    return lines


def render_repository_readme(
    repository_directory: Path,
    repository: Repository,
    collected_at: datetime,
) -> bool:
    """Generate one repository's Markdown dashboard.

    Returns True only when README.md changed.
    """

    if collected_at.tzinfo is None:
        raise ValueError(
            "collected_at must include timezone information."
        )

    traffic_file = (
        repository_directory
        / "traffic.csv"
    )

    rows = read_traffic_rows(
        traffic_file
    )

    if not rows:
        raise DashboardError(
            f"No traffic exists for {repository.full_name}."
        )

    referrer_date, referrers = _latest_snapshot(
        repository_directory
        / "referrers"
    )

    path_date, popular_paths = _latest_snapshot(
        repository_directory
        / "paths"
    )

    first_date = rows[0].day.isoformat()
    last_date = rows[-1].day.isoformat()

    collection_date = (
        collected_at
        .astimezone(timezone.utc)
        .date()
        .isoformat()
    )

    description = (
        repository.description.strip()
        or "No repository description."
    )

    lines = [
        f"# {repository.name}",
        "",
        f"> {_escape_table_text(description)}",
        "",
        f"[Open the public repository]({repository.html_url})",
        "",
        f"**Tracked period:** `{first_date}` to `{last_date}`  ",
        f"**Last collection:** `{collection_date} UTC`",
        "",
        "## Traffic summary",
        "",
        *_render_metric_summary(rows),
        "",
        "> [!NOTE]",
        "> GitHub provides unique counts for each individual day, "
        "but does not provide visitor identities. The same person "
        "may therefore be counted again on another day or in another "
        "repository.",
        "",
        "## Long-term views",
        "",
        "![Long-term views](charts/views.svg)",
        "",
        "## Long-term unique views",
        "",
        "![Long-term unique views](charts/unique-views.svg)",
        "",
        "## Long-term clones",
        "",
        "![Long-term clones](charts/clones.svg)",
        "",
        "## Long-term unique clones",
        "",
        "![Long-term unique clones](charts/unique-clones.svg)",
        "",
        "## Top referring sites",
        "",
    ]

    if referrer_date is not None:
        lines.extend(
            [
                f"Latest rolling snapshot: `{referrer_date}`",
                "",
            ]
        )

    lines.extend(
        _render_referrers(
            referrers
        )
    )

    lines.extend(
        [
            "",
            "## Most-viewed repository paths",
            "",
        ]
    )

    if path_date is not None:
        lines.extend(
            [
                f"Latest rolling snapshot: `{path_date}`",
                "",
            ]
        )

    lines.extend(
        _render_popular_paths(
            popular_paths
        )
    )

    lines.extend(
        [
            "",
            "---",
            "",
            "_Generated automatically by "
            "`github-traffic-archive`._",
            "",
        ]
    )

    content = "\n".join(lines)

    readme_file = (
        repository_directory
        / "README.md"
    )

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
