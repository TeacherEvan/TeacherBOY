"""Tests for the shared LINE-safe text splitter.

These tests are the regression net for the "profiler report is truncated"
defect: the splitter must NEVER lose content, no matter how the input is
shaped (no paragraphs, one giant line, one giant word, empty input).
"""

import pytest

from src.utils.text_split import LINE_PART_CHARS, split_sentences, split_text


class TestSplitSentences:
    """Tests for the sentence splitter."""

    def test_splits_on_terminators(self):
        result = split_sentences("One. Two! Three?")
        assert len(result) == 3

    def test_preserves_all_characters(self):
        text = "First one. Second one!  Third one? Tail without terminator"
        assert "".join(split_sentences(text)) == text

    def test_empty_input(self):
        assert split_sentences("") == []

    def test_does_not_split_decimals(self):
        text = "The score was 3.5 points overall."
        assert "".join(split_sentences(text)) == text
        assert len(split_sentences(text)) == 1


class TestSplitText:
    """Tests for the main chunking function."""

    def test_short_text_is_single_chunk(self):
        assert split_text("hello world") == ["hello world"]

    def test_empty_text(self):
        assert split_text("") == []

    def test_whitespace_only_text_yields_no_chunks(self):
        """The early-exit path and the general path must agree."""
        for text in (" ", "   ", "\n\n\n", "\t"):
            assert split_text(text) == [], text
            assert split_text(text, 3) == [], text

    def test_exact_boundary_is_not_split(self):
        text = "x" * 100
        assert split_text(text, 100) == [text]

    def test_exact_boundary_preserves_trailing_whitespace(self):
        """A chunk of exactly ``max_length`` must be returned byte-for-byte.

        The general path strips trailing whitespace, so the early-exit path
        has to agree with it — otherwise a report silently loses its final
        newline depending on its length.
        """
        text = "x" * 99 + "\n"
        assert split_text(text, 100) == [text]
        assert split_text(text + " ", 101) == [text + " "]

    def test_one_over_boundary_is_split(self):
        text = "x" * 101
        parts = split_text(text, 100)
        assert len(parts) == 2
        assert "".join(parts) == text

    def test_long_paragraph_is_split_on_sentences(self):
        paragraph = "This is a sentence about profiling. " * 20
        parts = split_text(paragraph, 200)
        assert len(parts) > 1
        assert all(len(p) <= 200 for p in parts)
        # No content lost (whitespace at chunk edges may be trimmed).
        assert "".join(parts).replace(" ", "") == paragraph.replace(" ", "")

    def test_giant_single_word_is_hard_split(self):
        text = "y" * 1000
        parts = split_text(text, 300)
        assert len(parts) == 4
        assert "".join(parts) == text

    def test_mixed_paragraphs_preserve_content(self):
        text = "## SECTION ONE\n\n" + "Detail line. " * 30 + "\n\n## SECTION TWO\n\n" + "More detail. " * 30
        parts = split_text(text, 400)
        assert len(parts) > 1
        assert all(len(p) <= 400 for p in parts)
        assert "SECTION ONE" in "".join(parts)
        assert "SECTION TWO" in "".join(parts)

    def test_never_returns_empty_parts(self):
        text = "\n\n\n" + "content " * 100
        parts = split_text(text, 150)
        assert all(p.strip() for p in parts)

    def test_default_limit_is_line_part_chars(self):
        text = "z" * (LINE_PART_CHARS + 500)
        parts = split_text(text)
        assert all(len(p) <= LINE_PART_CHARS for p in parts)
        assert "".join(parts) == text

    @pytest.mark.parametrize("length", [1, 99, 100, 101, 999, 1000, 4380, 4381, 4500])
    def test_content_is_never_lost(self, length):
        """M2 (zero/empty degeneracy) + M1 (boundary flip) sweep."""
        text = "abc" * length
        parts = split_text(text, 200)
        assert "".join(parts) == text
        assert all(len(p) <= 200 for p in parts)
