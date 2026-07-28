from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class SnapshotError(RuntimeError):
    """Raised when traffic snapshot data is invalid."""


def _non_negative_integer(
    value: Any,
    field: str,
) -> int:
    """Convert a value to a non-negative integer."""

    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise SnapshotError(
            f"Invalid integer for {field}: {value!r}"
        ) from exc

    if number < 0:
        raise SnapshotError(
            f"Negative integer for {field}: {number}"
        )

    return number


def _normalise_referrers(
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Validate and normalise referring-site entries."""

    normalised: list[dict[str, Any]] = []

    for item in items:
        referrer = item.get("referrer")

        if (
            not isinstance(referrer, str)
            or not referrer.strip()
        ):
            raise SnapshotError(
                "A referrer item has no valid referrer."
            )

        normalised.append(
            {
                "referrer": referrer.strip(),
                "count": _non_negative_integer(
                    item.get("count", 0),
                    "referrer count",
                ),
                "uniques": _non_negative_integer(
                    item.get("uniques", 0),
                    "referrer uniques",
                ),
            }
        )

    return normalised


def _normalise_paths(
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Validate and normalise popular-path entries."""

    normalised: list[dict[str, Any]] = []

    for item in items:
        path = item.get("path")
        title = item.get("title", "")

        if (
            not isinstance(path, str)
            or not path.strip()
        ):
            raise SnapshotError(
                "A popular-path item has no valid path."
            )

        if not isinstance(title, str):
            raise SnapshotError(
                "A popular-path item has no valid title."
            )

        normalised.append(
            {
                "path": path.strip(),
                "title": title.strip(),
                "count": _non_negative_integer(
                    item.get("count", 0),
                    "path count",
                ),
                "uniques": _non_negative_integer(
                    item.get("uniques", 0),
                    "path uniques",
                ),
            }
        )

    return normalised


def _read_existing_items(
    snapshot_file: Path,
) -> list[dict[str, Any]] | None:
    """Read items from an existing daily snapshot."""

    if not snapshot_file.exists():
        return None

    try:
        payload = json.loads(
            snapshot_file.read_text(
                encoding="utf-8",
            )
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise SnapshotError(
            f"Cannot read snapshot {snapshot_file}."
        ) from exc

    if not isinstance(payload, dict):
        raise SnapshotError(
            f"Snapshot {snapshot_file} is not an object."
        )

    items = payload.get("items")

    if not isinstance(items, list):
        raise SnapshotError(
            f"Snapshot {snapshot_file} "
            "has no valid items list."
        )

    return items


def _write_snapshot(
    snapshot_file: Path,
    *,
    repository_name: str,
    collected_at: datetime,
    items: list[dict[str, Any]],
) -> bool:
    """Write one daily snapshot when its data changed."""

    existing_items = _read_existing_items(
        snapshot_file
    )

    if existing_items == items:
        return False

    timestamp = (
        collected_at
        .astimezone(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )

    payload = {
        "repository": repository_name,
        "collected_at": timestamp,
        "window": "rolling_14_days",
        "items": items,
    }

    content = (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )

    snapshot_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_file = snapshot_file.with_suffix(
        ".json.tmp"
    )

    temporary_file.write_text(
        content,
        encoding="utf-8",
    )

    temporary_file.replace(
        snapshot_file
    )

    return True


def save_traffic_snapshots(
    repository_directory: Path,
    repository_name: str,
    referrers: list[dict[str, Any]],
    popular_paths: list[dict[str, Any]],
    *,
    collected_at: datetime | None = None,
) -> bool:
    """Save today's referrer and path snapshots.

    Returns True when at least one snapshot changed.
    """

    if not repository_name.strip():
        raise ValueError(
            "The repository name is empty."
        )

    if not isinstance(referrers, list):
        raise SnapshotError(
            "Referrers must be a list."
        )

    if not isinstance(popular_paths, list):
        raise SnapshotError(
            "Popular paths must be a list."
        )

    moment = (
        collected_at
        or datetime.now(timezone.utc)
    )

    if moment.tzinfo is None:
        raise ValueError(
            "collected_at must include "
            "timezone information."
        )

    snapshot_date = (
        moment
        .astimezone(timezone.utc)
        .date()
        .isoformat()
    )

    referrers_changed = _write_snapshot(
        (
            repository_directory
            / "referrers"
            / f"{snapshot_date}.json"
        ),
        repository_name=repository_name,
        collected_at=moment,
        items=_normalise_referrers(
            referrers
        ),
    )

    paths_changed = _write_snapshot(
        (
            repository_directory
            / "paths"
            / f"{snapshot_date}.json"
        ),
        repository_name=repository_name,
        collected_at=moment,
        items=_normalise_paths(
            popular_paths
        ),
    )

    return (
        referrers_changed
        or paths_changed
    )
