from deerflow.config.app_config import AppConfig
from deerflow.config.skills_config import SkillsConfig


def test_skills_config_defaults_auto_create_enabled():
    assert SkillsConfig().auto_create_enabled is True


def test_app_config_accepts_skills_auto_create_flag():
    app_config = AppConfig.model_validate(
        {
            "sandbox": {"use": "deerflow.sandbox.local:LocalSandboxProvider"},
            "skills": {
                "container_path": "/mnt/skills",
                "auto_create_enabled": False,
            },
        }
    )

    assert app_config.skills.auto_create_enabled is False
