from types import SimpleNamespace

import pytest
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from deerflow.agents.middlewares.skill_creation_guard_middleware import SkillCreationGuardMiddleware


def _request(
    *,
    path: str = "/mnt/user-data/outputs/generated.skill",
    source: str = "runtime_auto_create",
    expected_skill_name: str | None = None,
    state: dict | None = None,
    tool_call_id: str = "tc-1",
):
    args = {"path": path, "source": source}
    if expected_skill_name is not None:
        args["expected_skill_name"] = expected_skill_name
    return SimpleNamespace(
        tool_call={
            "name": "install_skill",
            "id": tool_call_id,
            "args": args,
        },
        state=state or {},
        runtime=SimpleNamespace(context={"thread_id": "thread-1"}),
    )


def test_runtime_install_success_records_attempt_and_installed_skill():
    middleware = SkillCreationGuardMiddleware()
    request = _request(
        state={
            "skill_lifecycle": {
                "last_check_outcome": "no_match",
                "last_reason": "no similar custom skill found",
                "checked_candidate_name": "generated",
            },
            "skill_creation": {
                "last_policy_allowed": True,
                "last_policy_reason": "allow_auto_create",
            }
        }
    )
    tool_message = ToolMessage(
        content="Skill 'report-writer' installed successfully",
        tool_call_id="tc-1",
        name="install_skill",
    )

    result = middleware.wrap_tool_call(request, lambda _req: tool_message)

    assert isinstance(result, Command)
    assert result.update["messages"][0] == tool_message
    assert result.update["skill_creation"] == {
        "auto_create_attempts": 1,
        "installed_skill_names": ["report-writer"],
        "last_failure": None,
        "last_policy_allowed": True,
        "last_policy_reason": "allow_auto_create",
    }


def test_runtime_install_failure_records_last_failure():
    middleware = SkillCreationGuardMiddleware()
    request = _request(
        state={
            "skill_lifecycle": {
                "last_check_outcome": "no_match",
                "last_reason": "no similar custom skill found",
                "checked_candidate_name": "generated",
            },
            "skill_creation": {
                "last_policy_allowed": True,
                "last_policy_reason": "allow_auto_create",
            }
        }
    )
    tool_message = ToolMessage(
        content="Error: Invalid skill archive",
        tool_call_id="tc-1",
        name="install_skill",
        status="error",
    )

    result = middleware.wrap_tool_call(request, lambda _req: tool_message)

    assert isinstance(result, Command)
    assert result.update["skill_creation"] == {
        "auto_create_attempts": 1,
        "installed_skill_names": [],
        "last_failure": "Error: Invalid skill archive",
        "last_policy_allowed": True,
        "last_policy_reason": "allow_auto_create",
    }


def test_non_runtime_install_path_bypasses_guard():
    middleware = SkillCreationGuardMiddleware()
    request = _request(path="/mnt/user-data/outputs/from-user.skill", source="manual")
    tool_message = ToolMessage(
        content="Skill 'manual-upload' installed successfully",
        tool_call_id="tc-1",
        name="install_skill",
    )

    result = middleware.wrap_tool_call(request, lambda _req: tool_message)

    assert result is tool_message


def test_runtime_path_is_guarded_even_without_runtime_source():
    middleware = SkillCreationGuardMiddleware()
    request = _request(
        path="/mnt/user-data/outputs/runtime-skills/generated.skill",
        source="manual",
        state={
            "skill_lifecycle": {
                "last_check_outcome": "no_match",
                "last_reason": "no similar custom skill found",
                "checked_candidate_name": "generated",
            },
            "skill_creation": {
                "last_policy_allowed": False,
                "last_policy_reason": "missing_policy_decision",
            }
        },
    )

    result = middleware.wrap_tool_call(request, lambda _req: None)

    assert isinstance(result, Command)
    assert "requires an ALLOW result" in result.update["messages"][0].content


def test_second_runtime_install_is_blocked_after_success():
    middleware = SkillCreationGuardMiddleware()
    request = _request(
        state={
            "skill_lifecycle": {
                "last_check_outcome": "no_match",
                "last_reason": "no similar custom skill found",
                "checked_candidate_name": "generated",
            },
            "skill_creation": {
                "auto_create_attempts": 1,
                "installed_skill_names": ["report-writer"],
                "last_failure": None,
                "last_policy_allowed": True,
                "last_policy_reason": "allow_auto_create",
            }
        }
    )

    called = False

    def _handler(_req):
        nonlocal called
        called = True
        return ToolMessage(content="should not run", tool_call_id="tc-1", name="install_skill")

    result = middleware.wrap_tool_call(request, _handler)

    assert called is False
    assert isinstance(result, Command)
    assert "already installed: report-writer" in result.update["messages"][0].content
    assert result.update["messages"][0].status == "error"


def test_retry_limit_blocks_after_two_failed_attempts():
    middleware = SkillCreationGuardMiddleware(max_auto_create_attempts=2)
    request = _request(
        state={
            "skill_lifecycle": {
                "last_check_outcome": "no_match",
                "last_reason": "no similar custom skill found",
                "checked_candidate_name": "generated",
            },
            "skill_creation": {
                "auto_create_attempts": 2,
                "installed_skill_names": [],
                "last_failure": "Error: Invalid skill archive",
                "last_policy_allowed": True,
                "last_policy_reason": "allow_auto_create",
            }
        }
    )

    result = middleware.wrap_tool_call(request, lambda _req: None)

    assert isinstance(result, Command)
    assert "retry limit reached" in result.update["messages"][0].content
    assert result.update["messages"][0].status == "error"


def test_runtime_install_requires_allowed_policy_decision():
    middleware = SkillCreationGuardMiddleware()
    request = _request(
        state={
            "skill_lifecycle": {
                "last_check_outcome": "no_match",
                "last_reason": "no similar custom skill found",
                "checked_candidate_name": "generated",
            },
            "skill_creation": {
                "auto_create_attempts": 0,
                "installed_skill_names": [],
                "last_failure": None,
                "last_policy_allowed": False,
                "last_policy_reason": "normal_tools_sufficient",
            }
        }
    )

    result = middleware.wrap_tool_call(request, lambda _req: None)

    assert isinstance(result, Command)
    assert "requires an ALLOW result" in result.update["messages"][0].content
    assert "normal_tools_sufficient" in result.update["messages"][0].content


def test_runtime_install_requires_no_match_lifecycle_decision():
    middleware = SkillCreationGuardMiddleware()
    request = _request(
        state={
            "skill_lifecycle": {
                "last_check_outcome": "similar_skill_exists",
                "last_reason": "a similar custom skill already exists",
                "primary_skill_name": "weather-helper",
            },
            "skill_creation": {
                "last_policy_allowed": True,
                "last_policy_reason": "allow_auto_create",
            },
        }
    )

    result = middleware.wrap_tool_call(request, lambda _req: None)

    assert isinstance(result, Command)
    assert "requires a `no_match` result" in result.update["messages"][0].content
    assert "weather-helper" in result.update["messages"][0].content


def test_runtime_install_requires_matching_checked_candidate_name():
    middleware = SkillCreationGuardMiddleware()
    request = _request(
        expected_skill_name="other-skill",
        state={
            "skill_lifecycle": {
                "last_check_outcome": "no_match",
                "last_reason": "no similar custom skill found",
                "checked_candidate_name": "generated",
            },
            "skill_creation": {
                "last_policy_allowed": True,
                "last_policy_reason": "allow_auto_create",
            },
        },
    )

    result = middleware.wrap_tool_call(request, lambda _req: None)

    assert isinstance(result, Command)
    assert "does not match the most recent lifecycle-approved candidate" in result.update["messages"][0].content


def test_before_model_injects_warning_after_failure():
    middleware = SkillCreationGuardMiddleware(max_auto_create_attempts=2)

    update = middleware.before_model(
        {
            "skill_creation": {
                "auto_create_attempts": 1,
                "installed_skill_names": [],
                "last_failure": "Error: Invalid skill archive",
            }
        },
        runtime=SimpleNamespace(context={"thread_id": "thread-1"}),
    )

    assert update is not None
    assert "Retry only if you made a concrete fix" in update["messages"][0].content


def test_before_model_injects_warning_after_successful_install():
    middleware = SkillCreationGuardMiddleware()

    update = middleware.before_model(
        {
            "skill_creation": {
                "auto_create_attempts": 1,
                "installed_skill_names": ["report-writer"],
                "last_failure": None,
            }
        },
        runtime=SimpleNamespace(context={"thread_id": "thread-1"}),
    )

    assert update is not None
    assert "already installed a runtime-created skill" in update["messages"][0].content
    assert "unless the user explicitly redirects you" not in update["messages"][0].content


def test_guard_preserves_existing_command_updates():
    middleware = SkillCreationGuardMiddleware()
    request = _request(
        state={
            "skill_lifecycle": {
                "last_check_outcome": "no_match",
                "last_reason": "no similar custom skill found",
                "checked_candidate_name": "generated",
            },
            "skill_creation": {
                "last_policy_allowed": True,
                "last_policy_reason": "allow_auto_create",
            }
        }
    )
    tool_message = ToolMessage(
        content="Skill 'report-writer' installed successfully",
        tool_call_id="tc-1",
        name="install_skill",
    )
    original = Command(update={"messages": [tool_message], "artifacts": ["/mnt/user-data/outputs/generated.skill"]})

    result = middleware.wrap_tool_call(request, lambda _req: original)

    assert isinstance(result, Command)
    assert result.update["artifacts"] == ["/mnt/user-data/outputs/generated.skill"]
    assert result.update["skill_creation"]["installed_skill_names"] == ["report-writer"]


@pytest.mark.anyio
async def test_async_runtime_install_success_records_state():
    middleware = SkillCreationGuardMiddleware()
    request = _request(
        state={
            "skill_lifecycle": {
                "last_check_outcome": "no_match",
                "last_reason": "no similar custom skill found",
                "checked_candidate_name": "generated",
            },
            "skill_creation": {
                "last_policy_allowed": True,
                "last_policy_reason": "allow_auto_create",
            }
        }
    )
    tool_message = ToolMessage(
        content="Skill 'report-writer' installed successfully",
        tool_call_id="tc-1",
        name="install_skill",
    )

    async def _handler(_req):
        return tool_message

    result = await middleware.awrap_tool_call(request, _handler)

    assert isinstance(result, Command)
    assert result.update["skill_creation"]["auto_create_attempts"] == 1
    assert result.update["skill_creation"]["installed_skill_names"] == ["report-writer"]


@pytest.mark.anyio
async def test_async_runtime_install_requires_no_match_lifecycle_decision():
    middleware = SkillCreationGuardMiddleware()
    request = _request(
        state={
            "skill_lifecycle": {
                "last_check_outcome": "similar_skill_exists",
                "last_reason": "a similar custom skill already exists",
                "checked_candidate_name": "generated",
                "primary_skill_name": "weather-helper",
            },
            "skill_creation": {
                "last_policy_allowed": True,
                "last_policy_reason": "allow_auto_create",
            },
        }
    )

    async def _handler(_req):
        return ToolMessage(
            content="Skill 'should-not-install' installed successfully",
            tool_call_id="tc-1",
            name="install_skill",
        )

    result = await middleware.awrap_tool_call(request, _handler)

    assert isinstance(result, Command)
    assert "requires a `no_match` result" in result.update["messages"][0].content
    assert "weather-helper" in result.update["messages"][0].content


@pytest.mark.anyio
async def test_async_runtime_install_requires_matching_checked_candidate_name():
    middleware = SkillCreationGuardMiddleware()
    request = _request(
        expected_skill_name="other-skill",
        state={
            "skill_lifecycle": {
                "last_check_outcome": "no_match",
                "last_reason": "no similar custom skill found",
                "checked_candidate_name": "generated",
            },
            "skill_creation": {
                "last_policy_allowed": True,
                "last_policy_reason": "allow_auto_create",
            },
        },
    )

    async def _handler(_req):
        return ToolMessage(
            content="Skill 'should-not-install' installed successfully",
            tool_call_id="tc-1",
            name="install_skill",
        )

    result = await middleware.awrap_tool_call(request, _handler)

    assert isinstance(result, Command)
    assert "does not match the most recent lifecycle-approved candidate" in result.update["messages"][0].content
