#!/usr/bin/env python3
"""
Log Decryption Utility - Retrieve and decrypt history logs from Hugging Face Hub.
"""

import argparse
import base64
import getpass
import hashlib
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Ensure we can import cryptography
try:
    from cryptography.fernet import Fernet
except ImportError:
    print("❌ Error: The 'cryptography' package is required for decryption.")
    print("Please run: pip install cryptography")
    sys.exit(1)

try:
    from huggingface_hub import hf_hub_download, list_repo_files
except ImportError:
    print("❌ Error: The 'huggingface_hub' package is required.")
    print("Please run: pip install huggingface_hub")
    sys.exit(1)


def get_fernet_key(encryption_key: str) -> bytes:
    """Derive Fernet key from encryption key string using the same method as HistoryLogService."""
    key_bytes = hashlib.sha256(encryption_key.encode()).digest()
    return base64.urlsafe_b64encode(key_bytes)


def decrypt_line(fernet: Fernet, line: str) -> str:
    """Attempt to decrypt a single line. If it fails or is not encrypted, return as-is."""
    line_stripped = line.strip()
    if not line_stripped:
        return line

    # Fernet tokens usually start with gAAAAA or Z0FBQUFB (base64url of gAAAAA)
    # Check both raw Fernet format and the base64-wrapped format in HistoryLogService
    try:
        # Check base64 url safe decode
        decoded = base64.urlsafe_b64decode(line_stripped.encode())
        decrypted = fernet.decrypt(decoded)
        return decrypted.decode("utf-8")
    except Exception:
        # Try direct Fernet decryption
        try:
            decrypted = fernet.decrypt(line_stripped.encode())
            return decrypted.decode("utf-8")
        except Exception:
            # Return as-is if it's not encrypted or decryption failed
            return line


def main():
    parser = argparse.ArgumentParser(description="Download and decrypt logs from Hugging Face Hub.")
    parser.add_argument("-k", "--key", help="Log encryption key (falls back to HISTORY_LOG_ENCRYPTION_KEY env var)")
    parser.add_argument("-r", "--repo", help="HF log repository ID (falls back to HISTORY_LOG_HF_REPO_ID env var)")
    parser.add_argument("-t", "--token", help="HF API token (falls back to HF_TOKEN or HF_MEMORY_TOKEN env var)")
    parser.add_argument("-o", "--out", default="./data/logs/decrypted", help="Output directory for decrypted logs")

    args = parser.parse_args()

    # Load env files
    load_dotenv()
    load_dotenv(".env.local")

    # Resolve parameters
    token = args.token or os.getenv("HF_TOKEN") or os.getenv("HF_MEMORY_TOKEN")
    repo_id = args.repo or os.getenv("HISTORY_LOG_HF_REPO_ID")
    encryption_key = args.key or os.getenv("HISTORY_LOG_ENCRYPTION_KEY")

    if not token:
        print("❌ Error: Hugging Face API token is required. Set HF_TOKEN env var or use --token.")
        sys.exit(1)

    if not repo_id:
        print("❌ Error: Repository ID is required. Set HISTORY_LOG_HF_REPO_ID env var or use --repo.")
        sys.exit(1)

    if not encryption_key:
        print("🔐 Logs may be encrypted. Please enter the encryption key.")
        encryption_key = getpass.getpass("Encryption Key: ").strip()
        if not encryption_key:
            print("⚠️ No encryption key provided. Decryption will be skipped; files will be downloaded as-is.")

    # Set up decryptor if key is provided
    fernet = None
    if encryption_key:
        try:
            fernet_key = get_fernet_key(encryption_key)
            fernet = Fernet(fernet_key)
            print("🔐 Decryptor initialized successfully.")
        except Exception as e:
            print(f"❌ Failed to initialize decryptor: {e}")
            sys.exit(1)

    # Create output directory
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"☁️ Connecting to Hugging Face repository: {repo_id}...")
    try:
        files = list_repo_files(repo_id=repo_id, repo_type="dataset", token=token)
    except Exception as e:
        print(f"❌ Failed to list repository files: {e}")
        sys.exit(1)

    log_files = [f for f in files if f.endswith(".jsonl")]
    if not log_files:
        print("📭 No log files (*.jsonl) found in the repository.")
        sys.exit(0)

    print(f"📂 Found {len(log_files)} log files. Starting download and decryption...")

    for filename in log_files:
        print(f"\n📥 Downloading: {filename}")
        try:
            # Download file
            local_path = hf_hub_download(repo_id=repo_id, filename=filename, repo_type="dataset", token=token)

            # Determine local output path
            out_filename = Path(filename).name
            out_filepath = out_dir / out_filename

            print(f"🔓 Decrypting to: {out_filepath}")
            decrypted_count = 0
            plain_count = 0

            with open(local_path, encoding="utf-8") as infile, open(out_filepath, "w", encoding="utf-8") as outfile:
                for line in infile:
                    if not line.strip():
                        continue
                    if fernet:
                        decrypted = decrypt_line(fernet, line)
                        if decrypted != line:
                            decrypted_count += 1
                        else:
                            plain_count += 1
                        outfile.write(decrypted.strip() + "\n")
                    else:
                        outfile.write(line)
                        plain_count += 1

            print(f"✅ Finished: {decrypted_count} entries decrypted, {plain_count} skipped/plain-text.")

        except Exception as e:
            print(f"⚠️ Error processing file {filename}: {e}")

    print(f"\n🎉 Done! Decrypted log files are stored in: {out_dir.resolve()}")


if __name__ == "__main__":
    main()
