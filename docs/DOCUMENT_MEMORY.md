---

**Feature Version:** 3.6.0  
**Last Updated:** 2026-01-19  
**Status:** Production-ready  
**Dependencies:** pypdf, python-docx, HF Hub (optional)  
**Related Commands:** `Zeus docs`, `Zeus doc <ID>`, `Zeus doc search <query>`

---

# Document Memory (PDF/DOCX)

Zeus can store PDF and DOCX files per chat and extract their text for later retrieval.

## What It Does

- Downloads PDF/DOCX files sent to the bot
- Extracts text and stores it locally under `data/documents`
- Optionally syncs to HF Hub for persistence across restarts

## Commands

- `Zeus docs` — list stored documents for this chat
- `Zeus doc <ID>` — show extracted text (truncated)
- `Zeus doc search <query>` — find documents containing a phrase
- `Zeus doc delete <ID>` — delete one document
- `Zeus doc clear` — clear all documents for this chat

## Configuration

```env
DOCUMENT_MEMORY_ENABLED=true
DOCUMENT_STORAGE_PATH=./data/documents
DOCUMENT_MAX_FILE_SIZE_MB=10.0
DOCUMENT_MAX_TEXT_CHARS=80000
DOCUMENT_HF_REPO_ID=username/zeus-documents
```

> For guaranteed persistence across container resets, set `DOCUMENT_HF_REPO_ID` and `HF_MEMORY_TOKEN`.

## Notes

- Supported file types: `.pdf`, `.docx`
- Text extraction may be empty for scanned PDFs
- `Zeus reset` clears conversation memory only — document memory is separate
