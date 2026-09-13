"""Public GitHub facts for one observation window, via the GraphQL API."""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from . import config

API = "https://api.github.com/graphql"

_REPO_FIELDS = """
  nameWithOwner url isPrivate
  primaryLanguage { name }
  defaultBranchRef { target { ... on Commit { oid committedDate history { totalCount } } } }
"""

_USER_FIELDS = """
  organizations(first: 50) { nodes { login } }
  contributionsCollection(from: $from, to: $to) { contributionCalendar { totalContributions } }
  pullRequests(first: 100, orderBy: { field: CREATED_AT, direction: DESC }) {
    nodes {
      number title url state createdAt
      repository { nameWithOwner isPrivate stargazerCount owner { login } }
    }
  }
"""


@dataclass(frozen=True)
class Repo:
    name: str
    url: str
    head: str | None
    committed: str | None
    commits: int
    language: str | None


@dataclass(frozen=True)
class PullRequest:
    repo: str
    number: int
    title: str
    url: str
    state: str
    created: str
    target_stars: int


@dataclass(frozen=True)
class Snapshot:
    window_from: datetime
    window_to: datetime
    observed_at: datetime
    contributions: int
    repos: dict[str, Repo | None]
    upstream: tuple[PullRequest, ...]

    def evidence(self) -> dict[str, Any]:
        return {
            "observed_at": _iso(self.observed_at),
            "window": {"from": _iso(self.window_from), "to": _iso(self.window_to)},
            "contributions": self.contributions,
            "heads": {name: repo.head if repo else None for name, repo in sorted(self.repos.items())},
            "upstream": sorted(
                ({"repo": pr.repo, "number": pr.number, "state": pr.state} for pr in self.upstream),
                key=lambda item: (item["repo"], item["number"]),
            ),
        }


def _iso(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _post(token: str, query: str, variables: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        API,
        data=json.dumps({"query": query, "variables": variables}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": f"{config.SUBJECT}-chain-of-custody",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        body = json.loads(response.read().decode("utf-8"))
    fatal = [e for e in body.get("errors", []) if e.get("type") != "NOT_FOUND"]
    if fatal or "data" not in body:
        raise RuntimeError(f"GraphQL error: {fatal or body}")
    return body["data"]


def _repo(node: dict[str, Any] | None) -> Repo | None:
    if node is None:
        return None
    if node["isPrivate"]:
        # Everything rendered is published; a private repository must never be sealed or shown.
        raise RuntimeError(f"{node['nameWithOwner']} is private; remove it from config.EXHIBITS")
    commit = (node.get("defaultBranchRef") or {}).get("target") or {}
    return Repo(
        name=node["nameWithOwner"],
        url=node["url"],
        head=commit.get("oid"),
        committed=commit.get("committedDate"),
        commits=(commit.get("history") or {}).get("totalCount", 0),
        language=(node.get("primaryLanguage") or {}).get("name"),
    )


def snapshot(token: str, window_from: datetime, window_to: datetime, observed_at: datetime) -> Snapshot:
    aliases = "\n".join(
        f"r{i}: repository(owner: {json.dumps(owner)}, name: {json.dumps(name)}) {{ {_REPO_FIELDS} }}"
        for i, (owner, name) in enumerate(repo.split("/", 1) for repo in config.SEALED_REPOS)
    )
    query = (
        "query($login: String!, $from: DateTime!, $to: DateTime!) {\n"
        f"  user(login: $login) {{ {_USER_FIELDS} }}\n{aliases}\n}}"
    )
    data = _post(token, query, {"login": config.SUBJECT, "from": _iso(window_from), "to": _iso(window_to)})

    user = data["user"]
    own = {config.SUBJECT.lower()} | {org["login"].lower() for org in user["organizations"]["nodes"]}
    upstream = tuple(
        PullRequest(
            repo=node["repository"]["nameWithOwner"],
            number=node["number"],
            title=node["title"],
            url=node["url"],
            state=node["state"],
            created=node["createdAt"],
            target_stars=node["repository"]["stargazerCount"],
        )
        for node in user["pullRequests"]["nodes"]
        if not node["repository"]["isPrivate"] and node["repository"]["owner"]["login"].lower() not in own
    )

    return Snapshot(
        window_from=window_from,
        window_to=window_to,
        observed_at=observed_at,
        contributions=user["contributionsCollection"]["contributionCalendar"]["totalContributions"],
        repos={repo: _repo(data.get(f"r{i}")) for i, repo in enumerate(config.SEALED_REPOS)},
        upstream=upstream,
    )
