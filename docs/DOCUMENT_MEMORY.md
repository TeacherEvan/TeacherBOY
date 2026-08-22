---
**Feature Version:** 3.6.0
**Last Updated:** 2026-06-13
**Status:** Production-ready
**Dependencies:** pypdf, python-docx, HF Hub (optional)
**Related Commands:** `Ms. Green docs`, `Ms. Green doc <ID>`, `Ms. Green doc search <query>`, `Ms. Green doc delete <ID>`, `Ms. Green doc clear`
---

# Document Memory (PDF/DOCX)

Ms. Green can store PDF and DOCX files per chat and extract their text for later retrieval.

## Quick Start

### List Documents

```
Ms. Green docs
Ms. Green doc
```

### View Document

```
Ms. Green doc 1
Ms. Green doc abc123
```

### Search Documents

```
Ms. Green doc search meeting notes
Ms. Green doc search budget
```

### Delete Document

```
Ms. Green doc delete 1
Ms. Green doc delete abc123
```

### Clear All Documents

```
Ms. Green doc clear
```

## Features

### 1. Automatic File Processing

When a PDF or DOCX file is uploaded to a chat where Ms. Green is present:
1. File is downloaded from LINE
2. Text is extracted (first 80,000 characters)
3. Stored locally with unique ID
4. Synced to HF Hub (if configured)

### 2. Per-Chat Isolation

Documents are scoped to the chat where they were uploaded:
- Group documents stay in that group
- DM documents stay private to that DM
- Users only see documents from their current chat

### 3. Search & Retrieval

- **List**: View all stored documents with IDs
- **View**: Read extracted text (truncated for display)
- **Search**: Find documents containing specific phrases
- **Delete**: Remove individual documents by ID
- **Clear**: Remove all documents from current chat

### 4. Persistence Options

| Mode | Description | Use Case |
|------|-------------|----------|
| Local only | Files in `./data/documents` | Development, single-server |
| HF Hub sync | Local + HF dataset backup | Multi-instance, restart persistence |
| Mounted volume | Docker volume at `/data` | HF Spaces, Kubernetes |

## Commands Reference

| Command | Description | Example |
|---------|-------------|---------|
| `Ms. Green docs` | List all documents in this chat | `Ms. Green docs` |
| `Ms. Green doc` | Same as above | `Ms. Green doc` |
| `Ms. Green doc <ID>` | Show extracted text for document | `Ms. Green doc 1` |
| `Ms. Green doc search <query>` | Search documents for phrase | `Ms. Green doc search budget` |
| `Ms. Green doc delete <ID>` | Delete specific document | `Ms. Green doc delete 1` |
| `Ms. Green doc clear` | Delete all documents in chat | `Ms. Green doc clear` |

## Configuration

```env
# Enable/disable feature
DOCUMENT_MEMORY_ENABLED=true

# Local storage path
DOCUMENT_STORAGE_PATH=./data/documents

# Max file size (MB)
DOCUMENT_MAX_FILE_SIZE_MB=10.0

# Max extracted text characters per document
DOCUMENT_MAX_TEXT_CHARS=80000

# Optional: Hugging Face Hub backup
DOCUMENT_HF_REPO_ID=username/ms-green-documents

# Required for HF sync
HF_MEMORY_TOKEN=hf_xxxxxxxxxxxx
```

### Mounted-Volume Deployment

For HF Spaces or Kubernetes with persistent volumes:

```env
DOCUMENT_STORAGE_PATH=/data/ms-green/documents
DOCUMENT_HF_REPO_ID=username/ms-green-documents
HF_MEMORY_TOKEN=hf_xxxxxxxxxxxx
```

> **Note**: `DOCUMENT_STORAGE_PATH` controls the local filesystem location (working directory). `DOCUMENT_HF_REPO_ID` is the separate HF dataset repo for cloud backup. Both are needed for full restart persistence.

## Supported File Types

| Extension | Library | Notes |
|-----------|---------|-------|
| `.pdf` | pypdf | Text extraction; scanned PDFs may return empty |
| `.docx` | python-docx | Full text extraction including tables |

## File Processing Limits

| Limit | Default | Configurable |
|-------|---------|--------------|
| Max file size | 10 MB | `DOCUMENT_MAX_FILE_SIZE_MB` |
| Max extracted text | 80,000 chars | `DOCUMENT_MAX_TEXT_CHARS` |
| Storage per chat | Unlimited | - |

## Technical Details

### Architecture

```
DocumentMemoryAgent (Priority: 8)
    ↓
DocumentMemoryService (CRUD + Persistence)
    ↓
Local Filesystem + Optional HF Hub (CommitScheduler)
```

### Data Model

```python
@dataclass
class Document:
    doc_id: str              # UUID
    chat_id: str             # LINE chat ID (user_XXX, group_XXX, room_XXX)
    filename: str            # Original filename
    file_size: int           # Bytes
    text_content: str        # Extracted text (truncated to max)
    uploaded_by: str         # LINE user ID
    uploaded_at: datetime    # Upload timestamp
    hf_synced: bool          # HF Hub sync status
```

### Components

| Component | File | Purpose |
|-----------|------|---------|
| Agent | `src/agents/document_memory_agent.py` | Handles triggers and multi-step flows |
| Service | `src/services/document_memory_service.py` | CRUD, storage, HF sync |
| Session Manager | `src/services/document_memory_session_manager.py` | State machine for delete/clear flows |

## Privacy and Security

- **Chat Isolation**: Document visibility scoped to current chat
- **No Cross-Chat Access**: Users cannot access documents from other chats
- **Local-First**: Files stored locally by default
- **Optional Cloud Backup**: HF Hub sync is opt-in
- **No Image Storage**: Only text content extracted and stored

## Troubleshooting

### "Document Memory not enabled"
→ Set `DOCUMENT_MEMORY_ENABLED=true` in `.env`

### "File too large"
→ Reduce file size or increase `DOCUMENT_MAX_FILE_SIZE_MB`

### "No text extracted"
→ PDF may be scanned/image-based; try OCR first or use DOCX

### "HF Sync failing"
→ Check `HF_MEMORY_TOKEN` has write access to `DOCUMENT_HF_REPO_ID`
→ Verify repo exists or bot has permission to create it

### "Commands not working"
→ Ensure you're in the same chat where documents were uploaded
→ Document commands only work for documents in current chat

## Examples

### Uploading a PDF

```
User: [sends meeting_notes.pdf]
Ms. Green: 📄 Document stored: meeting_notes.pdf (ID: a1b2c3d4)
         Extracted 2,450 characters.
```

### Searching Documents

```
User: Ms. Green doc search action items
Ms. Green: Found 2 documents:
          1. a1b2c3d4 - meeting_notes.pdf
             "...action items: John to review budget, Mary to prepare slides..."
          2. e5f6g7h8 - project_plan.docx
             "...action items for Q2: hire developer, setup CI/CD..."
```

### Viewing a Document

```
User: Ms. Green doc a1b2c3d4
Ms. Green: 📄 meeting_notes.pdf (ID: a1b2c3d4)
          Uploaded by U123... on 2026-06-10 14:30
          ──────────────────
          Meeting Notes - June 10, 2026
          
          Attendees: John, Mary, Peter
          
          Action Items:
          1. John - Review budget by Friday
          2. Mary - Prepare slides for Monday
          3. Peter - Setup CI/CD pipeline
          
          Next Meeting: June 17, 2026
          ──────────────────
          (Showing first 800 chars of 2,450)
```

### Clearing Documents

```
User: Ms. Green doc clear
Ms. Green: ⚠️ This will delete ALL 5 documents in this chat.
          Type "confirm" to proceed.
User: confirm
Ms. Green: ✅ Cleared 5 documents from this chat.
```

## Related Documentation

- [Quick Reference](reference/quick-reference.md) - Command summary
- [Environment Variables](reference/environment.md) - Configuration details
- [Conversation Memory](CONVERSATION_MEMORY.md) - Chat memory system
- [Deployment Guide](guides/deployment.md) - Mounted volume setup

---

**Last Updated**: June 2026  
**Version**: 1.1.0