"""Render Monday-native structure as Wielder documentation graphs."""

from __future__ import annotations

from typing import Any

from wielder.wield.visualizer import WDocGraph


class MondayStructureVisualizer:
    def graph_from_board_structure(self, board: dict[str, Any]) -> WDocGraph:
        board_id = str(board["id"])
        board_name = str(board["name"])
        graph = WDocGraph(id=f"monday_board_{board_id}", label=f"Monday board: {board_name}")

        workspace = board.get("workspace") or {}
        workspace_id = str(workspace.get("id") or "unknown_workspace")
        workspace_node = graph.add_node(
            f"workspace:{workspace_id}",
            label=str(workspace.get("name") or "Unknown workspace"),
            kind="monday.workspace",
            raw=dict(workspace),
        )
        board_node = graph.add_node(
            f"board:{board_id}",
            label=board_name,
            kind=f"monday.board:{board.get('board_kind', 'unknown')}",
            raw=dict(board),
        )
        graph.add_edge(workspace_node, board_node, label="contains board")

        columns_root = graph.add_node(
            f"board:{board_id}:columns",
            label="Columns",
            kind="monday.columns",
        )
        graph.add_edge(board_node, columns_root, label="has columns")
        for column in board.get("columns") or []:
            column_node = graph.add_node(
                f"column:{board_id}:{column['id']}",
                label=f"{column.get('title', column['id'])} ({column.get('type', 'unknown')})",
                kind="monday.column",
                raw=dict(column),
            )
            graph.add_edge(columns_root, column_node, label="defines")

        group_nodes: dict[str, str] = {}
        for group in board.get("groups") or []:
            group_node = graph.add_node(
                f"group:{board_id}:{group['id']}",
                label=str(group.get("title") or group["id"]),
                kind="monday.group",
                raw=dict(group),
            )
            graph.add_edge(board_node, group_node, label="has group")
            group_nodes[str(group["id"])] = group_node

        items_page = board.get("items_page") or {}
        for item in items_page.get("items") or []:
            group = item.get("group") or {}
            group_id = str(group.get("id") or "")
            parent_node = group_nodes.get(group_id, board_node)
            item_node = graph.add_node(
                f"item:{item['id']}",
                label=self._item_label(item),
                kind="monday.item",
                raw=dict(item),
            )
            graph.add_edge(parent_node, item_node, label="contains item")

            for subitem in item.get("subitems") or []:
                subitem_node = graph.add_node(
                    f"subitem:{subitem['id']}",
                    label=str(subitem.get("name") or subitem["id"]),
                    kind="monday.subitem",
                    raw=dict(subitem),
                )
                graph.add_edge(item_node, subitem_node, label="has subitem")

        return graph

    @staticmethod
    def _item_label(item: dict[str, Any]) -> str:
        status = ""
        owner = ""
        for column_value in item.get("column_values") or []:
            if column_value.get("id") == "status" and column_value.get("text"):
                status = str(column_value["text"])
            if column_value.get("id") == "person" and column_value.get("text"):
                owner = str(column_value["text"])
        suffix_parts = [part for part in [status, owner] if part]
        if not suffix_parts:
            return str(item.get("name") or item["id"])
        return f"{item.get('name') or item['id']} ({' / '.join(suffix_parts)})"
