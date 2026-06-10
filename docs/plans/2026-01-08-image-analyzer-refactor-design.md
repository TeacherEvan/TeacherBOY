# Image Analyzer Agent Refactor Design

## Problem Statement

The `ImageAnalyzerAgent` (`src/agents/image_analyzer_agent.py`) is 1,483 lines and handles multiple responsibilities:
- Trigger phrase detection and session initiation
- Image download, base64 encoding, memory management
- Analysis mode selection (standard, debrief, scrape)
- Question handling and vision API calls
- Calendar integration with friend verification
- Rate limiting
- Response formatting and date extraction

It also duplicates significant logic with `ProfilerAgent`:
- Image download from LINE API
- Base64 encoding and memory cleanup
- Vision message building
- Rate limiting pattern
- Chat ID extraction
