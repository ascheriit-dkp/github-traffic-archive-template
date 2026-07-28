from __future__ import annotations

import math
import random
import shutil
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .aggregate import render_global_dashboard
from .dashboard import render_repository_readme
from .github_api import Repository
from .render import render_repository_charts
from .snapshots import save_traffic_snapshots
from .storage import upsert_traffic


DEMO_ROOT = Path("docs/demo")
DEMO_DATA_ROOT = DEMO_ROOT / "data" / "repos"
DEMO_CHART_DIRECTORY = DEMO_ROOT / "charts"
DEMO_README = DEMO_ROOT / "README.md"

DEMO_OWNER = "demo-user"
PROJECT_URL = (
    "https://github.com/"
    "ascheriit-dkp/"
    "github-traffic-archive-archive"
)

START_DATE = date(2026, 4, 1)
NUMBER_OF_DAYS = 90

COLLECTED_AT = datetime(
    2026,
    6,
    30,
    12,
    0,
    tzinfo=timezone.utc,
)

DEMO_NOTICE_LINES = [
    "> [!NOTE]",
    "> This is a generated demonstration. "
    "All repository names, dates, traffic figures, "
    "referrers, and paths shown here are fictional.",
]


@dataclass(frozen=True)
class DemoRepository:
    """Configuration for one fictional repository."""

    name: str
    description: str
    seed: int
    base_views: float
    daily_growth: float
    clone_rate: float
    release_days: tuple[int, ...]
    release_strengths: tuple[int, ...]


DEMO_REPOSITORIES = (
    DemoRepository(
        name="atlas-docs",
        description=(
            "Documentation portal for a fictional "
            "open-source mapping toolkit."
        ),
        seed=11,
        base_views=32,
        daily_growth=0.65,
        clone_rate=0.08,
        release_days=(18, 54, 76),
        release_strengths=(95, 135, 80),
    ),
    DemoRepository(
        name="release-radar",
        description=(
            "Fictional utility that tracks and summarizes "
            "software releases."
        ),
        seed=23,
        base_views=22,
        daily_growth=0.18,
        clone_rate=0.16,
        release_days=(14, 42, 70),
        release_strengths=(55, 70, 95),
    ),
    DemoRepository(
        name="tiny-cli",
        description=(
            "Small fictional command-line utility used "
            "to demonstrate lower-volume repository traffic."
        ),
        seed=37,
        base_views=6,
        daily_growth=0.05,
        clone_rate=0.23,
        release_days=(30, 64),
        release_strengths=(35, 50),
    ),
)


DEMO_REFERRERS: dict[
    str,
    list[dict[str, Any]],
] = {
    "atlas-docs": [
        {
            "referrer": "Google",
            "count": 486,
            "uniques": 391,
        },
        {
            "referrer": "github.com",
            "count": 138,
            "uniques": 76,
        },
        {
            "referrer": "DuckDuckGo",
            "count": 91,
            "uniques": 74,
        },
        {
            "referrer": "Hacker News",
            "count": 67,
            "uniques": 61,
        },
        {
            "referrer": "Bing",
            "count": 42,
            "uniques": 34,
        },
    ],
    "release-radar": [
        {
            "referrer": "Google",
            "count": 181,
            "uniques": 142,
        },
        {
            "referrer": "github.com",
            "count": 96,
            "uniques": 58,
        },
        {
            "referrer": "Reddit",
            "count": 54,
            "uniques": 47,
        },
        {
            "referrer": "DuckDuckGo",
            "count": 39,
            "uniques": 31,
        },
    ],
    "tiny-cli": [
        {
            "referrer": "github.com",
            "count": 43,
            "uniques": 28,
        },
        {
            "referrer": "Google",
            "count": 31,
            "uniques": 25,
        },
        {
            "referrer": "DuckDuckGo",
            "count": 12,
            "uniques": 10,
        },
    ],
}


DEMO_PATHS: dict[
    str,
    list[dict[str, Any]],
] = {
    "atlas-docs": [
        {
            "path": "/demo-user/atlas-docs",
            "title": "Overview",
            "count": 512,
            "uniques": 421,
        },
        {
            "path": (
                "/demo-user/atlas-docs/"
                "blob/main/README.md"
            ),
            "title": "README",
            "count": 194,
            "uniques": 153,
        },
        {
            "path": (
                "/demo-user/atlas-docs/"
                "tree/main/docs"
            ),
            "title": "Documentation",
            "count": 83,
            "uniques": 67,
        },
        {
            "path": (
                "/demo-user/atlas-docs/"
                "releases"
            ),
            "title": "Releases",
            "count": 49,
            "uniques": 41,
        },
    ],
    "release-radar": [
        {
            "path": "/demo-user/release-radar",
            "title": "Overview",
            "count": 226,
            "uniques": 174,
        },
        {
            "path": (
                "/demo-user/release-radar/"
                "blob/main/README.md"
            ),
            "title": "README",
            "count": 91,
            "uniques": 69,
        },
        {
            "path": (
                "/demo-user/release-radar/"
                "releases"
            ),
            "title": "Releases",
            "count": 53,
            "uniques": 44,
        },
    ],
    "tiny-cli": [
        {
            "path": "/demo-user/tiny-cli",
            "title": "Overview",
            "count": 61,
            "uniques": 47,
        },
        {
            "path": (
                "/demo-user/tiny-cli/"
                "blob/main/README.md"
            ),
            "title": "README",
            "count": 27,
            "uniques": 22,
        },
        {
            "path": (
                "/demo-user/tiny-cli/"
                "releases"
            ),
            "title": "Releases",
            "count": 14,
            "uniques": 12,
        },
    ],
}


def _release_boost(
    repository: DemoRepository,
    index: int,
) -> float:
    """Return a short traffic spike near release dates."""

    total = 0.0

    for release_day, strength in zip(
        repository.release_days,
        repository.release_strengths,
        strict=True,
    ):
        distance = abs(
            index - release_day
        )

        if distance <= 2:
            total += (
                strength
                * (3 - distance)
                / 3
            )

    return total


def _traffic_payloads(
    repository: DemoRepository,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Create deterministic fictional API payloads."""

    generator = random.Random(
        repository.seed
    )

    views_items: list[dict[str, Any]] = []
    clone_items: list[dict[str, Any]] = []

    for index in range(NUMBER_OF_DAYS):
        current_date = (
            START_DATE
            + timedelta(days=index)
        )

        weekday_factor = (
            0.72
            if current_date.weekday() >= 5
            else 1.0
        )

        seasonal_factor = (
            1.0
            + 0.14 * math.sin(index / 6)
            + 0.08 * math.cos(index / 13)
        )

        release_boost = _release_boost(
            repository,
            index,
        )

        baseline = (
            repository.base_views
            + repository.daily_growth * index
        )

        views = max(
            1,
            round(
                baseline
                * weekday_factor
                * seasonal_factor
                + release_boost
                + generator.randint(-5, 5)
            ),
        )

        unique_ratio = (
            0.66
            + 0.08 * math.sin(index / 9)
        )

        unique_views = min(
            views,
            max(
                1,
                round(
                    views * unique_ratio
                    + generator.randint(-2, 2)
                ),
            ),
        )

        clones = max(
            0,
            round(
                views * repository.clone_rate
                + release_boost * 0.05
                + generator.uniform(-1.0, 1.0)
            ),
        )

        unique_clones = min(
            clones,
            max(
                0,
                round(
                    clones
                    * (
                        0.72
                        + generator.random() * 0.15
                    )
                ),
            ),
        )

        timestamp = (
            f"{current_date.isoformat()}"
            "T00:00:00Z"
        )

        views_items.append(
            {
                "timestamp": timestamp,
                "count": views,
                "uniques": unique_views,
            }
        )

        clone_items.append(
            {
                "timestamp": timestamp,
                "count": clones,
                "uniques": unique_clones,
            }
        )

    return (
        {
            "count": sum(
                item["count"]
                for item in views_items
            ),
            "uniques": sum(
                item["uniques"]
                for item in views_items
            ),
            "views": views_items,
        },
        {
            "count": sum(
                item["count"]
                for item in clone_items
            ),
            "uniques": sum(
                item["uniques"]
                for item in clone_items
            ),
            "clones": clone_items,
        },
    )


def _add_demo_notice(
    content: str,
    *,
    project_link: str | None = None,
) -> str:
    """Insert an explicit fictional-data notice."""

    lines = content.splitlines()

    if not lines:
        return content

    result = [
        lines[0],
        "",
        *DEMO_NOTICE_LINES,
    ]

    if project_link is not None:
        result.extend(
            [
                "",
                (
                    "[Back to the project overview]"
                    f"({project_link})"
                ),
            ]
        )

    result.extend(
        [
            "",
            *lines[2:],
        ]
    )

    return (
        "\n".join(result).rstrip()
        + "\n"
    )


def _patch_repository_readme(
    repository_directory: Path,
) -> None:
    """Correct demo links and add the demo notice."""

    readme_file = (
        repository_directory
        / "README.md"
    )

    content = readme_file.read_text(
        encoding="utf-8"
    )

    content = content.replace(
        (
            "[Open the public repository]"
            f"({PROJECT_URL})"
        ),
        (
            "**Fictional repository:** "
            "this repository name and every displayed "
            "value are demonstration data."
        ),
    )

    content = content.replace(
        "../../../docs/SETUP.md",
        "../../../../SETUP.md",
    )

    content = _add_demo_notice(
        content
    )

    readme_file.write_text(
        content,
        encoding="utf-8",
    )


def _patch_global_readme() -> None:
    """Correct demo links and label the global dashboard."""

    content = DEMO_README.read_text(
        encoding="utf-8"
    )

    content = content.replace(
        "# GitHub Traffic Archive",
        (
            "# GitHub Traffic Archive "
            "— Generated Demo"
        ),
        1,
    )

    content = content.replace(
        (
            "Private long-term analytics for all public "
            "repositories owned by this GitHub account."
        ),
        (
            "Generated example of the combined "
            "long-term analytics dashboard."
        ),
    )

    content = content.replace(
        "docs/SETUP.md",
        "../SETUP.md",
    )

    content = _add_demo_notice(
        content,
        project_link="../../README.md",
    )

    DEMO_README.write_text(
        content,
        encoding="utf-8",
    )


def _generate_repository(
    repository: DemoRepository,
) -> None:
    """Generate all files for one fictional repository."""

    repository_directory = (
        DEMO_DATA_ROOT
        / repository.name
    )

    views_payload, clones_payload = (
        _traffic_payloads(
            repository
        )
    )

    upsert_traffic(
        repository_directory,
        views_payload,
        clones_payload,
    )

    save_traffic_snapshots(
        repository_directory,
        repository.name,
        DEMO_REFERRERS[
            repository.name
        ],
        DEMO_PATHS[
            repository.name
        ],
        collected_at=COLLECTED_AT,
    )

    render_repository_charts(
        repository_directory,
        repository.name,
    )

    render_repository_readme(
        repository_directory,
        Repository(
            name=repository.name,
            full_name=(
                f"{DEMO_OWNER}/"
                f"{repository.name}"
            ),
            html_url=PROJECT_URL,
            description=(
                repository.description
            ),
            fork=False,
            archived=False,
            disabled=False,
            visibility="public",
        ),
        COLLECTED_AT,
    )

    _patch_repository_readme(
        repository_directory
    )


def generate_demo() -> None:
    """Generate the complete fictional archive."""

    if DEMO_ROOT.exists():
        shutil.rmtree(
            DEMO_ROOT
        )

    for repository in DEMO_REPOSITORIES:
        print(
            "Generating fictional repository: "
            f"{repository.name}"
        )

        _generate_repository(
            repository
        )

    render_global_dashboard(
        collected_at=COLLECTED_AT,
        data_root=DEMO_DATA_ROOT,
        chart_directory=(
            DEMO_CHART_DIRECTORY
        ),
        readme_file=DEMO_README,
    )

    _patch_global_readme()

    print(
        "Generated fictional demo in "
        f"{DEMO_ROOT}"
    )


def main() -> int:
    """Command-line entry point."""

    generate_demo()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
