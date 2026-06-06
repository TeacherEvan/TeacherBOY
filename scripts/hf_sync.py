"""One-shot Hugging Face sync helper.

Uploads local on-disk artifacts to Hugging Face Hub dataset repos.

This is intentionally separate from the in-app CommitScheduler so you can
force an immediate sync from the terminal.

Env vars (match src.config.Settings field names):
- HF_MEMORY_TOKEN: Hugging Face token (write scope)
- HF_MEMORY_REPO_ID: dataset repo for conversation memory (e.g. "user/zeus-memory")
- HISTORY_LOG_HF_REPO_ID: dataset repo for history logs (e.g. "user/zeus-logs")
- CALENDAR_HF_REPO_ID: dataset repo for calendar events (e.g. "user/zeus-calendar")
- DOCUMENT_HF_REPO_ID: dataset repo for document storage (e.g. "user/zeus-documents")

Folders:
- data/conversations
- data/logs/hf_sync
- data/calendar
- data/documents
"""

from __future__ import annotations

import argparse
import os
from datetime import UTC, datetime
from pathlib import Path


def _require_env(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        raise SystemExit(f"Missing required env var: {name}. Set it and re-run (PowerShell example: $env:{name} = '...').")
    return value


def _get_hf_token(explicit_token: str | None = None) -> str:
    token = (explicit_token or "").strip()
    if token:
        return token

    token = (os.getenv("HF_MEMORY_TOKEN") or "").strip()
    if token:
        return token

    # Fall back to token stored by `huggingface-cli login`.
    try:
        from huggingface_hub import HfFolder

        cached = (HfFolder.get_token() or "").strip()
        if cached:
            return cached
    except Exception:
        pass

    raise SystemExit("No Hugging Face token found. Either run `huggingface-cli login` OR set HF_MEMORY_TOKEN.")


def _ensure_folder(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)


def _ensure_nonempty(folder: Path, marker_name: str) -> None:
    # upload_folder fails on empty folders; add a minimal marker file.
    has_files = any(p.is_file() for p in folder.rglob("*") if p.name != marker_name)
    if has_files:
        return

    marker = folder / marker_name
    stamp = datetime.now(UTC).isoformat()
    marker.write_text(f"hf_sync_marker\ncreated_at_utc={stamp}\n", encoding="utf-8")


def _sync_folder(
    *,
    token: str,
    repo_id: str,
    local_folder: Path,
    commit_message: str,
) -> None:
    try:
        from huggingface_hub import HfApi
    except Exception as exc:
        raise SystemExit(
            "huggingface_hub is not installed in this environment. "
            "Install requirements (pip install -r requirements.txt) and retry."
        ) from exc

    api = HfApi(token=token)

    # Create repo if missing (best-effort; ignore if it exists).
    try:
        api.create_repo(repo_id=repo_id, repo_type="dataset", private=True, exist_ok=True)
    except TypeError:
        # Older hub versions may not support exist_ok.
        try:
            api.create_repo(repo_id=repo_id, repo_type="dataset", private=True)
        except Exception:
            pass
    except Exception:
        pass

    api.upload_folder(
        repo_id=repo_id,
        repo_type="dataset",
        folder_path=str(local_folder),
        path_in_repo=".",
        commit_message=commit_message,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Force-sync Zeus data to Hugging Face Hub.")
    parser.add_argument(
        "--token",
        type=str,
        default=None,
        help="Optional HF token (otherwise uses HF_MEMORY_TOKEN or `huggingface-cli login` cached token).",
    )
    parser.add_argument(
        "--memory",
        action="store_true",
        help="Sync conversation memory folder (data/conversations).",
    )
    parser.add_argument(
        "--memory-repo",
        type=str,
        default=None,
        help="HF dataset repo id for memory (e.g. 'username/zeus-memory'). Defaults to HF_MEMORY_REPO_ID env var.",
    )
    parser.add_argument(
        "--logs",
        action="store_true",
        help="Sync history logs folder (data/logs/hf_sync).",
    )
    parser.add_argument(
        "--logs-repo",
        type=str,
        default=None,
        help="HF dataset repo id for logs (e.g. 'username/zeus-logs'). Defaults to HISTORY_LOG_HF_REPO_ID env var.",
    )
    parser.add_argument(
        "--calendar",
        action="store_true",
        help="Sync calendar events folder (data/calendar).",
    )
    parser.add_argument(
        "--calendar-repo",
        type=str,
        default=None,
        help="HF dataset repo id for calendar (e.g. 'username/zeus-calendar'). Defaults to CALENDAR_HF_REPO_ID env var.",
    )
    parser.add_argument(
        "--documents",
        action="store_true",
        help="Sync document memory folder (data/documents).",
    )
    parser.add_argument(
        "--documents-repo",
        type=str,
        default=None,
        help="HF dataset repo id for documents (e.g. 'username/zeus-documents'). Defaults to DOCUMENT_HF_REPO_ID env var.",
    )
    args = parser.parse_args()

    do_memory = args.memory
    do_logs = args.logs
    do_calendar = args.calendar
    do_documents = args.documents
    if not do_memory and not do_logs and not do_calendar and not do_documents:
        do_memory = True
        do_logs = True
        do_calendar = True  # Include calendar in default sync
        do_documents = True  # Include documents in default sync

    token = _get_hf_token(args.token)

    root = Path(__file__).resolve().parents[1]

    if do_memory:
        repo_id = (args.memory_repo or os.getenv("HF_MEMORY_REPO_ID") or "").strip()
        if not repo_id:
            raise SystemExit("Missing memory repo id. Provide --memory-repo or set HF_MEMORY_REPO_ID.")
        folder = root / "data" / "conversations"
        _ensure_folder(folder)
        _ensure_nonempty(folder, marker_name=".hf_sync_marker.txt")
        _sync_folder(
            token=token,
            repo_id=repo_id,
            local_folder=folder,
            commit_message=f"Sync conversations ({datetime.now(UTC).date().isoformat()})",
        )
        print(f"✅ Synced conversations to hf://datasets/{repo_id}")

    if do_logs:
        repo_id = (args.logs_repo or os.getenv("HISTORY_LOG_HF_REPO_ID") or "").strip()
        if not repo_id:
            raise SystemExit("Missing logs repo id. Provide --logs-repo or set HISTORY_LOG_HF_REPO_ID.")
        folder = root / "data" / "logs" / "hf_sync"
        _ensure_folder(folder)

        # Mirror any newly written daily log files into the HF sync folder so
        # one-shot syncs do not depend on the background CommitScheduler timing.
        source_logs_dir = root / "data" / "logs"
        for source in source_logs_dir.glob("zeus_log_*.jsonl"):
            target = folder / source.name
            if not target.exists() or source.stat().st_mtime > target.stat().st_mtime:
                target.write_bytes(source.read_bytes())

        _ensure_nonempty(folder, marker_name=".hf_sync_marker.txt")
        _sync_folder(
            token=token,
            repo_id=repo_id,
            local_folder=folder,
            commit_message=f"Sync logs ({datetime.now(UTC).date().isoformat()})",
        )
        print(f"✅ Synced logs to hf://datasets/{repo_id}")

    if do_calendar:
        repo_id = (args.calendar_repo or os.getenv("CALENDAR_HF_REPO_ID") or "").strip()
        if not repo_id:
            print("⚠️  Skipping calendar sync: No CALENDAR_HF_REPO_ID provided")
        else:
            folder = root / "data" / "calendar"
            _ensure_folder(folder)
            _ensure_nonempty(folder, marker_name=".hf_sync_marker.txt")
            _sync_folder(
                token=token,
                repo_id=repo_id,
                local_folder=folder,
                commit_message=f"Sync calendar ({datetime.now(UTC).date().isoformat()})",
            )
            print(f"✅ Synced calendar to hf://datasets/{repo_id}")

    if do_documents:
        repo_id = (args.documents_repo or os.getenv("DOCUMENT_HF_REPO_ID") or "").strip()
        if not repo_id:
            print("⚠️  Skipping documents sync: No DOCUMENT_HF_REPO_ID provided")
        else:
            folder = root / "data" / "documents"
            _ensure_folder(folder)
            _ensure_nonempty(folder, marker_name=".hf_sync_marker.txt")
            _sync_folder(
                token=token,
                repo_id=repo_id,
                local_folder=folder,
                commit_message=f"Sync documents ({datetime.now(UTC).date().isoformat()})",
            )
            print(f"✅ Synced documents to hf://datasets/{repo_id}")


if __name__ == "__main__":
    main()
