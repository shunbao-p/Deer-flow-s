from deerflow.config.extensions_config import ExtensionsConfig, SkillStateConfig


def test_get_skill_key_uses_category_prefix():
    assert ExtensionsConfig.get_skill_key("weather-helper", "custom") == "custom:weather-helper"


def test_is_skill_enabled_prefers_category_key_for_custom():
    config = ExtensionsConfig(
        mcp_servers={},
        skills={
            "weather-helper": SkillStateConfig(enabled=True),
            "custom:weather-helper": SkillStateConfig(enabled=False),
        },
    )

    assert config.is_skill_enabled("weather-helper", "custom") is False


def test_is_skill_enabled_keeps_legacy_public_fallback():
    config = ExtensionsConfig(
        mcp_servers={},
        skills={
            "weather-helper": SkillStateConfig(enabled=False),
        },
    )

    assert config.is_skill_enabled("weather-helper", "public") is False
    assert config.is_skill_enabled("weather-helper", "custom") is True
