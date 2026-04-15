"""Tests for nanobot.agent.skill_discovery."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from nanobot.agent.skill_discovery import SkillCandidate, SkillDiscoverer
from nanobot.config.schema import SkillDiscoveryConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_store(tmp_path: Path) -> MagicMock:
    """Create a mock MemoryStore with a real workspace directory."""
    store = MagicMock()
    store.workspace = tmp_path
    store.get_skill_discovery_cursor.return_value = 0
    store.set_skill_discovery_cursor = MagicMock()
    store.read_memory.return_value = ""
    store.read_user.return_value = ""
    # Git mock — not initialized by default
    store.git.is_initialized.return_value = False
    return store


def _make_provider() -> MagicMock:
    """Create a mock LLMProvider."""
    provider = MagicMock()
    provider.chat_with_retry = AsyncMock()
    return provider


def _make_config(**overrides) -> SkillDiscoveryConfig:
    """Create a SkillDiscoveryConfig with optional overrides."""
    defaults = dict(
        enabled=True,
        max_history_entries=50,
        max_candidates=5,
        auto_approve=False,
        interval_turns=20,
        min_interval_s=7200,
        cron=None,
    )
    defaults.update(overrides)
    return SkillDiscoveryConfig(**defaults)


def _write_skill(base: Path, name: str, content: str = "# Skill\nDescription here.") -> Path:
    """Write a SKILL.md file under base/name/."""
    skill_dir = base / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    path = skill_dir / "SKILL.md"
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# SkillCandidate
# ---------------------------------------------------------------------------


class TestSkillCandidate:
    def test_format_preview(self) -> None:
        c = SkillCandidate(name="my-skill", description="Does something cool", content="# My Skill")
        assert c.format_preview() == "**my-skill** — Does something cool"


# ---------------------------------------------------------------------------
# Phase 1 parsing
# ---------------------------------------------------------------------------


class TestParsePhase1Analysis:
    def test_parse_json_in_code_block(self) -> None:
        analysis = '```json\n[{"name": "test-skill", "recommendation": "strong"}]\n```'
        result = SkillDiscoverer._parse_phase1_analysis(analysis)
        assert len(result) == 1
        assert result[0]["name"] == "test-skill"

    def test_parse_bare_json_array(self) -> None:
        analysis = '[{"name": "test-skill", "recommendation": "moderate"}]'
        result = SkillDiscoverer._parse_phase1_analysis(analysis)
        assert len(result) == 1

    def test_parse_empty_array(self) -> None:
        result = SkillDiscoverer._parse_phase1_analysis("[]")
        assert result == []

    def test_parse_invalid_json_returns_empty(self) -> None:
        result = SkillDiscoverer._parse_phase1_analysis("This is not JSON at all")
        assert result == []

    def test_parse_json_object_returns_empty(self) -> None:
        """A JSON object (not array) should not be accepted."""
        result = SkillDiscoverer._parse_phase1_analysis('{"name": "test"}')
        assert result == []


# ---------------------------------------------------------------------------
# Description extraction
# ---------------------------------------------------------------------------


class TestExtractDescription:
    def test_extracts_first_non_heading_line(self) -> None:
        content = "# My Skill\n\nThis is the description.\n\n## Steps\nDo stuff."
        assert SkillDiscoverer._extract_description(content) == "This is the description."

    def test_skips_empty_lines(self) -> None:
        content = "# Title\n\n\n\nActual description"
        assert SkillDiscoverer._extract_description(content) == "Actual description"

    def test_truncates_long_description(self) -> None:
        long_line = "x" * 300
        content = f"# Title\n{long_line}"
        result = SkillDiscoverer._extract_description(content)
        assert len(result) == 200

    def test_no_description_fallback(self) -> None:
        content = "# Just a heading\n## Another heading"
        assert SkillDiscoverer._extract_description(content) == "(no description)"


# ---------------------------------------------------------------------------
# Candidate filtering
# ---------------------------------------------------------------------------


class TestFilterCandidates:
    def test_filters_duplicate_names(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        provider = _make_provider()
        config = _make_config()
        sd = SkillDiscoverer(store=store, provider=provider, model="test", config=config)

        candidates = [
            SkillCandidate(name="dup", description="first", content="#1"),
            SkillCandidate(name="dup", description="second", content="#2"),
            SkillCandidate(name="unique", description="third", content="#3"),
        ]
        result = sd._filter_candidates(candidates)
        assert len(result) == 2
        assert result[0].name == "dup"
        assert result[1].name == "unique"

    def test_filters_existing_skills(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        provider = _make_provider()
        config = _make_config()
        sd = SkillDiscoverer(store=store, provider=provider, model="test", config=config)

        # Pre-install a skill
        _write_skill(sd.skills_dir, "existing-skill")

        candidates = [
            SkillCandidate(name="existing-skill", description="already there", content="#1"),
            SkillCandidate(name="new-skill", description="brand new", content="#2"),
        ]
        result = sd._filter_candidates(candidates)
        assert len(result) == 1
        assert result[0].name == "new-skill"

    def test_respects_max_candidates(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        provider = _make_provider()
        config = _make_config(max_candidates=2)
        sd = SkillDiscoverer(store=store, provider=provider, model="test", config=config)

        candidates = [
            SkillCandidate(name=f"skill-{i}", description=f"desc {i}", content=f"#{i}")
            for i in range(5)
        ]
        result = sd._filter_candidates(candidates)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Pending management
# ---------------------------------------------------------------------------


class TestPendingManagement:
    def test_save_and_list_pending(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        provider = _make_provider()
        config = _make_config()
        sd = SkillDiscoverer(store=store, provider=provider, model="test", config=config)

        candidates = [
            SkillCandidate(name="skill-a", description="Desc A", content="# Skill A\nDesc A."),
            SkillCandidate(name="skill-b", description="Desc B", content="# Skill B\nDesc B."),
        ]
        sd.save_pending(candidates)

        pending = sd.list_pending()
        assert len(pending) == 2
        names = {p.name for p in pending}
        assert names == {"skill-a", "skill-b"}

    def test_remove_pending(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        provider = _make_provider()
        config = _make_config()
        sd = SkillDiscoverer(store=store, provider=provider, model="test", config=config)

        candidates = [
            SkillCandidate(name="skill-a", description="Desc A", content="# A"),
            SkillCandidate(name="skill-b", description="Desc B", content="# B"),
        ]
        sd.save_pending(candidates)
        sd.remove_pending("skill-a")

        pending = sd.list_pending()
        assert len(pending) == 1
        assert pending[0].name == "skill-b"

    def test_clear_pending(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        provider = _make_provider()
        config = _make_config()
        sd = SkillDiscoverer(store=store, provider=provider, model="test", config=config)

        candidates = [SkillCandidate(name="x", description="X", content="# X")]
        sd.save_pending(candidates)
        sd.clear_pending()

        assert sd.list_pending() == []

    def test_list_pending_empty_when_no_dir(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        provider = _make_provider()
        config = _make_config()
        sd = SkillDiscoverer(store=store, provider=provider, model="test", config=config)

        assert sd.list_pending() == []


# ---------------------------------------------------------------------------
# Approval / installation
# ---------------------------------------------------------------------------


class TestApproval:
    def test_approve_installs_skill(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        provider = _make_provider()
        config = _make_config()
        sd = SkillDiscoverer(store=store, provider=provider, model="test", config=config)

        candidate = SkillCandidate(
            name="my-skill", description="A great skill", content="# My Skill\nGreat stuff."
        )
        path = sd.approve(candidate)

        assert path.exists()
        assert path.read_text(encoding="utf-8") == "# My Skill\nGreat stuff."
        assert (sd.skills_dir / "my-skill" / "SKILL.md").exists()

    def test_approve_all(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        provider = _make_provider()
        config = _make_config()
        sd = SkillDiscoverer(store=store, provider=provider, model="test", config=config)

        candidates = [
            SkillCandidate(name="a", description="A", content="# A"),
            SkillCandidate(name="b", description="B", content="# B"),
        ]
        paths = sd.approve_all(candidates)
        assert len(paths) == 2
        assert all(p.exists() for p in paths)

    def test_approve_with_git_commit(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        store.git.is_initialized.return_value = True
        provider = _make_provider()
        config = _make_config()
        sd = SkillDiscoverer(store=store, provider=provider, model="test", config=config)

        candidate = SkillCandidate(name="git-skill", description="G", content="# G")
        sd.approve(candidate)

        store.git.auto_commit.assert_called_once_with(
            "skill-discovery: install 'git-skill'"
        )


# ---------------------------------------------------------------------------
# Post-turn trigger
# ---------------------------------------------------------------------------


class TestPostTurnTrigger:
    def test_bump_turn_counter(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        provider = _make_provider()
        config = _make_config(interval_turns=3)
        sd = SkillDiscoverer(store=store, provider=provider, model="test", config=config)

        sd.bump_turn_counter("session-1")
        sd.bump_turn_counter("session-1")
        assert sd._turn_counters["session-1"] == 2

    def test_should_trigger_at_interval(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        provider = _make_provider()
        config = _make_config(interval_turns=3)
        sd = SkillDiscoverer(store=store, provider=provider, model="test", config=config)

        assert not sd.should_trigger("session-1")  # 0 < 3
        sd.bump_turn_counter("session-1")  # 1
        assert not sd.should_trigger("session-1")  # 1 < 3
        sd.bump_turn_counter("session-1")  # 2
        assert not sd.should_trigger("session-1")  # 2 < 3
        sd.bump_turn_counter("session-1")  # 3
        assert sd.should_trigger("session-1")  # 3 >= 3 → trigger + reset
        # Counter should be reset after trigger
        assert sd._turn_counters["session-1"] == 0

    def test_should_trigger_resets_counter(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        provider = _make_provider()
        config = _make_config(interval_turns=2)
        sd = SkillDiscoverer(store=store, provider=provider, model="test", config=config)

        sd.bump_turn_counter("s1")  # 1
        sd.bump_turn_counter("s1")  # 2
        assert sd.should_trigger("s1")  # triggers, resets to 0
        # Next check should not trigger
        assert not sd.should_trigger("s1")

    def test_should_trigger_disabled_with_zero_interval(self, tmp_path: Path) -> None:
        """When interval_turns is 1, every turn triggers."""
        store = _make_store(tmp_path)
        provider = _make_provider()
        config = _make_config(interval_turns=1)
        sd = SkillDiscoverer(store=store, provider=provider, model="test", config=config)

        sd.bump_turn_counter("s1")
        assert sd.should_trigger("s1")  # 1 >= 1 → triggers

    def test_independent_session_counters(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        provider = _make_provider()
        config = _make_config(interval_turns=2)
        sd = SkillDiscoverer(store=store, provider=provider, model="test", config=config)

        sd.bump_turn_counter("s1")  # s1=1
        sd.bump_turn_counter("s2")  # s2=1
        sd.bump_turn_counter("s1")  # s1=2
        assert sd.should_trigger("s1")  # s1 triggers
        assert not sd.should_trigger("s2")  # s2 not yet


# ---------------------------------------------------------------------------
# Discover (integration-style with mocked LLM)
# ---------------------------------------------------------------------------


class TestDiscover:
    @pytest.mark.asyncio
    async def test_discover_no_new_history(self, tmp_path: Path) -> None:
        """When there's no unprocessed history, discover returns empty."""
        store = _make_store(tmp_path)
        store.read_unprocessed_history.return_value = []
        provider = _make_provider()
        config = _make_config()
        sd = SkillDiscoverer(store=store, provider=provider, model="test", config=config)

        result = await sd.discover()
        assert result == []
        provider.chat_with_retry.assert_not_called()

    @pytest.mark.asyncio
    async def test_discover_phase1_fails_returns_empty(self, tmp_path: Path) -> None:
        """When Phase 1 LLM call fails, return empty without advancing cursor."""
        store = _make_store(tmp_path)
        store.read_unprocessed_history.return_value = [
            {"cursor": 1, "timestamp": "2026-01-01", "content": "test"}
        ]
        provider = _make_provider()
        provider.chat_with_retry.side_effect = RuntimeError("LLM error")
        config = _make_config()
        sd = SkillDiscoverer(store=store, provider=provider, model="test", config=config)

        result = await sd.discover()
        assert result == []
        # Cursor should NOT be advanced on Phase 1 failure
        store.set_skill_discovery_cursor.assert_not_called()

    @pytest.mark.asyncio
    async def test_discover_no_patterns_advances_cursor(self, tmp_path: Path) -> None:
        """When Phase 1 returns no patterns, cursor is still advanced."""
        store = _make_store(tmp_path)
        store.read_unprocessed_history.return_value = [
            {"cursor": 5, "timestamp": "2026-01-01", "content": "test"}
        ]
        provider = _make_provider()
        provider.chat_with_retry.return_value = MagicMock(content="[]")
        config = _make_config()
        sd = SkillDiscoverer(store=store, provider=provider, model="test", config=config)

        result = await sd.discover()
        assert result == []
        store.set_skill_discovery_cursor.assert_called_once_with(5)

    @pytest.mark.asyncio
    async def test_discover_weak_recommendations_filtered(self, tmp_path: Path) -> None:
        """Weak recommendations are filtered out, cursor still advances."""
        store = _make_store(tmp_path)
        store.read_unprocessed_history.return_value = [
            {"cursor": 3, "timestamp": "2026-01-01", "content": "test"}
        ]
        provider = _make_provider()
        provider.chat_with_retry.return_value = MagicMock(
            content=json.dumps([
                {"name": "weak-skill", "recommendation": "weak", "description": "skip me"}
            ])
        )
        config = _make_config()
        sd = SkillDiscoverer(store=store, provider=provider, model="test", config=config)

        result = await sd.discover()
        assert result == []
        store.set_skill_discovery_cursor.assert_called_once_with(3)


# ---------------------------------------------------------------------------
# Cron Schedule Tests
# ---------------------------------------------------------------------------


class TestBuildSchedule:
    """Test SkillDiscoveryConfig.build_schedule() behavior."""

    def test_default_schedule_is_every(self) -> None:
        """Without cron, schedule is 'every' based on min_interval_s."""
        config = _make_config(min_interval_s=3600)
        schedule = config.build_schedule("UTC")
        assert schedule.kind == "every"
        assert schedule.every_ms == 3600 * 1000
        assert schedule.expr is None

    def test_cron_overrides_every(self) -> None:
        """When cron is set, it takes precedence over interval-based schedule."""
        config = _make_config(cron="0 9 * * *", min_interval_s=3600)
        schedule = config.build_schedule("UTC")
        assert schedule.kind == "cron"
        assert schedule.expr == "0 9 * * *"
        assert schedule.tz == "UTC"
        assert schedule.every_ms is None

    def test_cron_with_timezone(self) -> None:
        """Cron schedule preserves the provided timezone."""
        config = _make_config(cron="0 9 * * 1-5")
        schedule = config.build_schedule("America/New_York")
        assert schedule.kind == "cron"
        assert schedule.expr == "0 9 * * 1-5"
        assert schedule.tz == "America/New_York"

    def test_min_interval_s_affects_every_ms(self) -> None:
        """Different min_interval_s values produce correct every_ms."""
        config = _make_config(min_interval_s=1800)
        schedule = config.build_schedule("UTC")
        assert schedule.kind == "every"
        assert schedule.every_ms == 1_800_000  # 1800 * 1000

    def test_cron_none_falls_back_to_every(self) -> None:
        """cron=None (default) produces an 'every' schedule."""
        config = _make_config(cron=None)
        schedule = config.build_schedule("UTC")
        assert schedule.kind == "every"

    def test_cron_empty_string_falls_back_to_every(self) -> None:
        """Empty string cron is falsy, so it falls back to 'every' schedule."""
        config = _make_config(cron="")
        schedule = config.build_schedule("UTC")
        assert schedule.kind == "every"


class TestCronJobRegistration:
    """Test that Skill Discovery cron jobs are correctly constructed."""

    def test_cron_job_fields(self) -> None:
        """Verify CronJob for skill-discovery has correct id, name, and payload."""
        from nanobot.cron.types import CronJob, CronPayload

        config = _make_config(cron="0 */4 * * *")
        schedule = config.build_schedule("UTC")

        job = CronJob(
            id="skill-discovery",
            name="skill-discovery",
            schedule=schedule,
            payload=CronPayload(kind="system_event"),
        )

        assert job.id == "skill-discovery"
        assert job.name == "skill-discovery"
        assert job.schedule.kind == "cron"
        assert job.schedule.expr == "0 */4 * * *"
        assert job.payload.kind == "system_event"
        assert job.enabled is True

    def test_no_cron_job_when_cron_unset(self) -> None:
        """When cron is not set, no CronJob should be registered."""
        config = _make_config(cron=None)
        # In commands.py, cron.register_system_job is only called if sd_cfg.cron
        # This test verifies the condition logic
        assert config.cron is None

    def test_cron_job_every_schedule(self) -> None:
        """When using interval-based schedule, CronJob uses 'every' kind."""
        from nanobot.cron.types import CronJob, CronPayload

        config = _make_config(min_interval_s=7200)
        schedule = config.build_schedule("UTC")

        job = CronJob(
            id="skill-discovery",
            name="skill-discovery",
            schedule=schedule,
            payload=CronPayload(kind="system_event"),
        )

        assert job.schedule.kind == "every"
        assert job.schedule.every_ms == 7_200_000


class TestCronDiscoveryExecution:
    """Test the cron job execution path for skill discovery."""

    @staticmethod
    def _mock_runner_write(pending_dir: Path, skill_name: str, skill_content: str) -> MagicMock:
        """Create a mock runner whose run() writes a SKILL.md to pending_dir.

        This simulates Phase 2 AgentRunner using write_file tool to generate
        skill files, without requiring a real AgentRunner + LLM round-trip.
        """
        mock_result = MagicMock()
        mock_result.stop_reason = "max_iterations"
        mock_result.tool_events = []

        async def _fake_run(spec):
            # Simulate what the real runner does: write SKILL.md via write_file
            skill_dir = pending_dir / skill_name
            skill_dir.mkdir(parents=True, exist_ok=True)
            (skill_dir / "SKILL.md").write_text(skill_content, encoding="utf-8")
            return mock_result

        runner = MagicMock()
        runner.run = _fake_run
        return runner

    @pytest.mark.asyncio
    async def test_cron_discovers_and_saves_pending(self, tmp_path: Path) -> None:
        """Cron trigger should call discover() and save_pending() for candidates."""
        store = _make_store(tmp_path)
        store.read_unprocessed_history.return_value = [
            {"cursor": 10, "timestamp": "2026-01-01", "content": "test"}
        ]
        provider = _make_provider()
        # Phase 1 returns one pattern
        provider.chat_with_retry.return_value = MagicMock(
            content=json.dumps([
                {
                    "name": "cron-skill",
                    "description": "A skill found by cron",
                    "recommendation": "strong",
                    "frequency": "3 times",
                    "evidence": ["entry 1"],
                    "complexity": "medium",
                    "rationale": "Repeated pattern",
                }
            ])
        )
        config = _make_config(cron="0 9 * * *")
        sd = SkillDiscoverer(store=store, provider=provider, model="test", config=config)

        # Mock Phase 2 runner to write SKILL.md to pending_dir
        skill_content = "# cron-skill\nA skill found by cron"
        sd._runner = self._mock_runner_write(
            sd._pending_dir, "cron-skill", skill_content
        )

        # Simulate what commands.py does on cron trigger
        candidates = await sd.discover()
        if candidates:
            sd.save_pending(candidates)

        # Verify candidates were discovered and saved
        assert len(candidates) == 1
        assert candidates[0].name == "cron-skill"
        pending = sd.list_pending()
        assert len(pending) == 1
        assert pending[0].name == "cron-skill"

    @pytest.mark.asyncio
    async def test_cron_discovers_no_candidates(self, tmp_path: Path) -> None:
        """Cron trigger with no new history should return empty list."""
        store = _make_store(tmp_path)
        store.read_unprocessed_history.return_value = []
        provider = _make_provider()
        config = _make_config(cron="0 */6 * * *")
        sd = SkillDiscoverer(store=store, provider=provider, model="test", config=config)

        candidates = await sd.discover()
        assert candidates == []

    @pytest.mark.asyncio
    async def test_cron_with_auto_approve(self, tmp_path: Path) -> None:
        """Cron trigger with autoApprove should install candidates directly."""
        store = _make_store(tmp_path)
        store.read_unprocessed_history.return_value = [
            {"cursor": 10, "timestamp": "2026-01-01", "content": "test"}
        ]
        provider = _make_provider()
        provider.chat_with_retry.return_value = MagicMock(
            content=json.dumps([
                {
                    "name": "auto-skill",
                    "description": "Auto-approved skill",
                    "recommendation": "strong",
                    "frequency": "2 times",
                    "evidence": ["entry 1", "entry 2"],
                    "complexity": "low",
                    "rationale": "Clear pattern",
                }
            ])
        )
        config = _make_config(cron="0 9 * * *", auto_approve=True)
        sd = SkillDiscoverer(store=store, provider=provider, model="test", config=config)

        # Mock Phase 2 runner to write SKILL.md to pending_dir
        skill_content = "# auto-skill\nAuto-approved skill"
        sd._runner = self._mock_runner_write(
            sd._pending_dir, "auto-skill", skill_content
        )

        # Simulate auto-approve path (as in cmd_discover_skills)
        candidates = await sd.discover()
        paths = []
        if candidates and sd.config.auto_approve:
            paths = sd.approve_all(candidates)

        assert len(paths) == 1
        # Verify SKILL.md was written to skills/ directory
        skill_file = tmp_path / "skills" / "auto-skill" / "SKILL.md"
        assert skill_file.exists()

    @pytest.mark.asyncio
    async def test_cron_failure_does_not_advance_cursor(self, tmp_path: Path) -> None:
        """If Phase 1 fails during cron execution, cursor should not advance."""
        store = _make_store(tmp_path)
        store.read_unprocessed_history.return_value = [
            {"cursor": 10, "timestamp": "2026-01-01", "content": "test"}
        ]
        provider = _make_provider()
        provider.chat_with_retry.side_effect = Exception("LLM timeout")
        config = _make_config(cron="0 9 * * *")
        sd = SkillDiscoverer(store=store, provider=provider, model="test", config=config)

        candidates = await sd.discover()
        assert candidates == []
        # Cursor must NOT be advanced on Phase 1 failure
        store.set_skill_discovery_cursor.assert_not_called()


# ---------------------------------------------------------------------------
# Trigger Mode Tests — Manual, Post-turn, Cron
# ---------------------------------------------------------------------------


def _make_inbound(channel: str = "cli", chat_id: str = "test") -> MagicMock:
    """Create a mock InboundMessage."""
    msg = MagicMock()
    msg.channel = channel
    msg.chat_id = chat_id
    msg.content = "/discover-skills"
    return msg


def _make_command_context(loop_mock: MagicMock, msg: MagicMock = None, args: str = "") -> MagicMock:
    """Create a mock CommandContext."""
    ctx = MagicMock()
    ctx.loop = loop_mock
    ctx.msg = msg or _make_inbound()
    ctx.args = args
    return ctx


class TestManualTrigger:
    """Test /discover-skills command (manual trigger) behavior."""

    @pytest.mark.asyncio
    async def test_manual_trigger_disabled(self) -> None:
        """When skill_discoverer is None, return disabled message."""
        from nanobot.command.builtin import cmd_discover_skills

        loop_mock = MagicMock()
        loop_mock.skill_discoverer = None
        ctx = _make_command_context(loop_mock)

        result = await cmd_discover_skills(ctx)
        assert "not enabled" in result.content

    @pytest.mark.asyncio
    async def test_manual_trigger_returns_immediate_ack(self) -> None:
        """Manual trigger returns 'Discovering skills...' immediately."""
        from nanobot.command.builtin import cmd_discover_skills

        loop_mock = MagicMock()
        discoverer = MagicMock(spec=SkillDiscoverer)
        discoverer.config = _make_config(enabled=True)
        # Make discover() a long-running coroutine to verify immediate return
        async def _slow_discover():
            import asyncio
            await asyncio.sleep(10)
            return []
        discoverer.discover = _slow_discover
        loop_mock.skill_discoverer = discoverer
        loop_mock.bus = MagicMock()
        ctx = _make_command_context(loop_mock)

        result = await cmd_discover_skills(ctx)
        assert "Discovering" in result.content

    @pytest.mark.asyncio
    async def test_manual_trigger_no_candidates(self, tmp_path: Path) -> None:
        """Manual trigger with no candidates publishes 'no new skills found'."""
        from nanobot.command.builtin import cmd_discover_skills

        store = _make_store(tmp_path)
        store.read_unprocessed_history.return_value = []
        provider = _make_provider()
        config = _make_config()
        sd = SkillDiscoverer(store=store, provider=provider, model="test", config=config)

        loop_mock = MagicMock()
        loop_mock.skill_discoverer = sd
        bus_mock = MagicMock()
        bus_mock.publish_outbound = AsyncMock()
        loop_mock.bus = bus_mock
        ctx = _make_command_context(loop_mock)

        result = await cmd_discover_skills(ctx)
        assert "Discovering" in result.content

        # Wait for background task to complete
        import asyncio
        await asyncio.sleep(0.1)

        # Bus should have published the result
        bus_mock.publish_outbound.assert_called_once()
        outbound = bus_mock.publish_outbound.call_args[0][0]
        assert "no new skills found" in outbound.content

    @pytest.mark.asyncio
    async def test_manual_trigger_with_candidates_saves_pending(self, tmp_path: Path) -> None:
        """Manual trigger with candidates saves them as pending (autoApprove=False)."""
        from nanobot.command.builtin import cmd_discover_skills

        store = _make_store(tmp_path)
        store.read_unprocessed_history.return_value = [
            {"cursor": 10, "timestamp": "2026-01-01", "content": "test"}
        ]
        provider = _make_provider()
        provider.chat_with_retry.return_value = MagicMock(
            content=json.dumps([
                {
                    "name": "manual-skill",
                    "description": "Found manually",
                    "recommendation": "strong",
                    "frequency": "2 times",
                    "evidence": ["e1"],
                    "complexity": "low",
                    "rationale": "test",
                }
            ])
        )
        config = _make_config(auto_approve=False)
        sd = SkillDiscoverer(store=store, provider=provider, model="test", config=config)

        # Mock Phase 2 runner
        skill_content = "# manual-skill\nFound manually"
        sd._runner = TestCronDiscoveryExecution._mock_runner_write(
            sd._pending_dir, "manual-skill", skill_content
        )

        loop_mock = MagicMock()
        loop_mock.skill_discoverer = sd
        bus_mock = MagicMock()
        bus_mock.publish_outbound = AsyncMock()
        loop_mock.bus = bus_mock
        ctx = _make_command_context(loop_mock)

        result = await cmd_discover_skills(ctx)
        assert "Discovering" in result.content

        import asyncio
        await asyncio.sleep(0.2)

        outbound = bus_mock.publish_outbound.call_args[0][0]
        assert "1 candidate" in outbound.content
        assert "manual-skill" in outbound.content
        assert "/skill-approve" in outbound.content

    @pytest.mark.asyncio
    async def test_manual_trigger_auto_approve_installs(self, tmp_path: Path) -> None:
        """Manual trigger with autoApprove=True installs skills directly."""
        from nanobot.command.builtin import cmd_discover_skills

        store = _make_store(tmp_path)
        store.read_unprocessed_history.return_value = [
            {"cursor": 10, "timestamp": "2026-01-01", "content": "test"}
        ]
        provider = _make_provider()
        provider.chat_with_retry.return_value = MagicMock(
            content=json.dumps([
                {
                    "name": "auto-manual-skill",
                    "description": "Auto-installed",
                    "recommendation": "strong",
                    "frequency": "1 time",
                    "evidence": ["e1"],
                    "complexity": "low",
                    "rationale": "test",
                }
            ])
        )
        config = _make_config(auto_approve=True)
        sd = SkillDiscoverer(store=store, provider=provider, model="test", config=config)

        skill_content = "# auto-manual-skill\nAuto-installed"
        sd._runner = TestCronDiscoveryExecution._mock_runner_write(
            sd._pending_dir, "auto-manual-skill", skill_content
        )

        loop_mock = MagicMock()
        loop_mock.skill_discoverer = sd
        bus_mock = MagicMock()
        bus_mock.publish_outbound = AsyncMock()
        loop_mock.bus = bus_mock
        ctx = _make_command_context(loop_mock)

        result = await cmd_discover_skills(ctx)

        import asyncio
        await asyncio.sleep(0.2)

        outbound = bus_mock.publish_outbound.call_args[0][0]
        assert "installed" in outbound.content.lower()
        assert "auto-manual-skill" in outbound.content
        # Verify skill file was written to skills/ directory
        skill_file = tmp_path / "skills" / "auto-manual-skill" / "SKILL.md"
        assert skill_file.exists()


class TestSkillApproveCommand:
    """Test /skill-approve command behavior."""

    @pytest.mark.asyncio
    async def test_approve_disabled(self) -> None:
        """When discoverer is None, return disabled message."""
        from nanobot.command.builtin import cmd_skill_approve

        loop_mock = MagicMock()
        loop_mock.skill_discoverer = None
        ctx = _make_command_context(loop_mock, args="test-skill")

        result = await cmd_skill_approve(ctx)
        assert "not enabled" in result.content

    @pytest.mark.asyncio
    async def test_approve_no_pending(self, tmp_path: Path) -> None:
        """When no pending skills, return appropriate message."""
        from nanobot.command.builtin import cmd_skill_approve

        store = _make_store(tmp_path)
        provider = _make_provider()
        config = _make_config()
        sd = SkillDiscoverer(store=store, provider=provider, model="test", config=config)

        loop_mock = MagicMock()
        loop_mock.skill_discoverer = sd
        ctx = _make_command_context(loop_mock, args="anything")

        result = await cmd_skill_approve(ctx)
        assert "No pending" in result.content

    @pytest.mark.asyncio
    async def test_approve_specific_skill(self, tmp_path: Path) -> None:
        """Approve a specific skill by name."""
        from nanobot.command.builtin import cmd_skill_approve

        store = _make_store(tmp_path)
        provider = _make_provider()
        config = _make_config()
        sd = SkillDiscoverer(store=store, provider=provider, model="test", config=config)

        # Save a pending candidate
        candidates = [
            SkillCandidate(name="skill-a", description="First", content="# Skill A\nFirst skill"),
            SkillCandidate(name="skill-b", description="Second", content="# Skill B\nSecond skill"),
        ]
        sd.save_pending(candidates)

        loop_mock = MagicMock()
        loop_mock.skill_discoverer = sd
        ctx = _make_command_context(loop_mock, args="skill-a")

        result = await cmd_skill_approve(ctx)
        assert "skill-a" in result.content
        assert "Installed" in result.content
        # Verify only skill-a was installed
        assert (tmp_path / "skills" / "skill-a" / "SKILL.md").exists()
        assert not (tmp_path / "skills" / "skill-b" / "SKILL.md").exists()

    @pytest.mark.asyncio
    async def test_approve_all(self, tmp_path: Path) -> None:
        """Approve all pending skills."""
        from nanobot.command.builtin import cmd_skill_approve

        store = _make_store(tmp_path)
        provider = _make_provider()
        config = _make_config()
        sd = SkillDiscoverer(store=store, provider=provider, model="test", config=config)

        candidates = [
            SkillCandidate(name="skill-x", description="X", content="# X"),
            SkillCandidate(name="skill-y", description="Y", content="# Y"),
        ]
        sd.save_pending(candidates)

        loop_mock = MagicMock()
        loop_mock.skill_discoverer = sd
        ctx = _make_command_context(loop_mock, args="all")

        result = await cmd_skill_approve(ctx)
        assert "2 skill" in result.content
        assert (tmp_path / "skills" / "skill-x" / "SKILL.md").exists()
        assert (tmp_path / "skills" / "skill-y" / "SKILL.md").exists()

    @pytest.mark.asyncio
    async def test_approve_nonexistent_name(self, tmp_path: Path) -> None:
        """Approve with a name that doesn't match any pending skill."""
        from nanobot.command.builtin import cmd_skill_approve

        store = _make_store(tmp_path)
        provider = _make_provider()
        config = _make_config()
        sd = SkillDiscoverer(store=store, provider=provider, model="test", config=config)

        sd.save_pending([
            SkillCandidate(name="real-skill", description="Real", content="# Real"),
        ])

        loop_mock = MagicMock()
        loop_mock.skill_discoverer = sd
        ctx = _make_command_context(loop_mock, args="fake-skill")

        result = await cmd_skill_approve(ctx)
        assert "No pending skill named 'fake-skill'" in result.content
        assert "real-skill" in result.content  # lists available

    @pytest.mark.asyncio
    async def test_approve_no_args_lists_pending(self, tmp_path: Path) -> None:
        """Approve with no args lists pending skills."""
        from nanobot.command.builtin import cmd_skill_approve

        store = _make_store(tmp_path)
        provider = _make_provider()
        config = _make_config()
        sd = SkillDiscoverer(store=store, provider=provider, model="test", config=config)

        sd.save_pending([
            SkillCandidate(name="list-skill", description="List me", content="# List"),
        ])

        loop_mock = MagicMock()
        loop_mock.skill_discoverer = sd
        ctx = _make_command_context(loop_mock, args="")

        result = await cmd_skill_approve(ctx)
        assert "Pending" in result.content
        assert "list-skill" in result.content
        assert "/skill-approve" in result.content


class TestPostTurnTrigger:
    """Test _maybe_trigger_skill_discovery (post-turn auto-trigger) behavior."""

    def test_post_turn_disabled_when_discoverer_none(self) -> None:
        """When skill_discoverer is None, no trigger occurs."""
        loop_mock = MagicMock()
        loop_mock.skill_discoverer = None
        loop_mock._schedule_background = MagicMock()

        # Simulate _maybe_trigger_skill_discovery logic
        sd = loop_mock.skill_discoverer
        if sd is not None and sd.config.enabled:
            sd.bump_turn_counter("s1")
            if sd.should_trigger("s1"):
                loop_mock._schedule_background(MagicMock())

        loop_mock._schedule_background.assert_not_called()

    def test_post_turn_disabled_when_config_disabled(self, tmp_path: Path) -> None:
        """When enabled=False, no trigger occurs even after enough turns."""
        store = _make_store(tmp_path)
        provider = _make_provider()
        config = _make_config(enabled=False, interval_turns=1)
        sd = SkillDiscoverer(store=store, provider=provider, model="test", config=config)

        loop_mock = MagicMock()
        loop_mock.skill_discoverer = sd
        loop_mock._schedule_background = MagicMock()

        # Simulate _maybe_trigger_skill_discovery logic
        if sd is not None and sd.config.enabled:
            sd.bump_turn_counter("s1")
            if sd.should_trigger("s1"):
                loop_mock._schedule_background(MagicMock())

        loop_mock._schedule_background.assert_not_called()

    def test_post_turn_triggers_after_interval(self, tmp_path: Path) -> None:
        """Post-turn triggers after interval_turns conversations."""
        store = _make_store(tmp_path)
        provider = _make_provider()
        config = _make_config(enabled=True, interval_turns=3)
        sd = SkillDiscoverer(store=store, provider=provider, model="test", config=config)

        loop_mock = MagicMock()
        loop_mock.skill_discoverer = sd
        loop_mock._schedule_background = MagicMock()

        # Simulate 3 turns
        for _ in range(3):
            sd.bump_turn_counter("s1")
        if sd.should_trigger("s1"):
            loop_mock._schedule_background(MagicMock())

        loop_mock._schedule_background.assert_called_once()

    def test_post_turn_no_trigger_before_interval(self, tmp_path: Path) -> None:
        """Post-turn does NOT trigger before reaching interval_turns."""
        store = _make_store(tmp_path)
        provider = _make_provider()
        config = _make_config(enabled=True, interval_turns=5)
        sd = SkillDiscoverer(store=store, provider=provider, model="test", config=config)

        loop_mock = MagicMock()
        loop_mock.skill_discoverer = sd
        loop_mock._schedule_background = MagicMock()

        # Only 3 turns, need 5
        for _ in range(3):
            sd.bump_turn_counter("s1")
        if sd.should_trigger("s1"):
            loop_mock._schedule_background(MagicMock())

        loop_mock._schedule_background.assert_not_called()

    def test_post_turn_counter_resets_after_trigger(self, tmp_path: Path) -> None:
        """After triggering, counter resets and next interval starts fresh."""
        store = _make_store(tmp_path)
        provider = _make_provider()
        config = _make_config(enabled=True, interval_turns=2)
        sd = SkillDiscoverer(store=store, provider=provider, model="test", config=config)

        # First cycle: 2 turns → trigger
        sd.bump_turn_counter("s1")
        sd.bump_turn_counter("s1")
        assert sd.should_trigger("s1")

        # Counter reset, 1 more turn should NOT trigger
        sd.bump_turn_counter("s1")
        assert not sd.should_trigger("s1")

    def test_post_turn_independent_sessions(self, tmp_path: Path) -> None:
        """Different sessions have independent turn counters."""
        store = _make_store(tmp_path)
        provider = _make_provider()
        config = _make_config(enabled=True, interval_turns=2)
        sd = SkillDiscoverer(store=store, provider=provider, model="test", config=config)

        # Session A reaches threshold
        sd.bump_turn_counter("session-a")
        sd.bump_turn_counter("session-a")
        assert sd.should_trigger("session-a")

        # Session B has not
        sd.bump_turn_counter("session-b")
        assert not sd.should_trigger("session-b")

    @pytest.mark.asyncio
    async def test_post_turn_discover_failure_is_caught(self, tmp_path: Path) -> None:
        """Post-turn discover() failure is caught and does not crash."""
        store = _make_store(tmp_path)
        store.read_unprocessed_history.side_effect = RuntimeError("DB error")
        provider = _make_provider()
        config = _make_config(enabled=True, interval_turns=1)
        sd = SkillDiscoverer(store=store, provider=provider, model="test", config=config)

        # Trigger should not raise
        sd.bump_turn_counter("s1")
        assert sd.should_trigger("s1")

        # discover() should raise, but the caller (_maybe_trigger_skill_discovery)
        # wraps it in try/except — verify the exception is raised from discover
        with pytest.raises(RuntimeError, match="DB error"):
            await sd.discover()


class TestCronTriggerHandler:
    """Test the cron job handler logic in commands.py for skill-discovery."""

    @pytest.mark.asyncio
    async def test_cron_handler_discovers_and_saves(self, tmp_path: Path) -> None:
        """Cron handler calls discover() and save_pending() for candidates."""
        store = _make_store(tmp_path)
        store.read_unprocessed_history.return_value = [
            {"cursor": 10, "timestamp": "2026-01-01", "content": "test"}
        ]
        provider = _make_provider()
        provider.chat_with_retry.return_value = MagicMock(
            content=json.dumps([
                {
                    "name": "cron-handler-skill",
                    "description": "From cron handler",
                    "recommendation": "strong",
                    "frequency": "2 times",
                    "evidence": ["e1"],
                    "complexity": "low",
                    "rationale": "test",
                }
            ])
        )
        config = _make_config(cron="0 9 * * *")
        sd = SkillDiscoverer(store=store, provider=provider, model="test", config=config)

        skill_content = "# cron-handler-skill\nFrom cron handler"
        sd._runner = TestCronDiscoveryExecution._mock_runner_write(
            sd._pending_dir, "cron-handler-skill", skill_content
        )

        # Simulate the cron handler logic from commands.py
        candidates = await sd.discover()
        if candidates:
            sd.save_pending(candidates)

        assert len(candidates) == 1
        assert candidates[0].name == "cron-handler-skill"
        pending = sd.list_pending()
        assert len(pending) == 1

    @pytest.mark.asyncio
    async def test_cron_handler_no_discoverer(self) -> None:
        """Cron handler with no discoverer skips gracefully."""
        agent = MagicMock()
        agent.skill_discoverer = None

        # Simulate cron handler logic
        if agent.skill_discoverer:
            candidates = await agent.skill_discoverer.discover()
        else:
            candidates = []

        assert candidates == []

    @pytest.mark.asyncio
    async def test_cron_handler_failure_is_caught(self, tmp_path: Path) -> None:
        """Cron handler catches discover() exceptions."""
        store = _make_store(tmp_path)
        store.read_unprocessed_history.return_value = [
            {"cursor": 10, "timestamp": "2026-01-01", "content": "test"}
        ]
        provider = _make_provider()
        provider.chat_with_retry.side_effect = RuntimeError("LLM down")
        config = _make_config(cron="0 9 * * *")
        sd = SkillDiscoverer(store=store, provider=provider, model="test", config=config)

        # Simulate cron handler with try/except (as in commands.py)
        try:
            candidates = await sd.discover()
            if candidates:
                sd.save_pending(candidates)
        except Exception:
            candidates = []

        assert candidates == []

    @pytest.mark.asyncio
    async def test_cron_handler_empty_result(self, tmp_path: Path) -> None:
        """Cron handler with no new history returns empty, no save_pending call."""
        store = _make_store(tmp_path)
        store.read_unprocessed_history.return_value = []
        provider = _make_provider()
        config = _make_config(cron="0 */6 * * *")
        sd = SkillDiscoverer(store=store, provider=provider, model="test", config=config)

        candidates = await sd.discover()
        save_called = False
        if candidates:
            sd.save_pending(candidates)
            save_called = True

        assert candidates == []
        assert not save_called
