from __future__ import annotations

import csv
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any


FIELDS = [
    "date",
    "views",
    "unique_views",
    "clones",
    "unique_clones",
]


class StorageError(RuntimeError):
    """Raised when stored or received traffic data is invalid."""


def repository_data_dir(
    repository_name: str,
) -> Path:
    """Return data/repos/<repository-name>."""

    if not repository_name or repository_name in {".", ".."}:
        raise ValueError("Invalid repository name.")

    return Path("data/repos") / repository_name


def _to_date(timestamp: str) -> str:
    """Convert a GitHub timestamp to a UTC YYYY-MM-DD date."""

    try:
        parsed = datetime.fromisoformat(
            timestamp.replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise StorageError(
            f"Invalid GitHub timestamp: {timestamp!r}"
        ) from exc

    return (
        parsed
        .astimezone(timezone.utc)
        .date()
        .isoformat()
    )


def _to_integer(
    value: Any,
    field: str,
) -> int:
    """Convert an API or CSV value to a non-negative integer."""

    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise StorageError(
            f"Invalid integer for {field}: {value!r}"
        ) from exc

    if number < 0:
        raise StorageError(
            f"Negative integer for {field}: {number}"
        )

    return number


def _empty_row(
    date: str,
) -> dict[str, int | str]:
    """Create an empty daily traffic row."""

    return {
        "date": date,
        "views": 0,
        "unique_views": 0,
        "clones": 0,
        "unique_clones": 0,
    }


def _read_rows(
    traffic_file: Path,
) -> dict[str, dict[str, int | str]]:
    """Read traffic.csv and index its rows by date."""

    if not traffic_file.exists():
        return {}

    rows: dict[str, dict[str, int | str]] = {}

    with traffic_file.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        reader = csv.DictReader(handle)

        if reader.fieldnames != FIELDS:
            raise StorageError(
                f"Unexpected columns in {traffic_file}"
            )

        for item in reader:
            date = item["date"].strip()

            try:
                datetime.strptime(
                    date,
                    "%Y-%m-%d",
                )
            except ValueError as exc:
                raise StorageError(
                    f"Invalid date in {traffic_file}: "
                    f"{date!r}"
                ) from exc

            rows[date] = {
                "date": date,
                "views": _to_integer(
                    item["views"],
                    "views",
                ),
                "unique_views": _to_integer(
                    item["unique_views"],
                    "unique_views",
                ),
                "clones": _to_integer(
                    item["clones"],
                    "clones",
                ),
                "unique_clones": _to_integer(
                    item["unique_clones"],
                    "unique_clones",
                ),
            }

    return rows


def _merge_metric(
    rows: dict[str, dict[str, int | str]],
    items: list[dict[str, Any]],
    count_field: str,
    unique_field: str,
) -> None:
    """Merge one daily GitHub metric into stored rows."""

    for item in items:
        timestamp = item.get("timestamp")

        if not isinstance(timestamp, str):
            raise StorageError(
                "A traffic item has no valid timestamp."
            )

        date = _to_date(timestamp)

        row = rows.setdefault(
            date,
            _empty_row(date),
        )

        row[count_field] = _to_integer(
            item.get("count", 0),
            count_field,
        )

        row[unique_field] = _to_integer(
            item.get("uniques", 0),
            unique_field,
        )


def _render_csv(
    rows: dict[str, dict[str, int | str]],
) -> str:
    """Render traffic rows deterministically as CSV."""

    output = StringIO(newline="")

    writer = csv.DictWriter(
        output,
        fieldnames=FIELDS,
        lineterminator="\n",
    )

    writer.writeheader()

    for date in sorted(rows):
        writer.writerow(rows[date])

    return output.getvalue()


def upsert_traffic(
    repository_directory: Path,
    views_payload: dict[str, Any],
    clones_payload: dict[str, Any],
) -> bool:
    """Merge the latest API window into traffic.csv.

    Returns True only when traffic.csv changed.
    """

    views = views_payload.get("views", [])
    clones = clones_payload.get("clones", [])

    if not isinstance(views, list):
        raise StorageError(
            "The API views field is not a list."
        )

    if not isinstance(clones, list):
        raise StorageError(
            "The API clones field is not a list."
        )

    traffic_file = (
        repository_directory
        / "traffic.csv"
    )

    rows = _read_rows(traffic_file)

    _merge_metric(
        rows,
        views,
        "views",
        "unique_views",
    )

    _merge_metric(
        rows,
        clones,
        "clones",
        "unique_clones",
    )

    content = _render_csv(rows)

    if (
        traffic_file.exists()
        and traffic_file.read_text(
            encoding="utf-8"
        )
        == content
    ):
        return False

    repository_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_file = (
        traffic_file
        .with_name("traffic.csv.tmp")
    )

    temporary_file.write_text(
        content,
        encoding="utf-8",
    )

    temporary_file.replace(
        traffic_file
    )

    return True
