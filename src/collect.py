from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .aggregate import (
    AggregateError,
    render_global_dashboard,
)
from .dashboard import (
    DashboardError,
    render_repository_readme,
)
from .github_api import (
    GitHubAPIError,
    GitHubClient,
    Repository,
)
from .render import (
    RenderError,
    render_repository_charts,
)
from .snapshots import (
    SnapshotError,
    save_traffic_snapshots,
)
from .storage import (
    StorageError,
    repository_data_dir,
    upsert_traffic,
)


CONFIG_FILE = Path("config.yaml")
TOKEN_ENVIRONMENT_VARIABLE = "TRAFFIC_TOKEN"
OWNER_ENVIRONMENT_VARIABLE = "GITHUB_REPOSITORY_OWNER"
REPOSITORY_ENVIRONMENT_VARIABLE = "GITHUB_REPOSITORY"


class ConfigurationError(RuntimeError):
    """Raised when the runtime configuration is missing or invalid."""


@dataclass(frozen=True)
class ArchiveConfig:
    """Configuration required by the collector."""

    owner: str
    archive_repository_name: str | None
    include_forks: bool
    include_archived: bool
    excluded_repositories: frozenset[str]


@dataclass
class RunSummary:
    """Counters describing one collection run."""

    discovered: int = 0
    selected: int = 0
    filtered: int = 0
    updated: int = 0
    unchanged: int = 0
    inaccessible: int = 0
    partial: int = 0
    failed: int = 0


def _require_mapping(
    value: Any,
    name: str,
) -> dict[str, Any]:
    """Validate that a configuration section is a mapping."""

    if not isinstance(value, dict):
        raise ConfigurationError(
            f"{name} must be a YAML mapping."
        )

    return value


def _read_boolean(
    section: dict[str, Any],
    key: str,
    *,
    default: bool,
) -> bool:
    """Read a strict boolean configuration value."""

    value = section.get(key, default)

    if not isinstance(value, bool):
        raise ConfigurationError(
            f"repositories.{key} must be true or false."
        )

    return value


def read_owner() -> str:
    """Detect the GitHub account that owns the archive."""

    owner = os.environ.get(
        OWNER_ENVIRONMENT_VARIABLE,
        "",
    ).strip()

    if not owner:
        raise ConfigurationError(
            f"The {OWNER_ENVIRONMENT_VARIABLE} "
            "environment variable is missing."
        )

    return owner


def read_archive_repository_name() -> str | None:
    """Return the current archive repository name."""

    full_name = os.environ.get(
        REPOSITORY_ENVIRONMENT_VARIABLE,
        "",
    ).strip()

    if "/" not in full_name:
        return None

    _, repository_name = full_name.split(
        "/",
        maxsplit=1,
    )

    return repository_name or None


def load_config(
    *,
    owner: str,
    archive_repository_name: str | None,
    config_file: Path = CONFIG_FILE,
) -> ArchiveConfig:
    """Read and validate config.yaml."""

    if not config_file.exists():
        raise ConfigurationError(
            f"Configuration file not found: {config_file}"
        )

    try:
        raw_config = yaml.safe_load(
            config_file.read_text(
                encoding="utf-8",
            )
        )
    except OSError as exc:
        raise ConfigurationError(
            f"Cannot read {config_file}."
        ) from exc
    except yaml.YAMLError as exc:
        raise ConfigurationError(
            f"Invalid YAML in {config_file}."
        ) from exc

    root = _require_mapping(
        raw_config,
        "The root configuration",
    )

    repositories_section = _require_mapping(
        root.get("repositories", {}),
        "repositories",
    )

    excluded = repositories_section.get(
        "exclude",
        [],
    )

    if not isinstance(excluded, list):
        raise ConfigurationError(
            "repositories.exclude must be a list."
        )

    excluded_names: set[str] = set()

    for value in excluded:
        if not isinstance(value, str):
            raise ConfigurationError(
                "Every repositories.exclude "
                "entry must be a string."
            )

        cleaned = value.strip()

        if cleaned:
            excluded_names.add(
                cleaned.casefold()
            )

    return ArchiveConfig(
        owner=owner,
        archive_repository_name=archive_repository_name,
        include_forks=_read_boolean(
            repositories_section,
            "include_forks",
            default=False,
        ),
        include_archived=_read_boolean(
            repositories_section,
            "include_archived",
            default=False,
        ),
        excluded_repositories=frozenset(
            excluded_names
        ),
    )


def read_token() -> str:
    """Read the traffic token from the environment."""

    token = os.environ.get(
        TOKEN_ENVIRONMENT_VARIABLE,
        "",
    ).strip()

    if not token:
        raise ConfigurationError(
            f"The {TOKEN_ENVIRONMENT_VARIABLE} "
            "environment variable is missing."
        )

    return token


def repository_filter_reason(
    repository: Repository,
    config: ArchiveConfig,
) -> str | None:
    """Return why a repository must be ignored."""

    if repository.disabled:
        return "repository is disabled"

    if (
        config.archive_repository_name
        and repository.name.casefold()
        == config.archive_repository_name.casefold()
    ):
        return "repository is the traffic archive itself"

    if (
        repository.fork
        and not config.include_forks
    ):
        return "forks are disabled in config.yaml"

    if (
        repository.archived
        and not config.include_archived
    ):
        return "archived repositories are disabled"

    if (
        repository.name.casefold()
        in config.excluded_repositories
    ):
        return "repository is explicitly excluded"

    return None


def collect_repository(
    client: GitHubClient,
    repository: Repository,
    collected_at: datetime,
) -> tuple[str, bool]:
    """Collect and store all available repository traffic."""

    views = client.get_views(
        repository.name
    )

    clones = client.get_clones(
        repository.name
    )

    if views is None or clones is None:
        return "inaccessible", False

    repository_directory = repository_data_dir(
        repository.name
    )

    traffic_changed = upsert_traffic(
        repository_directory,
        views,
        clones,
    )

    referrers = client.get_referrers(
        repository.name
    )

    popular_paths = client.get_popular_paths(
        repository.name
    )

    if (
        referrers is None
        or popular_paths is None
    ):
        return "partial", traffic_changed

    snapshots_changed = save_traffic_snapshots(
        repository_directory,
        repository.name,
        referrers,
        popular_paths,
        collected_at=collected_at,
    )

    render_repository_charts(
        repository_directory,
        repository.name,
    )

    readme_changed = render_repository_readme(
        repository_directory,
        repository,
        collected_at,
    )

    return (
        "complete",
        (
            traffic_changed
            or snapshots_changed
            or readme_changed
        ),
    )


def print_summary(
    summary: RunSummary,
) -> None:
    """Print a readable end-of-run summary."""

    print()
    print("=" * 52)
    print("GitHub traffic collection summary")
    print("=" * 52)
    print(
        f"Repositories discovered: {summary.discovered}"
    )
    print(
        f"Repositories selected:   {summary.selected}"
    )
    print(
        f"Repositories filtered:   {summary.filtered}"
    )
    print(
        f"Repositories updated:    {summary.updated}"
    )
    print(
        f"Repositories unchanged:  {summary.unchanged}"
    )
    print(
        f"Traffic inaccessible:    {summary.inaccessible}"
    )
    print(
        f"Partial collections:     {summary.partial}"
    )
    print(
        f"Failed collections:      {summary.failed}"
    )


def run_collection() -> RunSummary:
    """Run one complete collection operation."""

    owner = read_owner()

    config = load_config(
        owner=owner,
        archive_repository_name=(
            read_archive_repository_name()
        ),
    )

    token = read_token()

    client = GitHubClient(
        token=token,
        owner=config.owner,
    )

    print(
        f"Discovering public repositories "
        f"owned by {config.owner}..."
    )

    repositories = (
        client.list_owned_public_repositories()
    )

    summary = RunSummary(
        discovered=len(repositories)
    )

    selected_repositories: list[Repository] = []

    for repository in repositories:
        reason = repository_filter_reason(
            repository,
            config,
        )

        if reason is not None:
            summary.filtered += 1
            print(
                f"Filtered {repository.full_name}: "
                f"{reason}."
            )
            continue

        selected_repositories.append(
            repository
        )

    summary.selected = len(
        selected_repositories
    )

    collected_at = datetime.now(
        timezone.utc
    )

    if not selected_repositories:
        print(
            "No repositories matched "
            "the current configuration."
        )
        print_summary(summary)
        return summary

    total = len(selected_repositories)

    for index, repository in enumerate(
        selected_repositories,
        start=1,
    ):
        print()
        print(
            f"[{index}/{total}] "
            f"Collecting {repository.full_name}"
        )

        try:
            status, changed = collect_repository(
                client,
                repository,
                collected_at,
            )
        except (
            GitHubAPIError,
            StorageError,
            SnapshotError,
            RenderError,
            DashboardError,
            OSError,
            ValueError,
        ) as exc:
            summary.failed += 1
            print(
                f"Failed {repository.full_name}: "
                f"{exc}"
            )
            continue

        if status == "inaccessible":
            summary.inaccessible += 1
            print(
                "Skipped: repository traffic "
                "is unavailable to the token."
            )
            continue

        if status == "partial":
            summary.partial += 1
            print(
                "Traffic history stored, but "
                "referrer or path data was unavailable."
            )

        if changed:
            summary.updated += 1
            print(
                "Stored data was created or updated."
            )
        else:
            summary.unchanged += 1
            print(
                "Stored data is already current."
            )

    print()
    print("Generating combined root dashboard...")

    render_global_dashboard(
        collected_at=collected_at,
    )

    print(
        "Combined root dashboard generated."
    )

    print_summary(summary)

    return summary


def main() -> int:
    """Command-line entry point."""

    try:
        run_collection()
    except (
        ConfigurationError,
        GitHubAPIError,
        AggregateError,
    ) as exc:
        print(
            f"Fatal collection error: {exc}",
            file=sys.stderr,
        )
        return 1
    except KeyboardInterrupt:
        print(
            "Collection interrupted.",
            file=sys.stderr,
        )
        return 130

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
