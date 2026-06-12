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
1. Send "📷 Analyzing image... Please wait." message
2. Download the image from LINE
3. Send it to GPT-4o vision API for analysis
4. Ask: "What would you like to know about this image?"

### Step 3: Ask Your Question

Send your question about the image. Ms. Green will analyze and respond.

**Example:**

```
User: Ms. Green analyze
Ms. Green: 📷 Please send the image you'd like me to analyze (60 seconds)

User: [sends photo of a Thai menu]
Ms. Green: 📷 Analyzing image... Please wait.
Ms. Green: What would you like to know about this image?

User: What dishes are vegetarian?
Ms. Green: Based on the menu image, here are the vegetarian options...
```

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
# Enable/disable feature (requires GitHub Models)
# GitHub Models is required for vision AI
GITHUB_MODELS_PAT=your_github_pat_here

# Vision model (must support images)
# Default: openai/gpt-4o
# Alternative: openai/gpt-4o-mini (faster, less detailed)
# GITHUB_MODELS_DEFAULT_MODEL=openai/gpt-4o
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
📷 IMAGE ANALYSIS RESULT
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

**GitHub Models (Required):**
- Free tier: [GitHub Models](https://github.com/marketplace/models)
- Create GitHub PAT with `models:read` scope
- Set `GITHUB_MODELS_PAT` in `.env`

**Model:**
- Default: `openai/gpt-4o` (supports vision)
- Alternative: `openai/gpt-4o-mini` (faster, less detailed)

### Agent Priority

- Priority 7 (after Admin/Help, before Search/LLM)
- Handles both text triggers and images with active sessions

### Files

- `src/agents/image_analyzer_agent.py` - Main agent logic
- `src/services/image_analyzer_session_manager.py` - Session state tracking
- `tests/test_image_analyzer_*.py` - Test suite

## Troubleshooting

### "Image Analyzer: GitHub Models not configured"
→ Set `GITHUB_MODELS_PAT` in `.env` with valid GitHub PAT

### "Image Analyzer not responding to images"
→ Make sure you sent a trigger phrase first (within last 60 seconds)

### "Rate limit exceeded"
→ Wait 1 hour or contact admin for unlimited access

### "Image too large"
→ Compress image to under 20 MB (LINE limit)

## Privacy & Ethics

**Data Handling:**
- Images are NOT stored locally
- Images are sent to GitHub Models API for analysis
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
- [Quick Reference](../reference/quick-reference.md) - Command summary

---

**Last Updated**: June 2026  
**Version**: 1.0.0