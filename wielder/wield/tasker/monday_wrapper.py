"""Monday.com API-shaped wrapper.

This class intentionally speaks Monday nomenclature. Wielder-facing tasker
classes adapt this shape into Wielder tasker nomenclature.
"""

from __future__ import annotations

from typing import Any

import requests

from wielder.wield.tasker.tasker import WMondayTaskerConfig


class MondayWrapper:
    def __init__(self, config: WMondayTaskerConfig):
        self.config = config

    def account_context(self) -> dict[str, Any]:
        query = """
        query WhoAmI {
          me {
            id
            name
            email
            account {
              id
              name
              slug
            }
          }
          account {
            id
            name
            slug
          }
        }
        """
        payload = self.post_graphql(query=query, variables={})
        return payload.get("data", {})

    def workspaces(self) -> list[dict[str, Any]]:
        query = """
        query ListWorkspaces($limit: Int!, $page: Int!) {
          workspaces(
            limit: $limit,
            page: $page,
            membership_kind: __MEMBERSHIP_KIND__
          ) {
            id
            name
            kind
            state
            description
          }
        }
        """.replace("__MEMBERSHIP_KIND__", self.config.workspace_membership_kind)
        workspaces: list[dict[str, Any]] = []
        page = 1
        while True:
            payload = self.post_graphql(
                query=query,
                variables={"limit": self.config.workspace_limit, "page": page},
            )
            page_workspaces = payload.get("data", {}).get("workspaces", [])
            workspaces.extend(page_workspaces)
            if len(page_workspaces) < self.config.workspace_limit:
                return workspaces
            page += 1

    def boards(self, *, workspace_ids: list[str] | None = None) -> list[dict[str, Any]]:
        variables: dict[str, Any] = {"limit": self.config.board_limit}
        workspace_ids = workspace_ids or []

        if workspace_ids:
            variables["workspaceIds"] = workspace_ids
            board_selector = "boards(limit: $limit, workspace_ids: $workspaceIds)"
            variable_declaration = "$limit: Int!, $workspaceIds: [ID!]"
        else:
            board_selector = "boards(limit: $limit)"
            variable_declaration = "$limit: Int!"

        query = f"""
        query ListBoards({variable_declaration}) {{
          {board_selector} {{
            id
            name
            board_kind
            state
            workspace {{
              id
              name
            }}
          }}
        }}
        """
        payload = self.post_graphql(query=query, variables=variables)
        return payload.get("data", {}).get("boards", [])

    def board_structures(self, *, board_ids: list[str], item_limit: int) -> list[dict[str, Any]]:
        if not board_ids:
            raise ValueError("Monday board_structures requires at least one board id.")
        if item_limit < 1:
            raise ValueError("Monday board_structures item_limit must be positive.")

        query = """
        query BoardStructures($boardIds: [ID!], $itemLimit: Int!) {
          boards(ids: $boardIds) {
            id
            name
            board_kind
            state
            workspace {
              id
              name
            }
            groups {
              id
              title
            }
            columns {
              id
              title
              type
            }
            items_page(limit: $itemLimit) {
              cursor
              items {
                id
                name
                group {
                  id
                  title
                }
                column_values {
                  id
                  text
                  type
                }
                subitems {
                  id
                  name
                }
              }
            }
          }
        }
        """
        payload = self.post_graphql(
            query=query,
            variables={
                "boardIds": [str(board_id) for board_id in board_ids],
                "itemLimit": int(item_limit),
            },
        )
        return payload.get("data", {}).get("boards", [])

    def post_graphql(self, *, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        token = self.config.require_token()
        response = requests.post(
            self.config.api_url,
            headers={
                "Authorization": token,
                "Content-Type": "application/json",
                "API-Version": self.config.api_version,
            },
            json={"query": query, "variables": variables},
            timeout=self.config.timeout_seconds,
        )
        if response.status_code >= 400:
            raise RuntimeError(
                f"Monday API request failed with status [{response.status_code}]: "
                f"{response.text[:1000]}"
            )

        payload = response.json()
        errors = payload.get("errors")
        if errors:
            raise RuntimeError(f"Monday API returned GraphQL errors: {errors}")
        return payload
