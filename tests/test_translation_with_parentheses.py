"""Integration tests for translation with parenthesized text exclusion."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.services.google_translation import google_translation_service
from src.services.translation_service import translation_service


class TestGoogleTranslationWithParentheses:
    """Test Google Translation service with parenthesized text."""

    @pytest.mark.asyncio
    async def test_translate_with_single_parenthesis(self):
        """Test translation preserving single parenthesized name."""
        # Mock the API response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {
                "translations": [
                    {
                        "translatedText": "__PAREN_0__ มีวันหยุด",
                        "detectedSourceLanguage": "en"
                    }
                ]
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(google_translation_service, 'api_key', 'test_key'), \
             patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )
            
            # Test translation
            text = "(Pim) had the day off"
            result = await google_translation_service.translate(text, target_lang="th", source_lang="en")
            
            # Verify parenthesized text is preserved
            assert result == "(Pim) มีวันหยุด"
            assert "(Pim)" in result

    @pytest.mark.asyncio
    async def test_translate_with_multiple_parentheses(self):
        """Test translation preserving multiple parenthesized items."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {
                "translations": [
                    {
                        "translatedText": "__PAREN_0__ พบ __PAREN_1__ ที่ __PAREN_2__",
                        "detectedSourceLanguage": "en"
                    }
                ]
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(google_translation_service, 'api_key', 'test_key'), \
             patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )
            
            text = "(John) met (Jane) at (the park)"
            result = await google_translation_service.translate(text, target_lang="th", source_lang="en")
            
            # All parenthesized items should be preserved
            assert "(John)" in result
            assert "(Jane)" in result
            assert "(the park)" in result

    @pytest.mark.asyncio
    async def test_translate_text_without_parentheses(self):
        """Test that translation works normally without parentheses."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {
                "translations": [
                    {
                        "translatedText": "สวัสดีชาวโลก",
                        "detectedSourceLanguage": "en"
                    }
                ]
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(google_translation_service, 'api_key', 'test_key'), \
             patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )
            
            text = "Hello world"
            result = await google_translation_service.translate(text, target_lang="th", source_lang="en")
            
            assert result == "สวัสดีชาวโลก"

    @pytest.mark.asyncio
    async def test_translate_only_parentheses(self):
        """Test translation when text contains only parenthesized content."""
        # When text is only parentheses, it should return as-is without API call
        with patch.object(google_translation_service, 'api_key', 'test_key'):
            text = "(Pim)"
            result = await google_translation_service.translate(text, target_lang="th", source_lang="en")
            
            # Should return original text unchanged
            assert result == "(Pim)"


class TestLibreTranslationWithParentheses:
    """Test LibreTranslate service with parenthesized text."""

    @pytest.mark.asyncio
    async def test_translate_with_parenthesis(self):
        """Test LibreTranslate preserving parenthesized text."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "translatedText": "__PAREN_0__ มีวันหยุด"
        }
        mock_response.raise_for_status = MagicMock()

        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )
            
            text = "(Pim) had the day off"
            result = await translation_service.translate(text, source_lang="en", target_lang="th")
            
            # Verify parenthesized text is preserved
            assert result == "(Pim) มีวันหยุด"
            assert "(Pim)" in result

    @pytest.mark.asyncio
    async def test_translate_with_special_chars_in_parentheses(self):
        """Test translation with special characters in parentheses."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "translatedText": "__PAREN_0__ พบ __PAREN_1__"
        }
        mock_response.raise_for_status = MagicMock()

        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )
            
            text = "(Dr. Smith) met (Mr. O'Brien)"
            result = await translation_service.translate(text, source_lang="en", target_lang="th")
            
            # Special characters should be preserved
            assert "(Dr. Smith)" in result
            assert "(Mr. O'Brien)" in result

    @pytest.mark.asyncio
    async def test_translate_only_parentheses_libre(self):
        """Test LibreTranslate when text contains only parenthesized content."""
        text = "(Test Name)"
        result = await translation_service.translate(text, source_lang="en", target_lang="th")
        
        # Should return original text unchanged without making API call
        assert result == "(Test Name)"


class TestEndToEndTranslation:
    """End-to-end tests for the translation feature."""

    @pytest.mark.asyncio
    async def test_issue_example_pim(self):
        """Test the exact example from the GitHub issue."""
        # This test demonstrates the expected behavior for the issue:
        # Input: "(Pim) had the day off."
        # Expected: "(Pim)" should not be translated
        
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {
                "translations": [
                    {
                        "translatedText": "__PAREN_0__ มีวันหยุด",
                        "detectedSourceLanguage": "en"
                    }
                ]
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(google_translation_service, 'api_key', 'test_key'), \
             patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )
            
            # The exact input from the issue
            text = "(Pim) had the day off."
            result = await google_translation_service.translate(text, target_lang="th", source_lang="en")
            
            # Verify the name in parentheses is preserved
            assert "(Pim)" in result
            # Verify translation occurred (contains Thai text)
            assert "มีวันหยุด" in result
