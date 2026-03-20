from __future__ import annotations

import logging

from langchain.tools import ToolRuntime, tool
from langgraph.typing import ContextT

from deerflow.agents.thread_state import ThreadState
from deerflow.config.paths import VIRTUAL_PATH_PREFIX, get_paths
from deerflow.skills.updater import (
    InvalidSkillUpdateError,
    SkillUpdateNameMismatchError,
    SkillUpdateSourceNotFoundError,
    SkillUpdateTargetNotFoundError,
    update_custom_skill_from_directory,
)

logger = logging.getLogger(__name__)


@tool("update_custom_skill", parse_docstring=True)
def update_custom_skill_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    skill_name: str,
    path: str,
) -> str:
    """用当前线程工作区里的草稿目录原地更新已有 custom skill。

    典型流程是先读取已有 custom skill，然后在 `/mnt/user-data/workspace`
    中整理出修改后的 skill 目录，最后再通过本工具写回 `skills/custom`。

    Args:
        skill_name: 需要被原地修改的 custom skill 名称。
        path: 草稿 skill 目录的虚拟路径，必须位于当前线程的 `/mnt/user-data` 下。
    """
    thread_id = runtime.context.get("thread_id") if runtime is not None else None
    if not thread_id:
        return "Error: Thread ID is not available in runtime context"

    normalized_prefix = VIRTUAL_PATH_PREFIX.rstrip("/")
    if path != normalized_prefix and not path.startswith(f"{normalized_prefix}/"):
        return f"Error: Path must start with {VIRTUAL_PATH_PREFIX}"

    try:
        resolved_path = get_paths().resolve_virtual_path(thread_id, path)
        result = update_custom_skill_from_directory(skill_name, resolved_path)
        return result.message
    except (
        SkillUpdateSourceNotFoundError,
        SkillUpdateTargetNotFoundError,
        InvalidSkillUpdateError,
        SkillUpdateNameMismatchError,
    ) as exc:
        return f"Error: {exc}"
    except ValueError as exc:
        return f"Error: {exc}"
    except Exception as exc:
        logger.exception("Unexpected failure in update_custom_skill tool for thread %s", thread_id)
        return f"Error: Failed to update custom skill: {exc}"
