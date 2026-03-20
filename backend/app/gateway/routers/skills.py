import json
import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.gateway.path_utils import resolve_thread_virtual_path
from deerflow.config.extensions_config import ExtensionsConfig, SkillStateConfig, get_extensions_config, reload_extensions_config
from deerflow.skills import Skill, load_skills
from deerflow.skills.installer import (
    InvalidSkillArchiveError,
    SkillAlreadyExistsError,
    SkillArchiveNotFoundError,
    install_skill_archive,
)

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api", tags=["skills"])


class SkillResponse(BaseModel):
    """Response model for skill information."""

    name: str = Field(..., description="Name of the skill")
    description: str = Field(..., description="Description of what the skill does")
    license: str | None = Field(None, description="License information")
    category: str = Field(..., description="Category of the skill (public or custom)")
    enabled: bool = Field(default=True, description="Whether this skill is enabled")


class SkillsListResponse(BaseModel):
    """Response model for listing all skills."""

    skills: list[SkillResponse]


class SkillUpdateRequest(BaseModel):
    """Request model for updating a skill."""

    enabled: bool = Field(..., description="Whether to enable or disable the skill")


class SkillInstallRequest(BaseModel):
    """Request model for installing a skill from a .skill file."""

    thread_id: str = Field(..., description="The thread ID where the .skill file is located")
    path: str = Field(..., description="Virtual path to the .skill file (e.g., mnt/user-data/outputs/my-skill.skill)")


class SkillInstallResponse(BaseModel):
    """Response model for skill installation."""

    success: bool = Field(..., description="Whether the installation was successful")
    skill_name: str = Field(..., description="Name of the installed skill")
    message: str = Field(..., description="Installation result message")


def _skill_to_response(skill: Skill) -> SkillResponse:
    """Convert a Skill object to a SkillResponse."""
    return SkillResponse(
        name=skill.name,
        description=skill.description,
        license=skill.license,
        category=skill.category,
        enabled=skill.enabled,
    )


def _find_skill(skills: list[Skill], skill_name: str, category: str | None = None) -> Skill | None:
    if category is None:
        matches = [skill for skill in skills if skill.name == skill_name]
    else:
        matches = [skill for skill in skills if skill.name == skill_name and skill.category == category]

    if not matches:
        return None
    if category is None and len(matches) > 1:
        categories = ", ".join(sorted({skill.category for skill in matches}))
        raise HTTPException(
            status_code=409,
            detail=(
                f"Skill '{skill_name}' is ambiguous across categories: {categories}. "
                "Specify the category query parameter."
            ),
        )
    return matches[0]


@router.get(
    "/skills",
    response_model=SkillsListResponse,
    summary="List All Skills",
    description="Retrieve a list of all available skills from both public and custom directories.",
)
async def list_skills() -> SkillsListResponse:
    """List all available skills.

    Returns all skills regardless of their enabled status.

    Returns:
        A list of all skills with their metadata.

    Example Response:
        ```json
        {
            "skills": [
                {
                    "name": "PDF Processing",
                    "description": "Extract and analyze PDF content",
                    "license": "MIT",
                    "category": "public",
                    "enabled": true
                },
                {
                    "name": "Frontend Design",
                    "description": "Generate frontend designs and components",
                    "license": null,
                    "category": "custom",
                    "enabled": false
                }
            ]
        }
        ```
    """
    try:
        # Load all skills (including disabled ones)
        skills = load_skills(enabled_only=False)
        return SkillsListResponse(skills=[_skill_to_response(skill) for skill in skills])
    except Exception as e:
        logger.error(f"Failed to load skills: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to load skills: {str(e)}")


@router.get(
    "/skills/{skill_name}",
    response_model=SkillResponse,
    summary="Get Skill Details",
    description="Retrieve detailed information about a specific skill by its name.",
)
async def get_skill(
    skill_name: str,
    category: Annotated[str | None, Query(description="Optional category to disambiguate same-name skills")] = None,
) -> SkillResponse:
    """Get a specific skill by name.

    Args:
        skill_name: The name of the skill to retrieve.

    Returns:
        Skill information if found.

    Raises:
        HTTPException: 404 if skill not found.

    Example Response:
        ```json
        {
            "name": "PDF Processing",
            "description": "Extract and analyze PDF content",
            "license": "MIT",
            "category": "public",
            "enabled": true
        }
        ```
    """
    try:
        skills = load_skills(enabled_only=False)
        skill = _find_skill(skills, skill_name, category)

        if skill is None:
            raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")

        return _skill_to_response(skill)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get skill {skill_name}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get skill: {str(e)}")


@router.put(
    "/skills/{skill_name}",
    response_model=SkillResponse,
    summary="Update Skill",
    description="Update a skill's enabled status by modifying the extensions_config.json file.",
)
async def update_skill(
    skill_name: str,
    request: SkillUpdateRequest,
    category: Annotated[str | None, Query(description="Optional category to disambiguate same-name skills")] = None,
) -> SkillResponse:
    """Update a skill's enabled status.

    This will modify the extensions_config.json file to update the enabled state.
    The SKILL.md file itself is not modified.

    Args:
        skill_name: The name of the skill to update.
        request: The update request containing the new enabled status.

    Returns:
        The updated skill information.

    Raises:
        HTTPException: 404 if skill not found, 500 if update fails.

    Example Request:
        ```json
        {
            "enabled": false
        }
        ```

    Example Response:
        ```json
        {
            "name": "PDF Processing",
            "description": "Extract and analyze PDF content",
            "license": "MIT",
            "category": "public",
            "enabled": false
        }
        ```
    """
    try:
        # Find the skill to verify it exists
        skills = load_skills(enabled_only=False)
        skill = _find_skill(skills, skill_name, category)

        if skill is None:
            raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")

        # Get or create config path
        config_path = ExtensionsConfig.resolve_config_path()
        if config_path is None:
            # Create new config file in parent directory (project root)
            config_path = Path.cwd().parent / "extensions_config.json"
            logger.info(f"No existing extensions config found. Creating new config at: {config_path}")

        # Load current configuration
        extensions_config = get_extensions_config()

        # Update the skill's enabled status
        skill_key = ExtensionsConfig.get_skill_key(skill.name, skill.category)
        extensions_config.skills[skill_key] = SkillStateConfig(enabled=request.enabled)

        # Convert to JSON format (preserve MCP servers config)
        config_data = {
            "mcpServers": {name: server.model_dump() for name, server in extensions_config.mcp_servers.items()},
            "skills": {name: {"enabled": skill_config.enabled} for name, skill_config in extensions_config.skills.items()},
        }

        # Write the configuration to file
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2)

        logger.info(f"Skills configuration updated and saved to: {config_path}")

        # Reload the extensions config to update the global cache
        reload_extensions_config()

        # Reload the skills to get the updated status (for API response)
        skills = load_skills(enabled_only=False)
        updated_skill = _find_skill(skills, skill_name, skill.category)

        if updated_skill is None:
            raise HTTPException(status_code=500, detail=f"Failed to reload skill '{skill_name}' after update")

        logger.info(f"Skill '{skill_name}' enabled status updated to {request.enabled}")
        return _skill_to_response(updated_skill)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update skill {skill_name}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update skill: {str(e)}")


@router.post(
    "/skills/install",
    response_model=SkillInstallResponse,
    summary="Install Skill",
    description="Install a skill from a .skill file (ZIP archive) located in the thread's user-data directory.",
)
async def install_skill(request: SkillInstallRequest) -> SkillInstallResponse:
    """Install a skill from a .skill file.

    The .skill file is a ZIP archive containing a skill directory with SKILL.md
    and optional resources (scripts, references, assets).

    Args:
        request: The install request containing thread_id and virtual path to .skill file.

    Returns:
        Installation result with skill name and status message.

    Raises:
        HTTPException:
            - 400 if path is invalid or file is not a valid .skill file
            - 403 if access denied (path traversal detected)
            - 404 if file not found
            - 409 if skill already exists
            - 500 if installation fails

    Example Request:
        ```json
        {
            "thread_id": "abc123-def456",
            "path": "/mnt/user-data/outputs/my-skill.skill"
        }
        ```

    Example Response:
        ```json
        {
            "success": true,
            "skill_name": "my-skill",
            "message": "Skill 'my-skill' installed successfully"
        }
        ```
    """
    try:
        # Resolve the virtual path to actual file path
        skill_file_path = resolve_thread_virtual_path(request.thread_id, request.path)
        result = install_skill_archive(skill_file_path)
        logger.info("Skill '%s' installed successfully from %s", result.skill_name, request.path)
        return SkillInstallResponse(success=True, skill_name=result.skill_name, message=result.message)

    except HTTPException:
        raise
    except SkillArchiveNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidSkillArchiveError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except SkillAlreadyExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to install skill: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to install skill: {str(e)}")
