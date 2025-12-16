"""Tests for text preprocessing utilities."""

import pytest
from src.utils.text_preprocessing import (
    extract_parenthesized_text,
    restore_parenthesized_text,
    is_only_parenthesized_content,
)


class TestTextPreprocessing:
    """Test cases for text preprocessing utilities."""

    def test_extract_single_parenthesis(self):
        """Test extracting a single parenthesized item."""
        text = "(Pim) had the day off."
        processed, extracted = extract_parenthesized_text(text)
        
        assert processed == "__PAREN_0__ had the day off."
        assert extracted == ["(Pim)"]

    def test_extract_multiple_parentheses(self):
        """Test extracting multiple parenthesized items."""
        text = "(John) met (Jane) at the (park)."
        processed, extracted = extract_parenthesized_text(text)
        
        assert processed == "__PAREN_0__ met __PAREN_1__ at the __PAREN_2__."
        assert extracted == ["(John)", "(Jane)", "(park)"]

    def test_extract_no_parentheses(self):
        """Test text without any parentheses."""
        text = "Hello world"
        processed, extracted = extract_parenthesized_text(text)
        
        assert processed == "Hello world"
        assert extracted == []

    def test_extract_empty_parentheses(self):
        """Test empty parentheses."""
        text = "Test () text"
        processed, extracted = extract_parenthesized_text(text)
        
        assert processed == "Test __PAREN_0__ text"
        assert extracted == ["()"]

    def test_extract_nested_parentheses_not_supported(self):
        """Test that nested parentheses are handled (innermost only)."""
        text = "Test (outer (inner)) text"
        processed, extracted = extract_parenthesized_text(text)
        
        # Simple regex only matches innermost non-nested parentheses
        # So (inner) gets extracted, leaving (outer __PAREN_0__)
        assert len(extracted) == 1
        assert "(inner)" in extracted
        assert "outer" in processed
        # This is expected behavior for simple use cases

    def test_extract_parentheses_with_special_chars(self):
        """Test parentheses containing special characters."""
        text = "(Dr. Smith) and (Mr. O'Brien) met."
        processed, extracted = extract_parenthesized_text(text)
        
        assert processed == "__PAREN_0__ and __PAREN_1__ met."
        assert extracted == ["(Dr. Smith)", "(Mr. O'Brien)"]

    def test_extract_parentheses_with_numbers(self):
        """Test parentheses containing numbers."""
        text = "The result (42) is correct."
        processed, extracted = extract_parenthesized_text(text)
        
        assert processed == "The result __PAREN_0__ is correct."
        assert extracted == ["(42)"]

    def test_restore_single_parenthesis(self):
        """Test restoring a single parenthesized item."""
        text = "__PAREN_0__ มีวันหยุด"
        extracted = ["(Pim)"]
        restored = restore_parenthesized_text(text, extracted)
        
        assert restored == "(Pim) มีวันหยุด"

    def test_restore_multiple_parentheses(self):
        """Test restoring multiple parenthesized items."""
        text = "__PAREN_0__ พบ __PAREN_1__ ที่ __PAREN_2__"
        extracted = ["(John)", "(Jane)", "(park)"]
        restored = restore_parenthesized_text(text, extracted)
        
        assert restored == "(John) พบ (Jane) ที่ (park)"

    def test_restore_no_placeholders(self):
        """Test restoring when there are no placeholders."""
        text = "Hello world"
        extracted = []
        restored = restore_parenthesized_text(text, extracted)
        
        assert restored == "Hello world"

    def test_roundtrip_preservation(self):
        """Test that extract and restore preserve the original structure."""
        original = "(Pim) had the day off and saw (Tom) at (home)."
        
        # Extract
        processed, extracted = extract_parenthesized_text(original)
        
        # Simulate translation (just returning the same processed text)
        translated = processed
        
        # Restore
        restored = restore_parenthesized_text(translated, extracted)
        
        # Should maintain parentheses in their original positions
        assert "(Pim)" in restored
        assert "(Tom)" in restored
        assert "(home)" in restored

    def test_extract_with_thai_text(self):
        """Test extraction with Thai text inside parentheses."""
        text = "(สวัสดี) Hello (ครับ)"
        processed, extracted = extract_parenthesized_text(text)
        
        assert processed == "__PAREN_0__ Hello __PAREN_1__"
        assert extracted == ["(สวัสดี)", "(ครับ)"]

    def test_extract_with_unicode(self):
        """Test extraction with various Unicode characters."""
        text = "(日本語) and (한국어) text"
        processed, extracted = extract_parenthesized_text(text)
        
        assert processed == "__PAREN_0__ and __PAREN_1__ text"
        assert extracted == ["(日本語)", "(한국어)"]

    def test_identical_parenthesized_text(self):
        """Test handling of identical parenthesized text appearing multiple times."""
        text = "(test) is different from (test)"
        processed, extracted = extract_parenthesized_text(text)
        
        # Should extract both instances
        assert extracted == ["(test)", "(test)"]
        assert processed == "__PAREN_0__ is different from __PAREN_1__"
        
        # Restore should work correctly
        restored = restore_parenthesized_text(processed, extracted)
        assert restored == text


class TestIsOnlyParenthesizedContent:
    """Test cases for is_only_parenthesized_content helper."""

    def test_only_parentheses(self):
        """Test text with only parenthesized content."""
        processed = "__PAREN_0__"
        extracted = ["(Name)"]
        assert is_only_parenthesized_content(processed, extracted) is True

    def test_multiple_parentheses_only(self):
        """Test text with multiple parentheses and whitespace."""
        processed = "__PAREN_0__ __PAREN_1__"
        extracted = ["(First)", "(Second)"]
        assert is_only_parenthesized_content(processed, extracted) is True

    def test_parentheses_with_text(self):
        """Test text with parentheses and actual content."""
        processed = "__PAREN_0__ had the day off"
        extracted = ["(Pim)"]
        assert is_only_parenthesized_content(processed, extracted) is False

    def test_empty_text(self):
        """Test empty text."""
        assert is_only_parenthesized_content("", []) is True

    def test_whitespace_only(self):
        """Test text with only whitespace."""
        assert is_only_parenthesized_content("   ", []) is True

    def test_text_no_parentheses(self):
        """Test text without any parentheses."""
        processed = "Hello world"
        extracted = []
        assert is_only_parenthesized_content(processed, extracted) is False
