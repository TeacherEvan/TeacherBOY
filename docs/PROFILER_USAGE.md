# Psychological Profiler - User Guide

## Overview

The Zeus Psychological Profiler analyzes photos using advanced vision AI (GPT-4o) to provide comprehensive behavioral and psychological assessments based on established frameworks:

- **FBI Behavioral Analysis Unit (BAU)** methodology
- **Paul Ekman's FACS** (Facial Action Coding System) and 7 universal emotions
- **Joe Navarro's body language** principles (FBI-trained)
- **Color psychology** and environmental analysis

⚠️ **DISCLAIMER**: For educational and entertainment purposes only. NOT for professional psychological assessments, hiring decisions, or legal judgments.

## How to Use (Trigger-Based Workflow)

### Step 1: Send Trigger Phrase

First, send one of these trigger phrases to activate profiling mode:

- `zeus profile`
- `profile this`
- `analyze this image`
- `analyze this photo`
- `analyze image`
- `analyze photo`
- `profile image`
- `profile photo`

**Example:**
```
User: zeus profile
Zeus: 🔬 Ready to analyze!

Please send the image you want me to profile.
(You have 60 seconds)

พร้อมวิเคราะห์! กรุณาส่งรูปภาพ
```

### Step 2: Send Image

Within 60 seconds, send the image you want analyzed.

Zeus will:
1. Send "🔬 Analyzing image... Please wait." message
2. Download the image from LINE
3. Send it to GPT-4o vision API for comprehensive analysis
4. Return detailed psychological profile

## Example Analysis Output

```
⚡ ZEUS PSYCHOLOGICAL PROFILER ⚡
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

# Vision model (must support images)
PROFILER_MODEL=openai/gpt-4o

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

**GitHub Models (Required):**
- Free tier: https://github.com/marketplace/models
- Create GitHub PAT with `models:read` scope
- Set `GITHUB_MODELS_PAT` in `.env`

**Model:**
- Default: `openai/gpt-4o` (supports vision)
- Alternative: `openai/gpt-4o-mini` (faster, less detailed)

## Troubleshooting

### "ProfilerAgent: GitHub Models not configured"
→ Set `GITHUB_MODELS_PAT` in `.env` with valid GitHub PAT

### "Profiler not responding to images"
→ Make sure you sent a trigger phrase first (within last 60 seconds)

### "Rate limit exceeded"
→ Wait 1 hour or contact admin for unlimited access

### "Image too large"
→ Compress image to under 10 MB (configurable via `PROFILER_MAX_IMAGE_SIZE_MB`)

## Privacy & Ethics

**Data Handling:**
- Images are NOT stored locally
- Images are sent to GitHub Models API for analysis
- Analysis text is returned but not permanently logged
- No facial recognition database is created

**Ethical Use:**
- Do NOT use for making hiring/firing decisions
- Do NOT use for legal judgments
- Do NOT use for medical/clinical diagnoses
- Do NOT use for surveillance without consent
- Use ONLY for entertainment and educational purposes

**Consent:**
- Always obtain consent before analyzing someone's photo
- Respect privacy and personal boundaries

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

---

**Last Updated**: January 2025  
**Version**: 1.0.0 (Trigger-based profiling)
