from __future__ import annotations

import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


README_PATH = Path(__file__).resolve().parents[1] / "README.md"
START_MARKER = "<!-- OSS-STATS:START -->"
END_MARKER = "<!-- OSS-STATS:END -->"
USERNAME = os.environ.get("GITHUB_USERNAME", "terminalchai")
MAX_RECENT_PRS = 6
PER_PAGE = 100


def github_token() -> str:
    token = (
        os.environ.get("GITHUB_TOKEN")
        or os.environ.get("GH_TOKEN")
        or os.environ.get("GITHUB_PAT")
    )
    if not token:
        raise RuntimeError("Missing GITHUB_TOKEN, GH_TOKEN, or GITHUB_PAT")
    return token


def api_get(url: str, token: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "terminalchai-oss-stats-updater",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request) as response:
        return json.load(response)


def search_merged_prs(token: str) -> list[dict]:
    base_query = f"is:pr is:merged author:{USERNAME} -user:{USERNAME}"
    encoded_query = urllib.parse.quote(base_query, safe="")
    first_page_url = (
        "https://api.github.com/search/issues"
        f"?q={encoded_query}&per_page={PER_PAGE}&page=1"
    )
    first_page = api_get(first_page_url, token)
    items = list(first_page.get("items", []))
    total_count = int(first_page.get("total_count", 0))
    total_pages = max(1, (min(total_count, 1000) + PER_PAGE - 1) // PER_PAGE)

    for page in range(2, total_pages + 1):
        page_url = (
            "https://api.github.com/search/issues"
            f"?q={encoded_query}&per_page={PER_PAGE}&page={page}"
        )
        page_data = api_get(page_url, token)
        items.extend(page_data.get("items", []))

    return items


def parse_repo_name(repository_url: str) -> str:
    return repository_url.removeprefix("https://api.github.com/repos/")


def parse_merged_at(item: dict) -> datetime:
    merged_at = item.get("pull_request", {}).get("merged_at")
    if not merged_at:
        return datetime.min.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(merged_at.replace("Z", "+00:00"))


def format_badge(label: str, value: str, color: str, logo: str | None = None) -> str:
    encoded_label = urllib.parse.quote(label)
    encoded_value = urllib.parse.quote(value)
    logo_part = f"&logo={urllib.parse.quote(logo)}&logoColor=white" if logo else ""
    return (
        "https://img.shields.io/badge/"
        f"{encoded_label}-{encoded_value}-{color}?style=for-the-badge{logo_part}"
    )


def build_stats_block(items: list[dict]) -> str:
    merged_items = [item for item in items if item.get("pull_request", {}).get("merged_at")]
    merged_items.sort(key=parse_merged_at, reverse=True)

    merged_count = len(merged_items)
    repo_count = len({parse_repo_name(item["repository_url"]) for item in merged_items})

    counts = [
        (
            "Merged OSS PRs",
            str(merged_count),
            "111827",
            "github",
            "Merged OSS PRs",
        ),
        (
            "Repos Contributed To",
            str(repo_count),
            "0f172a",
            None,
            "Repos contributed to",
        ),
    ]

    lines = [
        '<p align="center">',
    ]
    for label, value, color, logo, alt in counts:
        badge_url = format_badge(label, value, color, logo)
        lines.append(f'  <img src="{badge_url}" alt="{alt}" />')
    lines.append("</p>")
    lines.append("")

    if merged_items:
        lines.append("Recent merged PRs:")
        lines.append("")
        for item in merged_items[:MAX_RECENT_PRS]:
            repo_name = parse_repo_name(item["repository_url"])
            merged_at = parse_merged_at(item).astimezone(timezone.utc).strftime("%b %d, %Y")
            lines.append(
                f"- [{repo_name}#{item['number']}]({item['html_url']})"
                f" {item['title']} ({merged_at})"
            )
    else:
        lines.append("- No merged open source pull requests found yet.")

    return "\n".join(lines)


def update_readme(block: str) -> bool:
    content = README_PATH.read_text(encoding="utf-8")
    if START_MARKER not in content or END_MARKER not in content:
        raise RuntimeError("OSS stats markers not found in README.md")
    pattern = re.compile(
        rf"{re.escape(START_MARKER)}.*?{re.escape(END_MARKER)}",
        flags=re.DOTALL,
    )
    replacement = f"{START_MARKER}\n{block}\n{END_MARKER}"
    updated = pattern.sub(replacement, content)
    if updated == content:
        return False
    README_PATH.write_text(updated, encoding="utf-8")
    return True


def main() -> int:
    token = github_token()
    items = search_merged_prs(token)
    block = build_stats_block(items)
    changed = update_readme(block)
    print(f"Updated OSS stats block. Changed README: {changed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
