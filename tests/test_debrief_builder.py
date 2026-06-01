"""Tests for the structured image debrief prompt builder."""

from src.prompts.builders.debrief_builder import (
    DebriefPromptBuilder,
    build_debrief_prompt,
)


EXPECTED_SECTIONS = [
    "SCENE OVERVIEW",
    "SUBJECTS",
    "EXPRESSION & BODY LANGUAGE",
    "OBJECTS & TEXT",
    "LIGHTING & IMAGE QUALITY",
    "COMPOSITION",
    "CONFIDENCE & LIMITATIONS",
]


def test_build_debrief_prompt_uses_vision_builder_structure():
    prompt = build_debrief_prompt()

    assert isinstance(prompt, str)
    assert len(prompt) > 0
    assert "Analyze the image below" in prompt
    assert "full" in prompt.lower()
    assert "Ekman" in prompt or "FBI" in prompt


def test_build_debrief_prompt_contains_exact_sections_in_order():
    prompt = build_debrief_prompt()

    last_index = -1
    for section in EXPECTED_SECTIONS:
        marker = f"## {section}"
        assert marker in prompt, f"Missing section: {section}"
        current_index = prompt.index(marker)
        assert current_index > last_index, f"Section out of order: {section}"
        last_index = current_index


def test_build_debrief_prompt_discourages_face_identification():
    prompt = build_debrief_prompt()

    assert "face identification" in prompt.lower() or "identify" in prompt.lower()
    assert "do not identify" in prompt.lower() or "avoid identifying" in prompt.lower()
    assert "literal" in prompt.lower()
    assert "observational" in prompt.lower()


def test_debrief_builder_custom_instructions_included():
    builder = DebriefPromptBuilder()
    prompt = builder.build()

    assert "Use only observable visual evidence" in prompt
    assert "Do not identify people" in prompt
    assert "confidence" in prompt.lower()


def test_debrief_builder_uses_requested_frameworks_and_analysis_type():
    builder = DebriefPromptBuilder()

    assert builder.builder.analysis_type == "full"
    assert builder.builder.frameworks == ["ekman", "fbi"]
    prompt = builder.build()
    assert "Ekman" in prompt or "FACS" in prompt
    assert "FBI" in prompt or "BAU" in prompt
