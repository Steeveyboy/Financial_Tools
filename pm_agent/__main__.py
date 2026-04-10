"""
pm_agent/__main__.py

CLI entrypoint for the Project Manager Agent.

Usage:
    python -m pm_agent                     # full run: scan + create issues + project
    python -m pm_agent --dry-run           # preview without touching GitHub
    python -m pm_agent --scan-only         # just print the WBS, no GitHub interaction
    python -m pm_agent --config path.yaml  # use a custom config file
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import yaml

from .github_issues import create_issues, ensure_labels
from .github_projects import ProjectManager
from .scanner import CodebaseScanner
from .wbs import build_wbs, print_wbs, wbs_to_json

_logger = logging.getLogger("pm_agent")

DEFAULT_CONFIG = Path(__file__).parent / "config.yaml"


def main(argv: list[str] | None = None) -> int:
    """Main entrypoint for the PM agent CLI."""
    args = parse_args(argv)
    _setup_logging(args.verbose)

    # Load config
    config = _load_config(args.config)
    repo_owner = config["repo"]["owner"]
    repo_name = config["repo"]["name"]

    # Determine repo root (parent of pm_agent/)
    repo_root = str(Path(__file__).parent.parent.resolve())
    _logger.info("Repository root: %s", repo_root)

    # Phase 1: Scan codebase
    _logger.info("Phase 1: Scanning codebase...")
    scanner = CodebaseScanner(
        repo_root=repo_root,
        scan_dirs=config.get("scan_directories", []),
        scan_extensions=config.get("scan_extensions", [".py"]),
        stub_patterns=config.get("stub_patterns", []),
    )
    scan_result = scanner.scan()

    _logger.info("Scan found: %s", scan_result.summary())

    # Phase 2: Build WBS
    _logger.info("Phase 2: Building Work Breakdown Structure...")
    predefined = config.get("predefined_tasks", [])
    wbs = build_wbs(scan_result, predefined)

    # Print WBS to stdout
    print_wbs(wbs)

    # Write WBS manifest
    wbs_path = Path(repo_root) / "pm_agent" / "wbs.json"
    wbs_to_json(wbs, wbs_path)

    if args.scan_only:
        print("\n--scan-only: stopping before GitHub interaction.")
        return 0

    # Phase 3: GitHub interaction
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        _logger.error(
            "GITHUB_TOKEN environment variable is not set.\n"
            "Set it before running:\n"
            '  export GITHUB_TOKEN="ghp_..."'
        )
        return 1

    _logger.info("Phase 3: Creating GitHub labels and issues...")

    from github import Auth, Github
    from github.GithubException import GithubException

    try:
        gh = Github(auth=Auth.Token(token))
        repo = gh.get_repo(f"{repo_owner}/{repo_name}")
    except GithubException as exc:
        _logger.error(
            "Failed to connect to GitHub repository %s/%s: %s\n"
            "Check that GITHUB_TOKEN is valid and has repo access.",
            repo_owner, repo_name, exc,
        )
        return 1

    # Ensure labels exist
    label_config = config.get("labels", {})
    if not args.dry_run:
        ensure_labels(repo, label_config)
    else:
        _logger.info("[DRY RUN] Would create %d label categories",
                      len(label_config))

    # Create issues
    results = create_issues(repo, wbs, dry_run=args.dry_run)

    # Print results
    _print_issue_results(results)

    # Phase 4: GitHub Project
    project_name = config.get("project_name", "Resonance Desk Roadmap")
    pm = ProjectManager(token, repo_owner, repo_name, project_name)

    if args.dry_run:
        _logger.info("[DRY RUN] Would create/update project '%s'", project_name)
    else:
        project_id = pm.get_or_create_project()
        if project_id:
            issue_numbers = [
                r["number"] for r in results
                if r["number"] is not None
            ]
            pm.add_issues_to_project(project_id, issue_numbers)
        else:
            _logger.warning(
                "Could not create or find project '%s'. "
                "Ensure your GITHUB_TOKEN has 'project' scope.",
                project_name,
            )

    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="pm_agent",
        description="Project Manager Agent — generates WBS, GitHub Issues, and Project boards",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without creating GitHub issues or project",
    )
    parser.add_argument(
        "--scan-only",
        action="store_true",
        help="Scan codebase and print WBS without any GitHub interaction",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=str(DEFAULT_CONFIG),
        help="Path to config YAML file (default: pm_agent/config.yaml)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args(argv)


def _load_config(config_path: str) -> dict:
    """Load YAML config file."""
    path = Path(config_path)
    if not path.exists():
        _logger.error("Config file not found: %s", path)
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    _logger.debug("Loaded config from %s", path)
    return config


def _setup_logging(verbose: bool = False) -> None:
    """Configure logging for the PM agent."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _print_issue_results(results: list[dict]) -> None:
    """Print a summary of issue creation results."""
    print(f"\n{'='*70}")
    print(f"  ISSUE CREATION RESULTS — {len(results)} tasks")
    print(f"{'='*70}\n")

    for r in results:
        status = r["status"]
        if status == "created":
            print(f"  ✅ #{r['number']} — {r['title']}")
            print(f"     {r['url']}")
        elif status == "exists":
            print(f"  ⏭️  #{r['number']} — {r['title']} (already exists)")
        elif status == "dry_run":
            print(f"  🔍 {r['title']} (dry run)")
        else:
            print(f"  ❌ {r['title']} ({status})")
        print()

    created = sum(1 for r in results if r["status"] == "created")
    existing = sum(1 for r in results if r["status"] == "exists")
    errors = sum(1 for r in results if r["status"] == "error")
    print(f"  Summary: {created} created, {existing} already existed, {errors} errors\n")


if __name__ == "__main__":
    sys.exit(main())
