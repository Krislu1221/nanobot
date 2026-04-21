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
