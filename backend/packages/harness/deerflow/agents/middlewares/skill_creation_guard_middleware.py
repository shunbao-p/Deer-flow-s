"""Guard runtime auto-created skill installation within a single thread."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from pathlib import PurePosixPath
from typing import NotRequired, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import SystemMessage, ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from deerflow.agents.thread_state import SkillCreationState, SkillLifecycleState

_INSTALL_SKILL_TOOL = "install_skill"
_EVALUATE_SKILL_CREATION_TOOL = "evaluate_skill_creation"
_EVALUATE_SKILL_LIFECYCLE_TOOL = "evaluate_skill_lifecycle"
_MISSING_TOOL_CALL_ID = "missing_tool_call_id"
_DEFAULT_MAX_AUTO_CREATE_ATTEMPTS = 2
_INSTALL_SUCCESS_RE = re.compile(r"Skill '([^']+)' installed successfully")
_RUNTIME_OUTPUTS_PREFIX = "/mnt/user-data/outputs/runtime-skills/"
_RUNTIME_WORKSPACE_PREFIX = "/mnt/user-data/workspace/runtime-skills/"


class SkillCreationGuardMiddlewareState(AgentState):
    """Compatible with the `ThreadState` schema."""

    skill_creation: NotRequired[SkillCreationState | None]
    skill_lifecycle: NotRequired[SkillLifecycleState | None]


class SkillCreationGuardMiddleware(AgentMiddleware[SkillCreationGuardMiddlewareState]):
    """Track and limit runtime auto-created skill installation per thread.

    Guard scope is intentionally narrow:
    - Only intercept `install_skill` calls
    - Only when the archive path points to runtime-generated locations
      (`/mnt/user-data/outputs` or `/mnt/user-data/workspace`)
    - Allow one retry after failure, but block repeated retries and additional
      runtime-created skill installs once one has succeeded in the thread
    """

    state_schema = SkillCreationGuardMiddlewareState

    def __init__(self, max_auto_create_attempts: int = _DEFAULT_MAX_AUTO_CREATE_ATTEMPTS):
        super().__init__()
        self.max_auto_create_attempts = max_auto_create_attempts

    def _get_guard_state(self, state: SkillCreationGuardMiddlewareState) -> SkillCreationState:
        current = state.get("skill_creation") or {}
        installed = current.get("installed_skill_names") or []
        return {
            "auto_create_attempts": int(current.get("auto_create_attempts") or 0),
            "installed_skill_names": list(installed),
            "last_failure": current.get("last_failure"),
            "last_policy_allowed": current.get("last_policy_allowed"),
            "last_policy_reason": current.get("last_policy_reason"),
        }

    def _get_lifecycle_state(self, state: SkillCreationGuardMiddlewareState) -> SkillLifecycleState:
        current = state.get("skill_lifecycle") or {}
        return {
            "last_check_outcome": current.get("last_check_outcome"),
            "last_reason": current.get("last_reason"),
            "checked_candidate_name": current.get("checked_candidate_name"),
            "primary_skill_name": current.get("primary_skill_name"),
            "primary_skill_path": current.get("primary_skill_path"),
            "primary_skill_enabled": current.get("primary_skill_enabled"),
            "matched_skill_names": list(current.get("matched_skill_names") or []),
            "disable_recommendations": list(current.get("disable_recommendations") or []),
        }

    def _runtime_target_name(self, request: ToolCallRequest) -> str | None:
        args = request.tool_call.get("args", {})
        expected_name = args.get("expected_skill_name")
        if isinstance(expected_name, str) and expected_name.strip():
            return expected_name.strip()

        path = args.get("path")
        if not isinstance(path, str) or not path.strip():
            return None
        return PurePosixPath(path).stem or None

    def _is_runtime_auto_create_install(self, request: ToolCallRequest) -> bool:
        if request.tool_call.get("name") != _INSTALL_SKILL_TOOL:
            return False

        args = request.tool_call.get("args", {})
        path = args.get("path")
        source = args.get("source")
        if not isinstance(path, str):
            return False

        if source == "runtime_auto_create":
            return True

        return path.startswith(_RUNTIME_OUTPUTS_PREFIX) or path.startswith(_RUNTIME_WORKSPACE_PREFIX)

    def _tool_call_id(self, request: ToolCallRequest) -> str:
        return str(request.tool_call.get("id") or _MISSING_TOOL_CALL_ID)

    def _build_block_message(self, request: ToolCallRequest, reason: str) -> Command:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=f"Error: {reason}",
                        tool_call_id=self._tool_call_id(request),
                        name=_INSTALL_SKILL_TOOL,
                        status="error",
                    )
                ]
            }
        )

    def _extract_tool_message(self, result: ToolMessage | Command) -> ToolMessage | None:
        if isinstance(result, ToolMessage):
            return result

        update = result.update or {}
        for message in update.get("messages", []):
            if isinstance(message, ToolMessage):
                return message
        return None

    def _build_updated_state(
        self,
        guard_state: SkillCreationState,
        tool_message: ToolMessage | None,
    ) -> SkillCreationState:
        attempts = int(guard_state.get("auto_create_attempts") or 0) + 1
        installed = list(guard_state.get("installed_skill_names") or [])
        last_failure = guard_state.get("last_failure")

        text = tool_message.text if tool_message is not None else ""
        match = _INSTALL_SUCCESS_RE.search(text)

        if match and not text.startswith("Error:"):
            skill_name = match.group(1)
            if skill_name not in installed:
                installed.append(skill_name)
            last_failure = None
        else:
            last_failure = text or "Error: install_skill did not return a usable result"

        return {
            "auto_create_attempts": attempts,
            "installed_skill_names": installed,
            "last_failure": last_failure,
            "last_policy_allowed": guard_state.get("last_policy_allowed"),
            "last_policy_reason": guard_state.get("last_policy_reason"),
        }

    def _with_skill_creation_update(self, result: ToolMessage | Command, new_state: SkillCreationState) -> Command:
        if isinstance(result, ToolMessage):
            return Command(update={"messages": [result], "skill_creation": new_state})

        update = dict(result.update or {})
        update["skill_creation"] = new_state
        return Command(
            graph=result.graph,
            update=update,
            resume=result.resume,
            goto=result.goto,
        )

    def _handle_runtime_install(
        self,
        state: SkillCreationGuardMiddlewareState,
        request: ToolCallRequest,
        result: ToolMessage | Command,
    ) -> Command:
        current = self._get_guard_state(state)
        new_state = self._build_updated_state(current, self._extract_tool_message(result))
        return self._with_skill_creation_update(result, new_state)

    def _validate_runtime_install_preconditions(self, request: ToolCallRequest) -> Command | None:
        guard_state = self._get_guard_state(request.state)
        installed = guard_state.get("installed_skill_names") or []
        attempts = int(guard_state.get("auto_create_attempts") or 0)
        last_policy_allowed = guard_state.get("last_policy_allowed")
        last_policy_reason = guard_state.get("last_policy_reason")
        lifecycle_state = self._get_lifecycle_state(request.state)
        lifecycle_outcome = lifecycle_state.get("last_check_outcome")
        checked_candidate_name = lifecycle_state.get("checked_candidate_name")
        runtime_target_name = self._runtime_target_name(request)

        if installed:
            names = ", ".join(installed)
            return self._build_block_message(
                request,
                f"Runtime skill auto-creation is blocked because this thread already installed: {names}.",
            )

        if attempts >= self.max_auto_create_attempts:
            return self._build_block_message(
                request,
                "Runtime skill auto-creation retry limit reached for this thread.",
            )

        if lifecycle_outcome != "no_match":
            reason = lifecycle_outcome or "missing_lifecycle_check"
            primary = lifecycle_state.get("primary_skill_name")
            suffix = f" Primary match: {primary}." if primary else ""
            return self._build_block_message(
                request,
                "Runtime skill auto-creation requires a `no_match` result from "
                f"`{_EVALUATE_SKILL_LIFECYCLE_TOOL}` first. Current lifecycle state: {reason}.{suffix}",
            )

        if not checked_candidate_name:
            return self._build_block_message(
                request,
                "Runtime skill auto-creation requires a recorded candidate name from "
                f"`{_EVALUATE_SKILL_LIFECYCLE_TOOL}` before installation.",
            )

        if runtime_target_name and runtime_target_name != checked_candidate_name:
            return self._build_block_message(
                request,
                "Runtime skill auto-creation install target does not match the most recent "
                f"lifecycle-approved candidate. Approved: {checked_candidate_name}; "
                f"attempted: {runtime_target_name}.",
            )

        if last_policy_allowed is not True:
            reason = last_policy_reason or "missing_policy_decision"
            return self._build_block_message(
                request,
                "Runtime skill auto-creation requires an ALLOW result from "
                f"`{_EVALUATE_SKILL_CREATION_TOOL}` first. Current policy state: {reason}.",
            )

        return None

    @override
    def before_model(self, state: SkillCreationGuardMiddlewareState, runtime) -> dict | None: #在模型下一次思考前，给模型注入提醒
        guard_state = self._get_guard_state(state)
        installed = guard_state.get("installed_skill_names") or []
        attempts = int(guard_state.get("auto_create_attempts") or 0)
        last_failure = guard_state.get("last_failure")

        if installed:
            names = ", ".join(installed)
            return {
                "messages": [
                    SystemMessage(
                        content=(
                            "[SKILL CREATION GUARD] This thread already installed a runtime-created "
                            f"skill: {names}. Prefer that skill or normal tools. Do not auto-create "
                            "another skill in this thread."
                        )
                    )
                ]
            }

        if last_failure and attempts >= self.max_auto_create_attempts:
            return {
                "messages": [
                    SystemMessage(
                        content=(
                            "[SKILL CREATION GUARD] Runtime skill creation already failed in this "
                            f"thread {attempts} time(s), which reached the retry limit. Do not call "
                            "`install_skill` again for runtime-generated packages in this thread."
                        )
                    )
                ]
            }

        if last_failure:
            return {
                "messages": [
                    SystemMessage(
                        content=(
                            "[SKILL CREATION GUARD] A previous runtime skill installation failed in "
                            f"this thread: {last_failure}. Retry only if you made a concrete fix; "
                            "otherwise continue with normal tools."
                        )
                    )
                ]
            }

        return None

    @override
    def wrap_tool_call(  #在执行 install_skill 工具时做拦截和状态更新
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command],
    ) -> ToolMessage | Command:
        if not self._is_runtime_auto_create_install(request):
            return handler(request)

        blocked = self._validate_runtime_install_preconditions(request)
        if blocked is not None:
            return blocked

        result = handler(request)
        return self._handle_runtime_install(request.state, request, result)

    @override
    async def awrap_tool_call(  #在执行 install_skill 工具时做拦截和状态更新
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]],
    ) -> ToolMessage | Command:
        if not self._is_runtime_auto_create_install(request):
            return await handler(request)

        blocked = self._validate_runtime_install_preconditions(request)
        if blocked is not None:
            return blocked

        result = await handler(request)
        return self._handle_runtime_install(request.state, request, result)
