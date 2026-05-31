# Image Privacy & Memory Management

## Overview

Ms. Green handles image data with privacy-first design principles. All image
data is **automatically scrubbed from memory** after processing to prevent
unauthorized retention of sensitive visual data.

## Image Lifecycle

### 1. Download (LINE API → Bot Memory)

- **Source**: LINE Messaging API Blob endpoint
- **Storage**: Temporary Python variable (`image_bytes`)
- **Duration**: Milliseconds
- **Size**: Original image size (max 10MB as per config)

### 2. Encoding (Binary → Base64)

```python
image_bytes  →  base64_encode  →  image_data_url
```

- **Format**: Data URL with base64 encoding (`data:image/jpeg;base64,...`)
- **Purpose**: Vision API compatibility (GPT-4o requires base64)
- **Storage**: Temporary Python variables

### 3. Processing Paths

#### **ProfilerAgent (Facial Profiling)**

```text
Download → Encode → Send to GPT-4o → DELETE ALL → Send response
```

- Image data is **immediately deleted** after GPT-4o returns analysis
- No storage in session manager (one-shot analysis)
- No storage in conversation memory
- No storage in history logs

#### **ImageAnalyzerAgent (Q&A)**

```text
Download → Encode → Store in Session → Wait for Question → Send to GPT-4o → DELETE ALL
```

- Image stored temporarily in `ImageAnalyzerSessionManager` (60-second TTL)
- Session manager clears image when:
  - User asks question (session completed)
  - 60 seconds elapse (session expires)
  - User cancels with shutdown phrase
- Image **never persists** beyond session completion

### 4. Deletion Points (CRITICAL)

#### **ProfilerAgent** (`profiler_agent.py`)

```python
# After vision API call:
del image_bytes        # Clear original binary data
del image_data_url     # Clear base64 data URL
del messages           # Clear vision API messages containing image
```

#### **ImageAnalyzerAgent** (`image_analyzer_agent.py`)

```python
# After encoding:
del image_bytes        # Clear binary data
del image_base64       # Clear intermediate base64 string
del image_data_url     # Clear after storing in session

# After vision API call:
del image_data         # Clear retrieved session data
del messages           # Clear vision API messages
```

#### **Session Managers**

- `ImageAnalyzerSessionManager.get_image_and_question()` **deletes session** after retrieval
- `profiler_session_manager.clear_session()` removes all session state
- Background cleanup tasks remove expired sessions every 60 seconds

## What Is NOT Stored

### ✅ Conversation Memory

- **Stores**: Text messages only (user questions, bot responses)
- **Does NOT store**: Image bytes, data URLs, or image references
- **Format**: JSON with `{role, content, timestamp}`
- **Image Questions**: Only the text question is stored, never the image

### ✅ History Logs

- **Stores**: Event metadata (event type, timestamp, chat_id, agent name)
- **Does NOT store**: Image bytes, data URLs, or visual content
- **Image Events**: Logs "image analysis started" but not the image itself
- **Format**: Structured log entries with `{id, timestamp, event_type, message, metadata}`

### ✅ External APIs

- **GitHub Models**: Receives image, returns text analysis, no storage
- **LINE API**: Original image stored on LINE servers (user's responsibility)

## Session TTLs

| Session Type           | Duration           | Cleanup Method              |
| ---------------------- | ------------------ | --------------------------- |
| Profiler Session       | No storage         | N/A (no session)            |
| Image Analyzer Session | 60 seconds         | Auto-cleanup + manual clear |
| Session Image Data     | Until Q&A complete | Deleted on retrieval        |

## Privacy Guarantees

1. **No Persistent Image Storage**: Images are never written to disk, databases, or HF Hub
2. **No Conversation Memory**: Image data URLs are not stored in conversation history
3. **No Audit Logs**: History logs do not contain image bytes or data URLs
4. **Explicit Memory Cleanup**: `del` statements remove references for garbage collection
5. **TTL Enforcement**: Session managers enforce 60-second expiration
6. **No External Sharing**: Images are sent ONLY to GitHub Models API (GPT-4o)

## Compliance Notes

### GDPR/CCPA

- Image data is **transient** (seconds to minutes)
- No long-term storage or profiling databases
- User can request deletion via shutdown phrase ("amen")
- Image analysis is **opt-in** (user must trigger with commands)

### Data Minimization

- Only image metadata logged (size, message_id)
- No biometric data stored (analysis results are text-only)
- Session cleanup removes all image references

### User Control

- Users must **explicitly request** image analysis/profiling
- Shutdown phrase ("amen") clears all active sessions
- Session expiration (60s) provides automatic cleanup

## Technical Implementation

### Memory Management Strategy

```python
# 1. Download (temporary)
image_bytes = await download_image()

# 2. Encode (temporary)
image_data_url = encode_to_base64(image_bytes)
del image_bytes  # Explicit cleanup

# 3. Process (temporary)
messages = build_vision_message(image_data_url)
analysis = await gpt4o_vision(messages)
del image_data_url  # Explicit cleanup
del messages       # Explicit cleanup

# 4. Respond (no image data)
send_text_response(analysis)
```

### Garbage Collection

Python's garbage collector automatically reclaims memory when:

- `del` statement removes last reference
- Function scope exits (local variables)
- Session manager deletes session dict

### Background Cleanup

- `profiler_session_manager.cleanup_expired()` runs every 60s
- `image_analyzer_session_manager.cleanup_expired()` runs every 60s
- Removes sessions older than TTL threshold

## Monitoring & Auditing

### What IS Logged

- "Image analysis started" (metadata only)
- "Image size: X bytes" (no image content)
- "Analysis completed" (text response length)

### What is NOT Logged

- Image binary data
- Base64 encoded image
- Vision API request payload (with image)

### Log Example

```json
{
  "event_type": "IMAGE_ANALYSIS",
  "message": "User requested facial profiling",
  "metadata": {
    "chat_id": "user_abc123",
    "image_size_bytes": 245678,
    "analysis_type": "full"
  }
}
```

## Developer Guidelines

### ✅ DO

- Use `del` to explicitly clear image variables after use
- Store images in session managers with TTL
- Log metadata (size, type) but not content
- Clear sessions after analysis completion

### ❌ DON'T

- Write images to disk
- Store images in conversation memory
- Include images in audit logs
- Keep image references beyond processing

## Rate Limiting & Cost Control

Image analysis is rate-limited to prevent abuse:

- **ProfilerAgent**: 3 requests/hour per chat (vision API is expensive)
- **ImageAnalyzerAgent**: 10 requests/hour per chat
- Admins bypass rate limits

This protects user privacy (prevents mass profiling) and controls API costs.

## Questions & Support

**Q: Can users request image deletion?**  
A: Images are automatically deleted after processing. No manual deletion needed.

**Q: Where are images stored?**  
A: Images are ONLY stored temporarily in Python memory (seconds to 60 seconds max).

**Q: Can admins see user images?**  
A: No. Admins have no access to image data. Only text analysis results are visible.

**Q: What happens if bot crashes during analysis?**  
A: Python process terminates, all memory (including images) is cleared.

**Q: Are images backed up to HF Hub?**  
A: No. HF Hub only stores conversation text, never images.

---

**Last Updated**: 2025-01-09  
**Privacy Compliance**: GDPR-ready, CCPA-compliant  
**Data Retention**: Transient (seconds to minutes, never persistent)
