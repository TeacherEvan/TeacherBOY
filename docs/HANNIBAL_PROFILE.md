# Hannibal Profile Agent - User Guide

## Overview

The Hannibal Profile Agent performs psychological profiling based on **message history** (text analysis), unlike the Profiler Agent which analyzes **images**. It uses message patterns, language use, and behavioral indicators to build a psychological profile.

## How to Use

### Trigger

Send in a private chat:

```
hannibal profile
```

or

```
analyze messages
```

**Example:**

```
User: hannibal profile
Ms. Green: 🧠 Analyzing your message history...
Ms. Green: [Returns detailed psychological profile]
```

### What It Analyzes

- **Communication style** - Formal vs casual, verbosity, structure
- **Emotional patterns** - Emotional range, regulation, expression
- **Cognitive indicators** - Complexity, abstraction, reasoning style
- **Social dynamics** - Interaction patterns, dominance, empathy markers
- **Language markers** - Vocabulary, syntax, pronouns, emotional words
- **Temporal patterns** - Response timing, consistency, activity cycles

### Frameworks Used

1. **FBI Behavioral Analysis Unit (BAU)** methodology
   - Victimology/subject assessment
   - Behavioral indicators
   - Cognitive load indicators
   - Social dynamics analysis

2. **Paul Ekman's 7 Universal Emotions** detection
   - Happiness, Sadness, Fear, Anger, Surprise, Disgust, Contempt
   - Microexpression equivalents in text

3. **Joe Navarro's Body Language** principles (adapted for text)
   - Limbic system responses in language
   - Discomfort vs comfort markers
   - Dominance/submission language patterns

4. **Color Psychology** - If emoji/color references present

## Access Control

| Context | Access |
|---------|--------|
| Private Chat (DM) | ✅ Available when AI providers configured |
| Group/Room | ❌ Not available (privacy) |

**Note**: Only works in private chats for privacy reasons.

## Rate Limits

- Standard limits apply
- Admins: Unlimited

## Configuration

Requires AI provider (Gemini free tier recommended):

```env
# Primary provider - Gemini free tier (recommended)
# Get key from: https://aistudio.google.com/app/apikey
GEMINI_API_KEY=your_gemini_api_key_here

# Alternative: OpenRouter (fallback)
# OPENROUTER_API_KEY=your_openrouter_api_key_here
```

**Note**: The agent uses the LLM fallback chain (Gemini first, then OpenRouter as fallback). See [Environment Variables](reference/environment.md) for all options.

## Example Output

```
🧠 HANNIBAL PROFILE - PSYCHOLOGICAL ANALYSIS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 **COMMUNICATION STYLE**
- Verbosity: Moderate (avg 47 words/message)
- Formality: Semi-formal (mixed register)
- Structure: Organized, uses paragraphs
- Questions: Frequent (23% of messages)

😊 **EMOTIONAL PROFILE (Ekman Framework)**
- Primary: Interest/Curiosity (34%)
- Secondary: Happiness (28%)
- Baseline: Calm/Neutral (31%)
- Rare: Anger (<2%), Fear (<1%)
- Emotional range: Moderate, well-regulated

🧠 **COGNITIVE INDICATORS**
- Complexity: High (uses abstract concepts)
- Reasoning: Analytical, evidence-based
- Planning: Future-oriented language
- Metacognition: Self-reflective statements present

👥 **SOCIAL DYNAMICS (Navarro Adaptation)**
- Dominance: Balanced (neither dominant nor submissive)
- Empathy markers: High (validation, support language)
- Collaboration: Team-oriented ("we", "let's")
- Conflict style: Constructive, solution-focused

⏰ **TEMPORAL PATTERNS**
- Peak activity: 09:00-12:00, 19:00-22:00 (Bangkok time)
- Response latency: Fast (median 2.3 min)
- Consistency: High (daily engagement)

🎯 **KEY BEHAVIORAL INDICATORS**
+ High intellectual curiosity
+ Strong emotional regulation
+ Collaborative leadership style
+ Evidence-based decision making
- Occasional over-analysis (perfectionism)
- May delay action for more information

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ **DISCLAIMER**: For educational/entertainment purposes only.
NOT for professional psychological assessment, hiring, legal, or medical use.
```

## Data Source

- Analyzes messages from the current conversation
- Uses conversation memory (if enabled) for broader context
- Does NOT access images or external data

## Privacy

- Analysis runs in private chat only
- Results not stored permanently
## Troubleshooting

### "HannibalProfileAgent: No LLM provider configured"

→ Set `GEMINI_API_KEY` in `.env` with valid Google AI Studio key

### "Not responding in group chat"

→ This feature is private-chat only for privacy

### "No conversation history to analyze"

→ Need some message history first. Chat more, then try again.

## Technical Details

### Agent Priority

- Priority 6 (same as Calendar, after Admin/Help)
- Only registered when AI providers configured

### Files

- `src/agents/hannibal_agent.py` - Main agent logic
- `src/utils/llm_fallback.py` - LLM fallback chain
- `tests/test_hannibal_agent.py` - Test suite (if exists)

### Flow

```text
User: "hannibal profile"
        │
        ▼
HannibalProfileAgent.should_handle() → True (matches pattern)
        │
        ▼
HannibalProfileAgent.handle()
        │
        ├─► Get conversation history from memory
        │
        ├─► Build prompt with FBI/Ekman/Navarro frameworks
        │
        ├─► Call LLM fallback chain (Gemini first)
        │
        └─► Return formatted psychological profile
```

## Differences from Profiler Agent

| Aspect | Hannibal Profile | Profiler Agent |
|--------|-----------------|----------------|
| **Input** | Message history (text) | Images/photos |
| **Focus** | Communication patterns | Visual behavioral cues |
| **Frameworks** | FBI BAU, Ekman, Navarro (text-adapted) | FBI BAU, Ekman FACS, Navarro (visual) |
| **Context** | Private chat only | Any chat (with trigger) |
| **Privacy** | Higher (text only) | Standard |

## Use Cases

### Self-Reflection
```
User: hannibal profile
Ms. Green: [Returns profile showing communication strengths, emotional patterns]
```

### Team Dynamics (in DM)
```
User: analyze messages
Ms. Green: [Shows how user interacts, collaboration style]
```

### Educational
- Learn about your own communication patterns
- Understand psychological frameworks through personal example
- Practice self-awareness

## Related Documentation

- [Psychological Profiler](PROFILER_USAGE.md) - Image-based profiling
- [Quick Reference](reference/quick-reference.md) - Command summary
- [Environment Variables](reference/environment.md) - Configuration guide

---

**Last Updated**: June 2026  
**Version**: 1.0.0  
**Disclaimer**: For educational and entertainment purposes only. NOT for professional assessments.