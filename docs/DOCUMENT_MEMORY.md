---

**Feature Version:** 3.6.0  
**Last Updated:** 2026-01-19  
**Status:** Production-ready  
**Dependencies:** pypdf, python-docx, HF Hub (optional)  
**Related Commands:** `Ms. Green docs`, `Ms. Green doc <ID>`, `Ms. Green doc search <query>`

---

# Document Memory (PDF/DOCX)

Ms. Green can store PDF and DOCX files per chat and extract their text for later retrieval.

## What It Does

- Downloads PDF/DOCX files sent to the bot
- Extracts text and stores it locally under `data/documents`
- Optionally syncs to HF Hub for persistence across restarts

## Commands

- `Ms. Green docs` — list stored documents for this chat
- `Ms. Green doc <ID>` — show extracted text (truncated)
- `Ms. Green doc search <query>` — find documents containing a phrase
- `Ms. Green doc delete <ID>` — delete one document
- `Ms. Green doc clear` — clear all documents for this chat

## Configuration

```env
DOCUMENT_MEMORY_ENABLED=true
DOCUMENT_STORAGE_PATH=./data/documents
DOCUMENT_MAX_FILE_SIZE_MB=10.0
DOCUMENT_MAX_TEXT_CHARS=80000
DOCUMENT_HF_REPO_ID=username/ms-green-documents
```

For the full storage contract and mounted-volume examples, see [Environment variables](reference/environment.md).

For production deployments with a mounted volume, point
`DOCUMENT_STORAGE_PATH` at the mounted filesystem path and keep
`DOCUMENT_HF_REPO_ID` separate for optional HF-backed persistence:

```env
DOCUMENT_STORAGE_PATH=/data/ms-sunshine/documents
DOCUMENT_HF_REPO_ID=username/ms-green-documents
```

> For restart persistence across container resets, set both
> `DOCUMENT_HF_REPO_ID` and `HF_MEMORY_TOKEN`. `DOCUMENT_STORAGE_PATH`
> controls the local filesystem location.

## Notes

- Supported file types: `.pdf`, `.docx`
- Text extraction may be empty for scanned PDFs
- `Ms. Green reset` clears conversation memory only — document memory is separate
