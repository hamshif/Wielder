"""Monday.com task manager implementation for the Wielder tasker contract."""

from __future__ import annotations

from typing import Any

from wielder.wield.tasker.tasker import WTaskBoard, WTaskSpace, WTasker, WTaskerProvider
from wielder.wield.tasker.monday_wrapper import MondayWrapper


class WMondayTasker(WTasker):
    provider = WTaskerProvider.MONDAY

    def __init__(self, spec):
        super().__init__(spec)
        self.monday = MondayWrapper(spec.monday)

    def monday_account_context(self) -> dict[str, Any]:
        return self.monday.account_context()

    def monday_workspaces(self) -> list[dict[str, Any]]:
        return self.monday.workspaces()

    def monday_boards(self, *, workspace_ids: list[str] | None = None) -> list[dict[str, Any]]:
        return self.monday.boards(workspace_ids=workspace_ids)

    def tasker_context(self) -> dict[str, Any]:
        return self.monday_account_context()

    def list_task_spaces(self) -> list[WTaskSpace]:
        return [
            self._task_space_from_monday_workspace(workspace)
            for workspace in self.monday_workspaces()
        ]

    def list_task_space_boards(self, task_space_name: str) -> list[WTaskBoard]:
        task_space = self._resolve_task_space_by_name(task_space_name)
        return [
            self._task_board_from_monday_board(board)
            for board in self.monday_boards(workspace_ids=[task_space.id])
        ]

    def _resolve_task_space_by_name(self, task_space_name: str) -> WTaskSpace:
        clean_name = task_space_name.strip()
        if not clean_name:
            raise ValueError("task_space_name must not be empty.")
        task_spaces = self.list_task_spaces()
        matches = [
            task_space
            for task_space in task_spaces
            if task_space.name.casefold() == clean_name.casefold()
        ]
        if not matches:
            available_names = [task_space.name for task_space in task_spaces]
            raise ValueError(
                f"Wielder task space [{task_space_name}] was not found. "
                f"Monday workspace names visible to this token: {available_names}"
            )
        if len(matches) > 1:
            ids = [task_space.id for task_space in matches]
            raise ValueError(
                f"Wielder task space name [{task_space_name}] is ambiguous. "
                f"Matching Monday workspace ids: {ids}"
            )
        return matches[0]

    @staticmethod
    def _task_board_from_monday_board(board: dict[str, Any]) -> WTaskBoard:
        workspace = board.get("workspace") or {}
        return WTaskBoard(
            id=str(board["id"]),
            name=str(board["name"]),
            task_space_id=str(workspace["id"]) if workspace.get("id") else None,
            task_space_name=str(workspace["name"]) if workspace.get("name") else None,
            raw=dict(board),
        )

    @staticmethod
    def _task_space_from_monday_workspace(workspace: dict[str, Any]) -> WTaskSpace:
        return WTaskSpace(
            id=str(workspace["id"]),
            name=str(workspace["name"]),
            raw=dict(workspace),
        )
