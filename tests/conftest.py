"""Pytest configuration and fixtures for TeacherBOY tests."""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Set test environment variables BEFORE any imports
os.environ["LINE_CHANNEL_SECRET"] = "testsecret123"
os.environ["LINE_CHANNEL_ACCESS_TOKEN"] = "testtoken456"
os.environ["DEBUG"] = "false"

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

# Now import and patch settings at module level
from src.config import settings

settings.line_channel_secret = "testsecret123"
settings.line_channel_access_token = "testtoken456"


@pytest.fixture(autouse=True)
def mock_settings():
    """Mock settings for all tests."""
    with patch("src.main.settings") as mock:
        mock.line_channel_secret = "testsecret123"
        mock.line_channel_access_token = "testtoken456"
        mock.debug = False
        mock.is_google_translate_configured.return_value = False
        yield mock
