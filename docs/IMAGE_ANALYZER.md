# Image Analyzer - User Guide

## Overview

The Ms. Green Image Analyzer allows you to submit images and ask general questions about them. Unlike the Psychological Profiler (which focuses on behavioral analysis), this agent handles practical image-based questions like:

- "What's on this menu?"
- "What does this sign say?"
- "What products are shown here?"
- "Translate this text from the image"

## How to Use (Trigger-Based Workflow)

### Step 1: Send Trigger Phrase

First, send one of these trigger phrases to activate the image analyzer:

- `Ms. Green analyze`
- `Ms. Green analyze this`
- `analyze image`
- `analyze this`
- `analyze this image`
- `analyze photo`
- `examine this photo`
- `examine image`

**Example:**

```
User: Ms. Green analyze
Ms. Green: 📷 Please send the image you'd like me to analyze (60 seconds)
```

### Step 2: Send Image

Within 60 seconds, send the image you want analyzed.

Ms. Green will:
1. Download the image from LINE
2. Store it and ask: "What would you like to do?"
3. Present **Quick Reply buttons** for common actions

### Step 3: Choose Action (Quick Reply Buttons)

Ms. Green shows three Quick Reply buttons:

| Button | Action | Description |
|--------|--------|-------------|
| 🔍 **Analyze** | `Analyze this` | General image Q&A — ask any question |
| 📝 **Scrape** | `Scrape this` | Extract text/data from image |
| 📖 **Generate Debrief** | `M` | Structured daily debrief extraction |

**Or** type your own question directly — the bot will treat it as an analysis question.

### Step 4: Get Your Answer

- If you tapped **🔍 Analyze**: Type your question (e.g., "What dishes are vegetarian?")
- If you tapped **📝 Scrape**: Bot extracts text/data automatically
- If you tapped **📖 Generate Debrief**: Bot runs structured debrief extraction

## Alternative: Bare `analyze` Trigger (New/Last Choice)

If you send just `analyze` or `Ms. Green analyze` (without "this"), Ms. Green will ask:

> **New or Last** — with Quick Reply buttons:
> - **New** — Send a new image
> - **Last** — Use the most recently analyzed image in this chat

This is useful when you want to ask multiple questions about the same image.

## Calendar Integration

When dates are detected in an image (schedules, announcements, event flyers, etc.), the agent can offer to add them to your calendar with reminders.

**Example:**

```
User: Ms. Green analyze [sends event flyer]
Ms. Green: [Analysis response]
      📅 I detected 2 dates:
      1. 2026-07-15: Summer Festival
      2. 2026-08-01: Workshop
      Add to calendar?
User: yes
Ms. Green: [Starts add flow for each date]
```

## Rate Limits

**Regular Users:**
- 5 analyses per hour per chat

**Admins:**
- Unlimited analyses (bypass rate limit)

## Configuration

Edit `.env` to customize:

```env
# Enable/disable feature (uses vision AI via fallback chain)
# Primary: Gemini free tier (GEMINI_API_KEY or GOOGLE_API_KEY)
# Fallback: OpenRouter, Hermes, HF Inference, Ollama
GEMINI_API_KEY=your_gemini_api_key_here

# Vision model (must support images/vision)
# Default: gemini-2.5-flash (supports vision)
# Alternative: gemini-2.0-flash (faster)
# GEMINI_VISION_MODEL=gemini-2.5-flash
```

## Supported Content Types

- **Photos**: Real-world photographs
- **Screenshots**: App screens, web pages
- **Documents**: Scanned documents, receipts, menus
- **Signs**: Street signs, store signs, informational signs
- **Product images**: Labels, packaging
- **Charts/Graphs**: Data visualizations

## Session Management

- **Session Duration**: 60 seconds after trigger for image upload, then continues until question answered
- **Session Expiration**: If no image sent within 60 seconds, session expires
- **Group Chat Safety**: In groups, only the person who sent the trigger can send the image

## Example Output

```
⚡ MS. GREEN OBSERVES ⚡
━━━━━━━━━━━━━━━━━━━━━━━

Based on the image you sent, I can see:

🍽️ **Menu Analysis**
This appears to be a Thai restaurant menu with 12 dishes.

**Vegetarian Options:**
1. ผัดผัก (Stir-fried vegetables) - 80 THB
2. แกงเขียวหวานผัก (Green curry vegetables) - 120 THB
3. ส้มตำมะม่วง (Mango salad) - 90 THB

**Spicy Dishes (marked with 🌶️):**
- Tom Yum Goong 🌶️🌶️
- Pad Thai 🌶️
- Green Curry 🌶️🌶️

**Recommendations for Westerners:**
- Pad Thai (classic, customizable spice)
- Fried Rice (safe choice)
- Mango Sticky Rice (dessert)

Would you like me to translate any specific dish descriptions?
```

## Technical Details

### API Requirements

**Vision AI (Required):**
- **Primary:** Google AI Studio free tier — [Gemini](https://aistudio.google.com/)
- Create API key at Google AI Studio
- Set `GEMINI_API_KEY` or `GOOGLE_API_KEY` in `.env`
- **Fallback chain:** OpenRouter (free models), Hermes, HF Inference, Ollama

**Model:**
- Default: `gemini-2.5-flash` (supports vision)
- Alternative: `gemini-2.0-flash` (faster)

### Agent Priority

- **Priority 7** (after Profiler, before Search/LLM)
- Handles both text triggers and images with active sessions

### Files

- `src/agents/image_analyzer_agent.py` - Main agent logic
- `src/services/image_analyzer_session_manager.py` - Session state tracking
- `tests/test_image_analyzer_*.py` - Test suite

## Troubleshooting

### "Vision AI not configured"
→ Set `GEMINI_API_KEY` or `GOOGLE_API_KEY` in `.env` with valid Google AI Studio API key

### "Image Analyzer not responding to images"
→ Make sure you sent a trigger phrase first (within last 60 seconds)

### "Rate limit exceeded"
→ Wait 1 hour or contact admin for unlimited access

### "Image too large"
→ Compress image to under 20 MB (LINE limit)

## Privacy & Ethics

**Data Handling:**
- Images are NOT stored locally
- Images are sent to Vision AI API (Gemini primary, fallback chain) for analysis
- Analysis text is returned but not permanently logged
- No image database is created

**Appropriate Uses:**
- ✅ Menu translation and food identification
- ✅ Sign/document translation
- ✅ Product label reading
- ✅ Schedule/event extraction for calendar
- ✅ General visual Q&A

**Inappropriate Uses:**
- ❌ Real person profiling without consent
- ❌ Private document analysis without permission
- ❌ Surveillance or monitoring

## Related Documentation

- [Psychological Profiler](PROFILER_USAGE.md) - For behavioral analysis of photos
- [Calendar & Reminders](CALENDAR_REMINDERS.md) - For adding detected dates to calendar
- [Quick Reference](reference/quick-reference.md) - Command summary

---

**Last Updated**: June 2026  
**Version**: 2.0.0 (Quick Reply flow)