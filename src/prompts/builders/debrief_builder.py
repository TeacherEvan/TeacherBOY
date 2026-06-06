"""Structured image debrief prompt builder.

This builder creates a professional, observational debrief prompt for image
analysis using the shared VisionPromptBuilder infrastructure.
"""

from src.prompts.builders.vision_builder import VisionPromptBuilder

DEBRIEF_SECTIONS = [
    "SCENE OVERVIEW",
    "SUBJECTS",
    "EXPRESSION & BODY LANGUAGE",
    "OBJECTS & TEXT",
    "LIGHTING & IMAGE QUALITY",
    "COMPOSITION",
    "CONFIDENCE & LIMITATIONS",
]


DEBRIEF_CUSTOM_INSTRUCTIONS = """
Use only observable visual evidence. Keep the response literal, neutral, and professional.
Do not identify people, infer names, or speculate about identity.
Avoid face identification; describe visible features and expressions only.
If a detail is unclear, say so directly.

Output format requirements:
- Use exactly the section headings below, in this order.
- Provide concise bullet points under each heading.
- Do not add extra headings or a conclusion outside the listed sections.
- Keep all statements grounded in visible evidence.

Required sections:
1. SCENE OVERVIEW
2. SUBJECTS
3. EXPRESSION & BODY LANGUAGE
4. OBJECTS & TEXT
5. LIGHTING & IMAGE QUALITY
6. COMPOSITION
7. CONFIDENCE & LIMITATIONS
""".strip()


class DebriefPromptBuilder:
    """Builder for structured, observational image debrief prompts."""

    def __init__(self):
        self.builder = (
            VisionPromptBuilder()
            .set_analysis_type("full")
            .add_framework("ekman")
            .add_framework("fbi")
            .add_custom_instructions(DEBRIEF_CUSTOM_INSTRUCTIONS)
        )

    def build(self, document_text: str | None = None) -> str:
        """Build the final debrief prompt."""
        if document_text:
            intro = (
                "You are a teaching assistant analyzing a lesson document or journal text.\n"
                "Extract the following fields STRICTLY as a valid JSON object. Do not include markdown formatting or explanations.\n"
                "If a field cannot be determined from the text, return an empty list or null where appropriate.\n\n"
                "Fields:\n"
                '- "topics_covered": (list of strings)\n'
                '- "comprehension_level": (string) "low", "medium", or "high"\n'
                '- "key_phrases_learned": (list of strings)\n'
                '- "suggested_review": (list of strings)\n'
                '- "confidence_score": (float) 0-1\n'
                '- "notes": (string or null)\n\n'
                f"Document text:\n{document_text}\n"
            )
            return intro

        intro = "Analyze the image below using a structured debrief format."
        frameworks_section = "\n\n".join(self.builder._framework_content)
        instructions = self.builder._build_instructions()
        ethics = self.builder._build_ethics_note()

        section_block = "\n\n".join(f"## {section}" for section in DEBRIEF_SECTIONS)

        return f"{intro}\n\n{frameworks_section}\n\n{instructions}\n\n{section_block}\n\n{ethics}"


def build_debrief_prompt() -> str:
    """Convenience helper for building the debrief prompt."""
    return DebriefPromptBuilder().build()
