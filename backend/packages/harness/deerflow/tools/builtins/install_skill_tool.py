import logging
from typing import Literal

from langchain.tools import ToolRuntime, tool
from langgraph.typing import ContextT

from deerflow.agents.thread_state import ThreadState
from deerflow.config.paths import VIRTUAL_PATH_PREFIX, get_paths
from deerflow.skills.installer import (
    InvalidSkillArchiveError,
    SkillAlreadyExistsError,
    SkillArchiveNotFoundError,
    install_skill_archive,
)

logger = logging.getLogger(__name__)


@tool("install_skill", parse_docstring=True)
def install_skill_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    path: str,
    source: Literal["manual", "runtime_auto_create"] = "manual",
    expected_skill_name: str | None = None,
) -> str:
    """Install a generated `.skill` archive from the current thread's user-data directory.

    Use this after creating a `.skill` file in the current thread, usually under
    `/mnt/user-data/outputs` or `/mnt/user-data/workspace`.

    Args:
        path: Absolute virtual path to the `.skill` file, such as `/mnt/user-data/outputs/my-skill.skill`.
        source: Installation source marker. Use `runtime_auto_create` only for the runtime
            auto-created skill flow. Otherwise leave it as `manual`.
        expected_skill_name: Optional candidate name already approved by lifecycle checks.
            For runtime auto-create flows, pass the same name that was checked by
            `evaluate_skill_lifecycle`.
    """
    thread_id = runtime.context.get("thread_id") if runtime is not None else None
    if not thread_id:
        return "Error: Thread ID is not available in runtime context"

    normalized_prefix = VIRTUAL_PATH_PREFIX.rstrip("/")
    if path != normalized_prefix and not path.startswith(f"{normalized_prefix}/"):
        return f"Error: Path must start with {VIRTUAL_PATH_PREFIX}"

    try:
        resolved_path = get_paths().resolve_virtual_path(thread_id, path)
        result = install_skill_archive(resolved_path)
        if expected_skill_name and result.skill_name != expected_skill_name:
            return (
                "Error: Installed skill name "
                f"'{result.skill_name}' did not match expected skill '{expected_skill_name}'."
            )
        return result.message
    except (SkillArchiveNotFoundError, InvalidSkillArchiveError, SkillAlreadyExistsError) as exc:
        return f"Error: {exc}"
    except ValueError as exc:
        return f"Error: {exc}"
    except Exception as exc:
        logger.exception("Unexpected failure in install_skill tool for thread %s", thread_id)
        return f"Error: Failed to install skill: {exc}"
