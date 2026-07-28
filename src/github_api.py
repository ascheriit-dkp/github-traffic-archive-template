from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

API_BASE_URL = "https://api.github.com"
API_VERSION = "2026-03-10"
DEFAULT_TIMEOUT_SECONDS = 30


class GitHubAPIError(RuntimeError):
    """Raised when GitHub returns an unexpected API response."""


@dataclass(frozen=True)
class Repository:
    """Small repository representation used by the collector."""

    name: str
    full_name: str
    html_url: str
    description: str
    fork: bool
    archived: bool
    disabled: bool
    visibility: str


class GitHubClient:
    """Minimal GitHub REST API client for traffic collection."""

    def __init__(self, token: str, owner: str) -> None:
        if not token.strip():
            raise ValueError("The GitHub token is empty.")

        if not owner.strip():
            raise ValueError("The GitHub owner is empty.")

        self.owner = owner

        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": API_VERSION,
                "User-Agent": "github-traffic-archive",
            }
        )

    def _get_json(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        traffic_endpoint: bool = False,
    ) -> Any | None:
        """Perform a GET request and decode its JSON response."""

        response = self.session.get(
            f"{API_BASE_URL}{path}",
            params=params,
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )

        # A repository can be visible while its traffic endpoint is
        # unavailable to the token. Such repositories will be skipped.
        if traffic_endpoint and response.status_code in {403, 404}:
            if response.headers.get("X-RateLimit-Remaining") == "0":
                reset_at = response.headers.get(
                    "X-RateLimit-Reset",
                    "unknown",
                )

                raise GitHubAPIError(
                    "GitHub API rate limit exhausted; "
                    f"reset timestamp: {reset_at}."
                )

            return None

        if not response.ok:
            try:
                message = response.json().get(
                    "message",
                    response.text,
                )
            except ValueError:
                message = response.text

            raise GitHubAPIError(
                "GitHub API request failed: "
                f"{response.status_code} "
                f"{response.reason} for {path}: {message}"
            )

        try:
            return response.json()
        except ValueError as exc:
            raise GitHubAPIError(
                f"GitHub returned invalid JSON for {path}."
            ) from exc

    def list_owned_public_repositories(
        self,
    ) -> list[Repository]:
        """Return all public repositories owned by the account."""

        repositories: list[Repository] = []
        page = 1

        while True:
            payload = self._get_json(
                "/user/repos",
                params={
                    "visibility": "public",
                    "affiliation": "owner",
                    "sort": "full_name",
                    "direction": "asc",
                    "per_page": 100,
                    "page": page,
                },
            )

            if not isinstance(payload, list):
                raise GitHubAPIError(
                    "GitHub returned an unexpected "
                    "repository-list response."
                )

            for item in payload:
                item_owner = (
                    item.get("owner", {}).get("login", "")
                )

                if item_owner.casefold() != self.owner.casefold():
                    continue

                if item.get("private", False):
                    continue

                repositories.append(
                    Repository(
                        name=item["name"],
                        full_name=item["full_name"],
                        html_url=item["html_url"],
                        description=(
                            item.get("description") or ""
                        ),
                        fork=bool(item.get("fork", False)),
                        archived=bool(
                            item.get("archived", False)
                        ),
                        disabled=bool(
                            item.get("disabled", False)
                        ),
                        visibility=item.get(
                            "visibility",
                            "public",
                        ),
                    )
                )

            if len(payload) < 100:
                break

            page += 1

        return repositories

    def get_views(
        self,
        repository_name: str,
    ) -> dict[str, Any] | None:
        """Return the latest daily view information."""

        payload = self._get_json(
            (
                f"/repos/{self.owner}/{repository_name}"
                "/traffic/views"
            ),
            params={"per": "day"},
            traffic_endpoint=True,
        )

        return payload if isinstance(payload, dict) else None

    def get_clones(
        self,
        repository_name: str,
    ) -> dict[str, Any] | None:
        """Return the latest daily clone information."""

        payload = self._get_json(
            (
                f"/repos/{self.owner}/{repository_name}"
                "/traffic/clones"
            ),
            params={"per": "day"},
            traffic_endpoint=True,
        )

        return payload if isinstance(payload, dict) else None

    def get_referrers(
        self,
        repository_name: str,
    ) -> list[dict[str, Any]] | None:
        """Return the current top referring sites."""

        payload = self._get_json(
            (
                f"/repos/{self.owner}/{repository_name}"
                "/traffic/popular/referrers"
            ),
            traffic_endpoint=True,
        )

        return payload if isinstance(payload, list) else None

    def get_popular_paths(
        self,
        repository_name: str,
    ) -> list[dict[str, Any]] | None:
        """Return the current most-viewed repository paths."""

        payload = self._get_json(
            (
                f"/repos/{self.owner}/{repository_name}"
                "/traffic/popular/paths"
            ),
            traffic_endpoint=True,
        )

        return payload if isinstance(payload, list) else None
