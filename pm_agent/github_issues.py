"""
pm_agent/github_issues.py

Creates GitHub Issues from WBS tasks, with idempotency (won't duplicate).
Also ensures the label taxonomy exists in the repo.
"""

from __future__ import annotations

import logging
from typing import Any

from github import Github
from github.GithubException import GithubException
from github.Repository import Repository

_logger = logging.getLogger(__name__)


def ensure_labels(repo: Repository, label_config: dict[str, list[dict]]) -> None:
    """
    Create all labels from config if they don't already exist.

    Args:
        repo:         PyGithub Repository object.
        label_config: Dict of label categories, each containing a list of
                      {"name": str, "color": str, "description": str}.
    """
    existing = {label.name for label in repo.get_labels()}

    for _category, labels in label_config.items():
        for label_def in labels:
            name = label_def["name"]
            if name in existing:
                _logger.debug("Label already exists: %s", name)
                continue

            try:
                repo.create_label(
                    name=name,
                    color=label_def.get("color", "ededed"),
                    description=label_def.get("description", ""),
                )
                _logger.info("Created label: %s", name)
            except GithubException as exc:
                _logger.error("Failed to create label '%s': %s", name, exc)


def create_issues(
    repo: Repository,
    wbs: list[dict],
    dry_run: bool = False,
) -> list[dict]:
    """
    Create one GitHub Issue per WBS task. Idempotent — skips tasks whose
    title already matches an existing open issue.

    Args:
        repo:    PyGithub Repository object.
        wbs:     List of WBS task dicts.
        dry_run: If True, log what would be created but don't touch GitHub.

    Returns:
        List of dicts with 'title', 'number', 'url', 'status' ('created' or 'exists').
    """
    # Fetch existing open issues for dedup
    existing_titles: dict[str, int] = {}
    for issue in repo.get_issues(state="open"):
        existing_titles[issue.title] = issue.number

    results = []

    for task in wbs:
        title = task["title"]

        if title in existing_titles:
            _logger.info("Issue already exists: #%d — %s", existing_titles[title], title)
            results.append({
                "title": title,
                "number": existing_titles[title],
                "url": f"https://github.com/{repo.full_name}/issues/{existing_titles[title]}",
                "status": "exists",
            })
            continue

        body = _format_issue_body(task)
        labels = task.get("labels", [])

        if dry_run:
            _logger.info("[DRY RUN] Would create issue: %s (labels: %s)", title, labels)
            results.append({
                "title": title,
                "number": None,
                "url": None,
                "status": "dry_run",
            })
            continue

        try:
            issue = repo.create_issue(
                title=title,
                body=body,
                labels=labels,
            )
            _logger.info("Created issue #%d: %s", issue.number, title)
            results.append({
                "title": title,
                "number": issue.number,
                "url": issue.html_url,
                "status": "created",
            })
            # Update dedup map so later tasks can reference this one
            existing_titles[title] = issue.number
        except GithubException as exc:
            _logger.error("Failed to create issue '%s': %s", title, exc)
            results.append({
                "title": title,
                "number": None,
                "url": None,
                "status": "error",
            })

    # Now add dependency cross-references
    if not dry_run:
        _add_dependency_references(repo, wbs, results, existing_titles)

    return results


def _format_issue_body(task: dict) -> str:
    """Format a WBS task dict into a GitHub Issue markdown body."""
    sections = []

    # Summary
    if task.get("summary"):
        sections.append(f"## Summary\n\n{task['summary']}")

    # WBS Context
    deps = task.get("dependencies", [])
    deps_str = ", ".join(f'"{d}"' for d in deps) if deps else "None"
    sections.append(
        f"## WBS Context\n\n"
        f"- **Source:** {task.get('source', 'predefined')}\n"
        f"- **Dependencies:** {deps_str}\n"
        f"- **Files:** {', '.join(f'`{f}`' for f in task.get('files', [])) or 'N/A'}"
    )

    # Approach
    if task.get("approach"):
        sections.append(f"## Approach Options\n\n{task['approach']}")

    # Acceptance Criteria
    criteria = task.get("acceptance_criteria", [])
    if criteria:
        items = "\n".join(f"- [ ] {c}" for c in criteria)
        sections.append(f"## Acceptance Criteria\n\n{items}")

    # Agent Instructions
    agent_parts = []
    if task.get("files"):
        files_str = "\n".join(f"- `{f}`" for f in task["files"])
        agent_parts.append(f"### Files to Edit\n{files_str}")
    if task.get("interface"):
        agent_parts.append(f"### Interface Contract\n```\n{task['interface'].strip()}\n```")
    if task.get("test_file"):
        agent_parts.append(f"### Tests to Write\n`{task['test_file']}`")
    if task.get("dependencies_text"):
        agent_parts.append(f"### Dependencies\n{task['dependencies_text']}")

    if agent_parts:
        sections.append("## Agent Instructions\n\n" + "\n\n".join(agent_parts))

    return "\n\n".join(sections)


def _add_dependency_references(
    repo: Repository,
    wbs: list[dict],
    results: list[dict],
    title_to_number: dict[str, int],
) -> None:
    """Add cross-reference comments to issues that have dependencies."""
    for task, result in zip(wbs, results):
        deps = task.get("dependencies", [])
        if not deps or result["number"] is None:
            continue

        dep_refs = []
        for dep_title in deps:
            dep_num = title_to_number.get(dep_title)
            if dep_num:
                dep_refs.append(f"- Depends on #{dep_num} — {dep_title}")

        if dep_refs:
            comment = "## Dependencies\n\n" + "\n".join(dep_refs)
            try:
                issue = repo.get_issue(result["number"])
                issue.create_comment(comment)
            except GithubException as exc:
                _logger.warning(
                    "Could not add dependency comment to #%d: %s",
                    result["number"], exc,
                )
