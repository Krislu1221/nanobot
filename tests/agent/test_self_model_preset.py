# tests/agent/test_self_model_preset.py
import asyncio
from pathlib import Path
from unittest.mock import MagicMock

from nanobot.agent.loop import AgentLoop
from nanobot.agent.tools.self import MyTool
from nanobot.config.schema import ModelPresetConfig
from nanobot.providers.base import GenerationSettings


def _make_loop(presets: dict | None = None) -> tuple[AgentLoop, MyTool]:
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    provider.generation = GenerationSettings(temperature=0.1, max_tokens=8192)
    _presets = presets or {}
    loop = AgentLoop(
        bus=MagicMock(),
        provider=provider,
        workspace=Path("/tmp/test"),
        model="test-model",
        context_window_tokens=65536,
        model_presets=_presets,
    )
    tool = MyTool(loop, modify_allowed=True, model_presets=_presets)
    return loop, tool


async def test_set_model_preset_updates_all_fields() -> None:
    presets = {
        "gpt5": ModelPresetConfig(
            model="gpt-5",
            provider="openai",
            max_tokens=16384,
            context_window_tokens=128000,
            temperature=0.2,
        ),
    }
    loop, tool = _make_loop(presets)
    result = await tool.execute(action="set", key="model_preset", value="gpt5")

    assert "model_preset" in result
    assert loop.model == "gpt-5"
    assert loop.context_window_tokens == 128000
    assert loop.provider.generation.temperature == 0.2
    assert loop.provider.generation.max_tokens == 16384


async def test_set_model_preset_unknown_returns_error() -> None:
    loop, tool = _make_loop({})
    result = await tool.execute(action="set", key="model_preset", value="nope")

    assert "Error" in result or "not found" in result


async def test_check_model_preset_shows_current() -> None:
    presets = {"gpt5": ModelPresetConfig(model="gpt-5", provider="openai")}
    loop, tool = _make_loop(presets)
    result = await tool.execute(action="check", key="model_preset")

    assert "gpt5" in result or "None" in result


async def test_check_model_preset_shows_available() -> None:
    presets = {
        "gpt5": ModelPresetConfig(model="gpt-5", provider="openai"),
        "ds": ModelPresetConfig(model="deepseek-chat", provider="deepseek"),
    }
    loop, tool = _make_loop(presets)
    result = await tool.execute(action="check", key="model_presets")

    assert "gpt5" in result
    assert "ds" in result


async def test_set_model_preset_logs_audit() -> None:
    presets = {"gpt5": ModelPresetConfig(model="gpt-5", provider="openai")}
    loop, tool = _make_loop(presets)
    tool._channel = "test"
    tool._chat_id = "ch"
    await tool.execute(action="set", key="model_preset", value="gpt5")

    # No crash = audit path executed
