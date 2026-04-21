from nanobot.config.schema import Config, ModelPresetConfig


def test_model_preset_config_accepts_model_and_provider_separately() -> None:
    preset = ModelPresetConfig(model="gpt-5", provider="openai")
    assert preset.model == "gpt-5"
    assert preset.provider == "openai"


def test_model_preset_config_defaults() -> None:
    preset = ModelPresetConfig(model="test-model")
    assert preset.provider == "auto"
    assert preset.max_tokens == 8192
    assert preset.context_window_tokens == 65_536
    assert preset.temperature == 0.1
    assert preset.reasoning_effort is None


def test_model_preset_config_all_fields() -> None:
    preset = ModelPresetConfig(
        model="deepseek-r1",
        provider="deepseek",
        max_tokens=16384,
        context_window_tokens=131072,
        temperature=0.2,
        reasoning_effort="high",
    )
    assert preset.model == "deepseek-r1"
    assert preset.provider == "deepseek"
    assert preset.max_tokens == 16384
    assert preset.context_window_tokens == 131072
    assert preset.temperature == 0.2
    assert preset.reasoning_effort == "high"


def test_config_accepts_model_presets_dict() -> None:
    cfg = Config(model_presets={
        "gpt5": ModelPresetConfig(model="gpt-5", provider="openai", max_tokens=16384),
        "ds": ModelPresetConfig(model="deepseek-chat", provider="deepseek"),
    })
    assert "gpt5" in cfg.model_presets
    assert cfg.model_presets["gpt5"].max_tokens == 16384
    assert cfg.model_presets["ds"].model == "deepseek-chat"


def test_preset_resolves_model_fields_into_defaults() -> None:
    cfg = Config.model_validate({
        "model_presets": {
            "gpt5": {
                "model": "gpt-5",
                "provider": "openai",
                "max_tokens": 16384,
                "context_window_tokens": 128000,
                "temperature": 0.2,
            },
        },
        "agents": {"defaults": {"model_preset": "gpt5"}},
    })
    d = cfg.agents.defaults
    assert d.model == "gpt-5"
    assert d.provider == "openai"
    assert d.max_tokens == 16384
    assert d.context_window_tokens == 128000
    assert d.temperature == 0.2


def test_preset_overrides_old_config_fields() -> None:
    """If user sets model_preset, preset wins completely — even over old config remnants."""
    cfg = Config.model_validate({
        "model_presets": {
            "gpt5": {
                "model": "gpt-5",
                "provider": "openai",
                "max_tokens": 16384,
                "context_window_tokens": 128000,
                "temperature": 0.2,
            },
        },
        "agents": {
            "defaults": {
                "model_preset": "gpt5",
                "model": "old-model",       # old config remnant — should be overridden
                "temperature": 0.5,          # old config remnant — should be overridden
            },
        },
    })
    d = cfg.agents.defaults
    assert d.model == "gpt-5"           # preset wins, not "old-model"
    assert d.temperature == 0.2          # preset wins, not 0.5
    assert d.max_tokens == 16384         # from preset


def test_preset_not_found_raises_error() -> None:
    import pytest
    with pytest.raises(Exception, match="model_preset.*not found"):
        Config.model_validate({
            "model_presets": {},
            "agents": {"defaults": {"model_preset": "nonexistent"}},
        })


def test_no_preset_means_no_changes() -> None:
    """Backward compat: config without model_preset works exactly as before."""
    cfg = Config.model_validate({
        "agents": {"defaults": {"model": "deepseek-chat"}},
    })
    assert cfg.agents.defaults.model == "deepseek-chat"
    assert cfg.agents.defaults.max_tokens == 8192  # built-in default


def test_preset_with_reasoning_effort() -> None:
    cfg = Config.model_validate({
        "model_presets": {
            "ds-r1": {
                "model": "deepseek-r1",
                "provider": "deepseek",
                "reasoning_effort": "high",
            },
        },
        "agents": {"defaults": {"model_preset": "ds-r1"}},
    })
    assert cfg.agents.defaults.reasoning_effort == "high"
