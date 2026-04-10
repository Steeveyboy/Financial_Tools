"""
pm_agent/github_projects.py

Creates and manages a GitHub Projects (v2) board for organizing WBS issues.

GitHub Projects v2 uses the GraphQL API. This module handles:
  - Creating a project if it doesn't exist
  - Adding issues to the project
  - (Future) organizing columns/status fields

Note: GitHub Projects v2 requires a classic PAT with `project` scope,
or a fine-grained PAT with Projects read/write permission.
"""

from __future__ import annotations

import json
import logging

import requests

_logger = logging.getLogger(__name__)

GITHUB_GRAPHQL_URL = "https://api.github.com/graphql"


class ProjectManager:
    """
    Manages a GitHub Projects v2 board via the GraphQL API.

    Args:
        token:        GitHub PAT with project permissions.
        owner:        Repository owner (user or org).
        repo_name:    Repository name.
        project_name: Name for the project board.
    """

    def __init__(self, token: str, owner: str, repo_name: str, project_name: str):
        self.token = token
        self.owner = owner
        self.repo_name = repo_name
        self.project_name = project_name
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def _graphql(self, query: str, variables: dict | None = None) -> dict:
        """Execute a GraphQL query against the GitHub API."""
        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        resp = requests.post(
            GITHUB_GRAPHQL_URL,
            headers=self.headers,
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        if "errors" in data:
            _logger.error("GraphQL errors: %s", json.dumps(data["errors"], indent=2))
        return data

    def get_or_create_project(self) -> str | None:
        """
        Get the project ID if it exists, or create a new one.

        Returns:
            The project node ID, or None on failure.
        """
        project_id = self._find_existing_project()
        if project_id:
            _logger.info("Found existing project: %s", self.project_name)
            return project_id

        return self._create_project()

    def add_issues_to_project(
        self, project_id: str, issue_numbers: list[int], dry_run: bool = False
    ) -> int:
        """
        Add issues to the project board.

        Args:
            project_id:    The project node ID.
            issue_numbers: List of issue numbers to add.
            dry_run:       If True, log but don't actually add.

        Returns:
            Number of issues successfully added.
        """
        if dry_run:
            _logger.info("[DRY RUN] Would add %d issues to project", len(issue_numbers))
            return 0

        # Get issue node IDs
        repo_id, issue_node_ids = self._get_issue_node_ids(issue_numbers)
        if not issue_node_ids:
            _logger.warning("No issue node IDs found")
            return 0

        added = 0
        for issue_num, node_id in issue_node_ids.items():
            if self._add_item_to_project(project_id, node_id):
                added += 1
                _logger.debug("Added issue #%d to project", issue_num)

        _logger.info("Added %d/%d issues to project", added, len(issue_numbers))
        return added

    def _find_existing_project(self) -> str | None:
        """Search for an existing project by name."""
        query = """
        query($owner: String!, $first: Int!) {
          user(login: $owner) {
            projectsV2(first: $first) {
              nodes {
                id
                title
              }
            }
          }
        }
        """
        variables = {"owner": self.owner, "first": 20}
        data = self._graphql(query, variables)

        # Try user projects first, then org
        projects = (
            data.get("data", {})
            .get("user", {})
            .get("projectsV2", {})
            .get("nodes", [])
        )

        if not projects:
            # Try as organization
            query_org = query.replace("user(login:", "organization(login:")
            query_org = query_org.replace("user {", "organization {")
            data = self._graphql(query_org, variables)
            projects = (
                data.get("data", {})
                .get("organization", {})
                .get("projectsV2", {})
                .get("nodes", [])
            )

        for project in projects:
            if project.get("title") == self.project_name:
                return project["id"]

        return None

    def _create_project(self) -> str | None:
        """Create a new project."""
        # First, get the owner ID
        owner_id = self._get_owner_id()
        if not owner_id:
            _logger.error("Could not find owner ID for %s", self.owner)
            return None

        query = """
        mutation($input: CreateProjectV2Input!) {
          createProjectV2(input: $input) {
            projectV2 {
              id
              title
              url
            }
          }
        }
        """
        variables = {
            "input": {
                "ownerId": owner_id,
                "title": self.project_name,
            }
        }

        data = self._graphql(query, variables)
        project = (
            data.get("data", {})
            .get("createProjectV2", {})
            .get("projectV2")
        )

        if project:
            _logger.info("Created project: %s (%s)", project["title"], project.get("url"))
            return project["id"]

        _logger.error("Failed to create project")
        return None

    def _get_owner_id(self) -> str | None:
        """Get the node ID of the repository owner."""
        query = """
        query($login: String!) {
          user(login: $login) { id }
        }
        """
        data = self._graphql(query, {"login": self.owner})
        user_id = data.get("data", {}).get("user", {}).get("id")
        if user_id:
            return user_id

        # Try as org
        query_org = """
        query($login: String!) {
          organization(login: $login) { id }
        }
        """
        data = self._graphql(query_org, {"login": self.owner})
        return data.get("data", {}).get("organization", {}).get("id")

    def _get_issue_node_ids(
        self, issue_numbers: list[int]
    ) -> tuple[str | None, dict[int, str]]:
        """Get node IDs for a list of issue numbers."""
        query = """
        query($owner: String!, $repo: String!, $number: Int!) {
          repository(owner: $owner, name: $repo) {
            id
            issue(number: $number) {
              id
              number
            }
          }
        }
        """
        repo_id = None
        result: dict[int, str] = {}

        for num in issue_numbers:
            variables = {
                "owner": self.owner,
                "repo": self.repo_name,
                "number": num,
            }
            data = self._graphql(query, variables)
            repo_data = data.get("data", {}).get("repository", {})

            if not repo_id:
                repo_id = repo_data.get("id")

            issue = repo_data.get("issue")
            if issue:
                result[num] = issue["id"]

        return repo_id, result

    def _add_item_to_project(self, project_id: str, content_id: str) -> bool:
        """Add a single item to the project."""
        query = """
        mutation($input: AddProjectV2ItemByIdInput!) {
          addProjectV2ItemById(input: $input) {
            item { id }
          }
        }
        """
        variables = {
            "input": {
                "projectId": project_id,
                "contentId": content_id,
            }
        }

        data = self._graphql(query, variables)
        item = (
            data.get("data", {})
            .get("addProjectV2ItemById", {})
            .get("item")
        )
        return item is not None
