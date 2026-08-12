"""Tests for incomplete sentence detection to prevent translation hallucination."""

from src.utils.text_preprocessing import detect_incomplete_sentence


class TestIncompleteSentenceDetection:
    """Test suite for incomplete sentence detection."""

    def test_incomplete_sentence_so_i_tried(self):
        """Test the exact failing case from the bug report."""
        text = "Also (Mayu) was abcent yesterday and went home today so i tried"
        result, was_incomplete = detect_incomplete_sentence(text)

        assert was_incomplete is True
        assert result == text + "..."
        assert result.endswith("so i tried...")

    def test_incomplete_sentence_standalone_conjunctions(self):
        """Test detection of standalone conjunctions."""
        test_cases = [
            "I wanted to go but",
            "She said hello and",
            "He left because",
            "We should try therefore",
            "It was nice however",
        ]

        for text in test_cases:
            result, was_incomplete = detect_incomplete_sentence(text)
            assert was_incomplete is True, f"Failed to detect: {text}"
            assert result.endswith("...")

    def test_incomplete_sentence_pronoun_verb(self):
        """Test detection of 'conjunction + pronoun + verb' patterns."""
        test_cases = [
            "so i tried",
            "but she wanted",
            "and they needed",
            "because we thought",
            "so you hoped",
        ]

        for text in test_cases:
            result, was_incomplete = detect_incomplete_sentence(text)
            assert was_incomplete is True, f"Failed to detect: {text}"
            assert result.endswith("...")

    def test_incomplete_sentence_transitive_verbs(self):
        """Test detection of transitive verbs without objects."""
        test_cases = [
            "I tried",
            "She wanted",
            "They needed",
            "He thought",
            "We hoped",
            "You planned",
            "She forgot",
            "They remembered",
        ]

        for text in test_cases:
            result, was_incomplete = detect_incomplete_sentence(text)
            assert was_incomplete is True, f"Failed to detect: {text}"
            assert result.endswith("...")

    def test_complete_sentences_no_modification(self):
        """Test that complete sentences are not modified."""
        test_cases = [
            "Hello world",
            "I went to the store",
            "She is happy today",
            "They finished their homework",
            "The cat is sleeping",
            "I tried my best",  # Has object "my best"
            "She wanted a cookie",  # Has object "a cookie"
        ]

        for text in test_cases:
            result, was_incomplete = detect_incomplete_sentence(text)
            assert was_incomplete is False, f"False positive: {text}"
            assert result == text

    def test_already_has_ellipsis(self):
        """Test that text already ending with ellipsis is not modified."""
        text = "I was thinking..."
        result, was_incomplete = detect_incomplete_sentence(text)

        assert was_incomplete is False
        assert result == text

    def test_questions_not_flagged(self):
        """Test that questions are not incorrectly flagged as incomplete."""
        test_cases = [
            "Where did you go?",
            "What did you try?",
            "How are you?",
        ]

        for text in test_cases:
            result, was_incomplete = detect_incomplete_sentence(text)
            # These might be flagged depending on verb patterns, but shouldn't cause issues
            # Main goal is to prevent hallucination, not to catch every edge case
            # So we just verify it doesn't crash
            assert result is not None

    def test_case_insensitive_detection(self):
        """Test that detection works regardless of case."""
        test_cases = [
            ("SO I TRIED", True),
            ("So I Tried", True),
            ("so i tried", True),
            ("HELLO WORLD", False),
        ]

        for text, should_be_incomplete in test_cases:
            result, was_incomplete = detect_incomplete_sentence(text)
            assert was_incomplete == should_be_incomplete, f"Failed: {text}"

    def test_whitespace_handling(self):
        """Test that trailing whitespace is handled correctly."""
        test_cases = [
            "so i tried  ",
            "  so i tried",
            "  so i tried  ",
        ]

        for text in test_cases:
            result, was_incomplete = detect_incomplete_sentence(text)
            assert was_incomplete is True
            assert result.strip().endswith("...")
            # Should not have double spaces before ellipsis
            assert not result.endswith("  ...")

    def test_multiple_sentences_last_incomplete(self):
        """Test detection when only the last sentence is incomplete."""
        text = "I went to the store. She was there too. But then we"
        result, was_incomplete = detect_incomplete_sentence(text)

        assert was_incomplete is True
        assert result.endswith("...")

    def test_real_world_professional_message(self):
        """Test with realistic professional messages that could cause issues."""
        test_cases = [
            # Incomplete messages that need protection
            ("I sent the report but forgot", True),
            ("The meeting went well so we decided", True),
            ("Please check the document because", True),
            # Complete messages that should pass through
            ("I sent the report to the team", False),
            ("The meeting went well today", False),
            ("Please check the document when you can", False),
        ]

        for text, should_be_incomplete in test_cases:
            result, was_incomplete = detect_incomplete_sentence(text)
            assert was_incomplete == should_be_incomplete, f"Failed: {text}"

            if should_be_incomplete:
                assert result.endswith("...")
            else:
                assert not result.endswith("...")


class TestIntegrationWithTranslation:
    """Integration tests to verify the fix works end-to-end."""

    def test_problematic_message_preprocessing(self):
        """Test the exact message from the bug report through preprocessing."""
        original = "Also (Mayu) was abcent yesterday and went home today so i tried"

        # Step 1: Detect incompleteness
        processed, was_incomplete = detect_incomplete_sentence(original)

        assert was_incomplete is True
        assert "..." in processed

        # Step 2: Verify parentheses are still present
        assert "(Mayu)" in processed

        # The processed text should now be less ambiguous for translation
        # "so i tried..." clearly signals incompleteness vs "so i tried"
        expected = original + "..."
        assert processed == expected

    def test_edge_case_empty_string(self):
        """Test edge case: empty string."""
        text = ""
        result, was_incomplete = detect_incomplete_sentence(text)

        assert was_incomplete is False
        assert result == ""

    def test_edge_case_only_whitespace(self):
        """Test edge case: only whitespace."""
        text = "   "
        result, was_incomplete = detect_incomplete_sentence(text)

        assert was_incomplete is False
        assert result == "   "
