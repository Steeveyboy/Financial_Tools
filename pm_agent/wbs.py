"""
pm_agent/wbs.py

Builds a structured Work Breakdown Structure (WBS) from scan results
and predefined tasks in the config.

The WBS is a list of task dicts, each containing:
  - title, summary, files, approach, acceptance_criteria
  - labels (for GitHub issue creation)
  - dependencies (titles of tasks that must be done first)
  - source: "predefined" or "scan"
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .scanner import ScanResult

_logger = logging.getLogger(__name__)


def build_wbs(
    scan_result: ScanResult,
    predefined_tasks: list[dict],
) -> list[dict]:
    """
    Combine predefined tasks with scan-discovered findings into a WBS.

    Predefined tasks are always included. Scan findings are deduplicated
    against predefined tasks by checking if the finding's file is already
    covered by a predefined task.

    Args:
        scan_result:      Results from CodebaseScanner.scan()
        predefined_tasks: Task dicts from config.yaml

    Returns:
        List of WBS task dicts ready for issue creation.
    """
    wbs: list[dict] = []

    # Add predefined tasks first
    for task in predefined_tasks:
        wbs.append({
            "title": task["title"],
            "summary": task.get("summary", "").strip(),
            "files": task.get("files", []),
            "approach": task.get("approach", "").strip(),
            "acceptance_criteria": task.get("acceptance_criteria", []),
            "interface": task.get("interface", ""),
            "test_file": task.get("test_file", ""),
            "dependencies_text": task.get("dependencies_text", ""),
            "labels": task.get("labels", []),
            "dependencies": task.get("dependencies", []),
            "source": "predefined",
        })

    # Collect files already covered by predefined tasks
    covered_files: set[str] = set()
    for task in wbs:
        covered_files.update(task["files"])

    # Add scan-discovered TODOs that aren't covered by predefined tasks
    for finding in scan_result.todos:
        if finding.file in covered_files:
            continue

        title = _title_from_todo(finding.text, finding.file)

        # Skip if a predefined task already has a very similar title
        if any(_titles_match(title, t["title"]) for t in wbs):
            continue

        wbs.append({
            "title": title,
            "summary": f"Found at `{finding.file}:{finding.line}`:\n```\n{finding.text}\n```",
            "files": [finding.file],
            "approach": "",
            "acceptance_criteria": [
                f"TODO at {finding.file}:{finding.line} is resolved",
                "All existing tests still pass",
            ],
            "interface": "",
            "test_file": "",
            "dependencies_text": "",
            "labels": _labels_from_module(finding.module),
            "dependencies": [],
            "source": "scan",
        })
        covered_files.add(finding.file)

    _logger.info("WBS built: %d tasks (%d predefined, %d from scan)",
                  len(wbs),
                  len(predefined_tasks),
                  len(wbs) - len(predefined_tasks))

    return wbs


def wbs_to_json(wbs: list[dict], output_path: str | Path) -> None:
    """Write the WBS to a JSON file."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(wbs, f, indent=2, default=str)
    _logger.info("WBS written to %s", path)


def print_wbs(wbs: list[dict]) -> None:
    """Print the WBS to stdout in a human-readable format."""
    print(f"\n{'='*70}")
    print(f"  WORK BREAKDOWN STRUCTURE — {len(wbs)} tasks")
    print(f"{'='*70}\n")

    for i, task in enumerate(wbs, start=1):
        labels_str = ", ".join(task["labels"]) if task["labels"] else "none"
        deps_str = ", ".join(task["dependencies"]) if task["dependencies"] else "none"
        print(f"  [{i}] {task['title']}")
        print(f"      Source: {task['source']} | Labels: {labels_str}")
        if task["dependencies"]:
            print(f"      Dependencies: {deps_str}")
        print(f"      Files: {', '.join(task['files']) or 'N/A'}")
        print()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _title_from_todo(text: str, filepath: str) -> str:
    """Generate a short issue title from a raw comment line."""
    # Remove leading comment markers and task prefixes
    cleaned = text.lstrip("#").strip()
    for prefix in ("TODO:", "TODO", "todo:", "todo"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()

    if len(cleaned) > 80:
        cleaned = cleaned[:77] + "..."

    # If the cleaned text is too short, use the filename
    if len(cleaned) < 10:
        filename = Path(filepath).stem
        return f"Resolve TODO in {filename}"

    return cleaned


def _titles_match(a: str, b: str) -> bool:
    """Check if two titles are similar enough to be considered duplicates."""
    return a.lower().strip() == b.lower().strip()


def _labels_from_module(module: str) -> list[str]:
    """Infer labels from the module name."""
    labels = ["agent:coding", "priority:medium"]

    module_lower = module.lower()
    if "transform" in module_lower:
        labels.append("wbs:transformation")
    elif "extract" in module_lower:
        labels.append("wbs:extraction")
    elif "db" in module_lower or "schema" in module_lower:
        labels.append("wbs:schema")
    else:
        labels.append("wbs:infrastructure")

    return labels
