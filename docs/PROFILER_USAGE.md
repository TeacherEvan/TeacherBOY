# Psychological Profiler - User Guide

## Overview

The Ms. Green Psychological Profiler analyzes photos and artwork using advanced vision AI (Gemini 2.5 Flash primary, with fallback chain) to provide comprehensive behavioral and psychological assessments based on established frameworks:

- **FBI Behavioral Analysis Unit (BAU)** methodology
- **Paul Ekman's FACS** (Facial Action Coding System) and 7 universal emotions
- **Joe Navarro's body language** principles (FBI-trained)
- **Color psychology** and environmental analysis

### Supported Content Types

- **Real Photographs**: Standard psychological profiling for actual persons
- **Fictional Artwork**: Character design analysis for anime, manga, illustrations, pencil drawings, concept art
- **Creative Projects**: Art direction support for music videos, storytelling, and visual narratives
- **Accessibility**: Assists neurodivergent users (autism) with understanding character expressions in art

⚠️ **DISCLAIMER**: For educational, entertainment, and creative purposes
only. NOT for professional psychological assessments, hiring decisions, or
legal judgments.

## How to Use (Trigger-Based Workflow)

### Step 1: Send Trigger Phrase

First, send one of these trigger phrases to activate profiling mode:

- `Ms. Green profile`
- `profile this`
- `analyze this image`
- `analyze this photo`
- `analyze image`
- `analyze photo`
- `profile image`
- `profile photo`

**Example:**

```text
User: Ms. Green profile
Ms. Green: 🔬 Ready to analyze!

Please send the image you want me to profile.
(You have 60 seconds)

พร้อมวิเคราะห์! กรุณาส่งรูปภาพ
```

### Step 2: Send Image

Within 60 seconds, send the image you want analyzed.

Ms. Green will:

1. Send "🔬 Analyzing image... Please wait." message
2. Download the image from LINE
3. Send it to Vision AI API (Gemini primary, fallback chain) for comprehensive analysis
4. Return detailed psychological profile

## Example Analysis Output

```text
⚡ MS. GREEN PSYCHOLOGICAL PROFILER ⚡
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## 🎯 SUBJECT IDENTIFICATION
- Single subject, adult male, approximately 30-40 years
- Professional business attire

## 😊 FACIAL EXPRESSION ANALYSIS (Ekman Framework)
- **Primary Emotion**: Confidence (60%)
- **Intensity**: Medium
- **Authenticity**: Genuine expression
- **Microexpression Indicators**: None detected

## 👁️ EYE ANALYSIS
- **Gaze Direction**: Direct camera contact
- **Eye Contact Quality**: Engaged, confident
- **Pupil/Tension Indicators**: Relaxed, no stress indicators

...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ For entertainment only. Not professional advice.
```

## Rate Limits

**Regular Users:**

- 3 analyses per hour per chat
- Prevents excessive API costs

**Admins:**

- Unlimited analyses (bypass rate limit)

## Configuration

Edit `.env` to customize:

```env
# Enable/disable feature
PROFILER_ENABLED=true

# Vision model (must support images/vision)
# Primary: Gemini free tier
PROFILER_MODEL=gemini-2.5-flash

# Analysis depth
PROFILER_ANALYSIS_TYPE=full  # Options: full, quick, body, facial

# Rate limiting
PROFILER_RATE_LIMIT_PER_HOUR=3

# Max image size
PROFILER_MAX_IMAGE_SIZE_MB=10.0
```

## Session Management

- **Session Duration**: 60 seconds after trigger phrase
- **Session Expiration**: If no image sent within 60 seconds, session expires
- **Session Cleanup**: Automatically cleared after successful analysis or error
- **Group Chat Safety**: In groups, only the person who sent the trigger can send the image

## Technical Details

### Frameworks Used

#### 1. Paul Ekman's 7 Universal Emotions

- Happiness
- Sadness
- Fear
- Anger
- Surprise
- Disgust
- Contempt

#### 2. FBI BAU Methodology

- Victimology/subject assessment
- Behavioral indicators
- Cognitive load indicators
- Social dynamics

#### 3. Joe Navarro's Body Language

- Limbic system responses (freeze/flight/fight)
- Feet and legs (most honest body part)
- Torso displays
- Arm and hand behaviors
- Neck and shoulder tells
- Facial tells

#### 4. Color Psychology

- Clothing color significance
- Environmental color analysis
- Color combination patterns

### API Requirements

**Vision AI (Required):**
- **Primary:** Google AI Studio free tier — [Gemini](https://aistudio.google.com/)
- Create API key at Google AI Studio
- Set `GEMINI_API_KEY` or `GOOGLE_API_KEY` in `.env`
- **Fallback chain:** OpenRouter (free models), Hermes, HF Inference, Ollama

**Model:**
- Default: `gemini-2.5-flash` (supports vision)
- Alternative: `gemini-2.0-flash` (faster)

## Troubleshooting

### "Vision AI not configured"

→ Set `GEMINI_API_KEY` or `GOOGLE_API_KEY` in `.env` with valid Google AI Studio API key

### "Profiler not responding to images"

→ Make sure you sent a trigger phrase first (within last 60 seconds)

### "Rate limit exceeded"

→ Wait 1 hour or contact admin for unlimited access

### "Image too large"

→ Compress image to under 10 MB (configurable via `PROFILER_MAX_IMAGE_SIZE_MB`)

### "Safety features obscuring content"

→ The profiler now includes context for fictional artwork analysis. If faces are still blurred:

- Ensure the image is clearly artistic (anime/manga style, pencil drawing, etc.)
- The model will analyze visible artistic elements even if some features are obscured
- For creative projects, mention "character design for [project name]" in your analysis request

## Privacy & Ethics

**Data Handling:**

- Images are NOT stored locally
- Images are sent to Vision AI API (Gemini primary, fallback chain) for analysis
- Analysis text is returned but not permanently logged
- No facial recognition database is created

**Ethical Use:**

- ✅ **Recommended Uses**:
  - Fictional character analysis for creative projects
  - Art direction for music videos and visual storytelling
  - Accessibility support for neurodivergent creators
  - Educational study of behavioral psychology frameworks
  - Personal entertainment and learning

- ❌ **Prohibited Uses**:
  - Making hiring/firing decisions
  - Legal judgments or court evidence
  - Medical/clinical diagnoses
  - Surveillance without consent
  - Real person profiling without explicit permission

**Consent:**

- **Real Persons**: Always obtain explicit consent before analyzing someone's photo
- **Fictional Art**: No consent needed for artwork analysis (characters are not real persons)
- Respect privacy and personal boundaries in all contexts

## Developer Notes

**Session Manager:**

- Located in `src/services/profiler_session_manager.py`
- Tracks `{chat_id: (user_id, timestamp)}` state
- Cleanup happens on analysis completion or error

**Agent Priority:**

- Priority 7 (after admin/help, before search/LLM)
- Handles both text triggers and images with active sessions

**Testing:**

- Run `pytest tests/test_profiler_agent.py` (23 tests)
- Mock session manager for unit tests
- Integration tests cover full trigger → image workflow

## Use Cases

### Creative Projects

**Music Video Character Design:**

```text
User: Ms. Green profile
Ms. Green: 🔬 Ready to analyze!

User: [sends Viking character sketch]
Ms. Green: [Analyzes facial expression, posture, armor design, color psychology]
```

**Accessibility Support:**

- Users with autism can get detailed breakdowns of character emotions
- Helps understand subtle facial expressions in artwork
- Assists with art direction decisions for storytelling

**Art Direction:**

- Validate character design choices
- Ensure emotions read correctly in illustrations
- Compare different character poses/expressions

---

**Last Updated**: January 2026  
**Version**: 1.1.0 (Fictional artwork analysis + accessibility support)
