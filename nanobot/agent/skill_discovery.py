"""Skill discovery: analyze conversation history to find reusable behavioral patterns."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from nanobot.utils.prompt_templates import render_template

if TYPE_CHECKING:
    from nanobot.agent.memory import MemoryStore
    from nanobot.agent.runner import AgentRunner
    from nanobot.config.schema import SkillDiscoveryConfig
    from nanobot.providers.base import LLMProvider


@dataclass
class SkillCandidate:
    """A candidate skill discovered from conversation history."""

    name: str
    description: str
    content: str  # Full SKILL.md content

    def format_preview(self) -> str:
        """Format a short preview for display."""
        return f"**{self.name}** — {self.description}"


class SkillDiscoverer:
    """Discover reusable skills from conversation history.

    Two-phase processing:
      Phase 1: LLM analyzes history → structured JSON patterns
      Phase 2: AgentRunner generates SKILL.md files using read_file + write_file

    Quality gates:
      - Name conflict check (skip if skill already exists)
      - Deduplication (skip duplicate candidate names)
      - max_candidates cap
      - Weak recommendation filtering (Phase 2)
    """

    def __init__(
        self,
        store: MemoryStore,
        provider: LLMProvider,
        model: str,
        config: SkillDiscoveryConfig,
        skills_dir: Path | None = None,
    ):
        self.store = store
        self.provider = provider
        self.model = model
        self.config = config
        self.skills_dir = skills_dir or (store.workspace / "skills")
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self._pending_dir = store.workspace / ".pending_skills"

        # Lazy-init AgentRunner for Phase 2
        self._runner: AgentRunner | None = None

        # Post-turn trigger state (in-memory, resets on restart)
        self._turn_counters: dict[str, int] = {}

    def _get_runner(self) -> AgentRunner:
        """Lazy-initialize the AgentRunner for Phase 2."""
        if self._runner is None:
            from nanobot.agent.runner import AgentRunner
            self._runner = AgentRunner(self.provider)
        return self._runner

    # -- main entry point ----------------------------------------------------

    async def discover(self) -> list[SkillCandidate]:
        """Two-phase skill discovery: analyze patterns, then generate skills.

        Returns a list of SkillCandidate objects (may be empty).
        Cursor is always advanced after processing, even if no candidates found.
        """
        # 1. Incremental history read
        last_cursor = self.store.get_skill_discovery_cursor()
        entries = self.store.read_unprocessed_history(since_cursor=last_cursor)
        if not entries:
            logger.info(
                "Skill discovery: no new history entries since cursor {}",
                last_cursor,
            )
            return []

        batch = entries[: self.config.max_history_entries]

        # 2. Build history text
        history_text = "\n".join(
            f"[{e['timestamp']}] {e['content']}" for e in batch
        )

        # 3. Build context (Memory + User + existing Skills)
        context = self._build_context()

        # ── Phase 1: Structured analysis ──
        phase1_prompt = f"## Conversation History\n{history_text}\n\n{context}"
        try:
            phase1_response = await self.provider.chat_with_retry(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": render_template(
                            "agent/skill_discovery_phase1.md", strip=True
                        ),
                    },
                    {"role": "user", "content": phase1_prompt},
                ],
                tools=None,
                tool_choice=None,
            )
            analysis = phase1_response.content or ""
            logger.debug(
                "Skill discovery Phase 1: {} chars", len(analysis)
            )
        except Exception:
            logger.exception("Skill discovery Phase 1 failed")
            # Phase 1 failed — do NOT advance cursor (preserve retry opportunity)
            return []

        # Parse Phase 1 result
        patterns = self._parse_phase1_analysis(analysis)
        if not patterns:
            # No patterns found — advance cursor and return
            new_cursor = batch[-1]["cursor"]
            self.store.set_skill_discovery_cursor(new_cursor)
            logger.info(
                "Skill discovery: no patterns found in {} entries (cursor {}→{})",
                len(batch), last_cursor, new_cursor,
            )
            return []

        # Quality gate: filter weak recommendations
        patterns = [p for p in patterns if p.get("recommendation") != "weak"]
        if not patterns:
            new_cursor = batch[-1]["cursor"]
            self.store.set_skill_discovery_cursor(new_cursor)
            logger.info(
                "Skill discovery: all patterns filtered as weak (cursor {}→{})",
                last_cursor, new_cursor,
            )
            return []

        # ── Phase 2: AgentRunner generation ──
        pending_dir = self._pending_dir
        pending_dir.mkdir(parents=True, exist_ok=True)

        phase2_prompt = (
            f"## Analysis Result\n{json.dumps(patterns, indent=2, ensure_ascii=False)}\n\n{context}"
        )
        tools = self._build_tools(pending_dir)
        messages = [
            {
                "role": "system",
                "content": render_template(
                    "agent/skill_discovery_phase2.md", strip=True
                ),
            },
            {"role": "user", "content": phase2_prompt},
        ]

        try:
            runner = self._get_runner()
            from nanobot.agent.runner import AgentRunSpec
            result = await runner.run(AgentRunSpec(
                initial_messages=messages,
                tools=tools,
                model=self.model,
                max_iterations=self.config.max_candidates * 3,  # ~3 rounds per candidate
                max_tool_result_chars=16_000,
                fail_on_tool_error=False,
            ))
            logger.debug(
                "Skill discovery Phase 2: stop_reason={}, events={}",
                result.stop_reason, len(result.tool_events or []),
            )
        except Exception:
            logger.exception("Skill discovery Phase 2 failed")
            result = None

        # Collect generated candidates from pending directory
        candidates = self._collect_pending_candidates(pending_dir)

        # Apply quality gates: name conflict + dedup + max_candidates
        candidates = self._filter_candidates(candidates)

        # Advance cursor — always, to avoid re-processing
        new_cursor = batch[-1]["cursor"]
        self.store.set_skill_discovery_cursor(new_cursor)

        logger.info(
            "Skill discovery: analyzed {} entries (cursor {}→{}), found {} candidate(s)",
            len(batch), last_cursor, new_cursor, len(candidates),
        )
        return candidates

    # -- context building ----------------------------------------------------

    def _build_context(self) -> str:
        """Build context string with Memory, User profile, and existing skills."""
        parts = []

        # Memory context
        memory = self.store.read_memory()
        if memory:
            parts.append(f"## Current MEMORY.md\n{memory}")

        # User profile
        user = self.store.read_user()
        if user:
            parts.append(f"## Current USER.md\n{user}")

        # Existing Skills list (avoid duplicate generation)
        existing = self._list_existing_skills()
        if existing:
            parts.append(
                "## Existing Skills\n" + "\n".join(f"- {s}" for s in existing)
            )

        return "\n\n".join(parts)

    def _list_existing_skills(self) -> list[str]:
        """List names of all installed skills."""
        if not self.skills_dir.exists():
            return []
        return [
            d.name
            for d in sorted(self.skills_dir.iterdir())
            if d.is_dir() and (d / "SKILL.md").exists()
        ]

    # -- candidate filtering -------------------------------------------------

    def _filter_candidates(self, candidates: list[SkillCandidate]) -> list[SkillCandidate]:
        """Filter out invalid or duplicate candidates."""
        existing = set(self._list_existing_skills())
        seen_names: set[str] = set()
        filtered: list[SkillCandidate] = []

        for c in candidates:
            # Name conflict check
            if c.name in existing:
                logger.debug(
                    "Skill discovery: skipping '{}' — already exists", c.name
                )
                continue
            # Dedup
            if c.name in seen_names:
                continue
            seen_names.add(c.name)
            filtered.append(c)

        return filtered[: self.config.max_candidates]

    # -- Phase 1 analysis parsing --------------------------------------------

    @staticmethod
    def _parse_phase1_analysis(analysis: str) -> list[dict]:
        """Parse Phase 1 structured analysis into pattern dicts."""
        # Try extracting JSON from markdown code block
        json_match = re.search(
            r"```(?:json)?\s*(\[.*?\])\s*```", analysis, re.DOTALL
        )
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try parsing the entire response as JSON
        try:
            parsed = json.loads(analysis)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass

        logger.warning("Skill discovery: failed to parse Phase 1 analysis")
        return []

    # -- Phase 2 tool building -----------------------------------------------

    def _build_tools(self, target_dir: Path) -> "ToolRegistry":
        """Build tool registry for Phase 2 AgentRunner."""
        from nanobot.agent.tools.filesystem import ReadFileTool, WriteFileTool
        from nanobot.agent.tools.registry import ToolRegistry

        tools = ToolRegistry()
        workspace = self.store.workspace
        tools.register(ReadFileTool(workspace=workspace, allowed_dir=workspace))
        tools.register(WriteFileTool(workspace=target_dir, allowed_dir=target_dir))
        return tools

    # -- pending candidate collection ----------------------------------------

    def _collect_pending_candidates(self, pending_dir: Path) -> list[SkillCandidate]:
        """Collect skill candidates from pending directory."""
        candidates: list[SkillCandidate] = []
        if not pending_dir.exists():
            return candidates

        for skill_dir in sorted(pending_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue
            content = skill_md.read_text(encoding="utf-8")
            name = skill_dir.name
            desc = self._extract_description(content)
            candidates.append(SkillCandidate(
                name=name,
                description=desc,
                content=content,
            ))

        return candidates

    @staticmethod
    def _extract_description(content: str) -> str:
        """Extract a one-line description from SKILL.md content."""
        # Try to find the first non-heading, non-empty line
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            return line[:200]  # Truncate long descriptions
        return "(no description)"

    # -- pending management --------------------------------------------------

    def save_pending(self, candidates: list[SkillCandidate]) -> None:
        """Save candidates to the pending directory for later approval."""
        self._pending_dir.mkdir(parents=True, exist_ok=True)
        for c in candidates:
            skill_dir = self._pending_dir / c.name
            skill_dir.mkdir(parents=True, exist_ok=True)
            (skill_dir / "SKILL.md").write_text(c.content, encoding="utf-8")
        logger.info(
            "Skill discovery: saved {} candidate(s) to pending", len(candidates)
        )

    def list_pending(self) -> list[SkillCandidate]:
        """List all pending skill candidates."""
        return self._collect_pending_candidates(self._pending_dir)

    def remove_pending(self, name: str) -> None:
        """Remove a specific pending skill candidate."""
        skill_dir = self._pending_dir / name
        if skill_dir.is_dir():
            import shutil
            shutil.rmtree(skill_dir, ignore_errors=True)

    def clear_pending(self) -> None:
        """Remove all pending skill candidates."""
        if self._pending_dir.is_dir():
            import shutil
            shutil.rmtree(self._pending_dir, ignore_errors=True)

    # -- approval / installation ---------------------------------------------

    def approve(self, candidate: SkillCandidate) -> Path:
        """Install a skill candidate to the skills directory."""
        skill_dir = self.skills_dir / candidate.name
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_path = skill_dir / "SKILL.md"
        skill_path.write_text(candidate.content, encoding="utf-8")

        # Git commit
        if self.store.git.is_initialized():
            self.store.git.auto_commit(
                f"skill-discovery: install '{candidate.name}'"
            )

        logger.info("Installed skill '{}' to {}", candidate.name, skill_path)
        return skill_path

    def approve_all(self, candidates: list[SkillCandidate]) -> list[Path]:
        """Install all skill candidates."""
        paths = []
        for c in candidates:
            paths.append(self.approve(c))
        return paths

    # -- post-turn trigger ---------------------------------------------------

    def bump_turn_counter(self, session_key: str) -> None:
        """Increment the turn counter for a session."""
        self._turn_counters[session_key] = self._turn_counters.get(session_key, 0) + 1

    def should_trigger(self, session_key: str) -> bool:
        """Check if skill discovery should trigger for this session.

        Triggers when the turn counter reaches `interval_turns`,
        then resets the counter.
        """
        interval = self.config.interval_turns
        if interval <= 0:
            return False
        count = self._turn_counters.get(session_key, 0)
        if count >= interval:
            self._turn_counters[session_key] = 0
            return True
        return False
