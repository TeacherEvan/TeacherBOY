#!/usr/bin/env python3
"""Purge legacy HF dataset pollution."""

import argparse
import os

from huggingface_hub import CommitOperationDelete, HfApi

REPO_ID = os.environ.get("PURGE_REPO_ID", "EvilEvan/teacherBOY-memory")
BAD_PREFIXES = ("conversations/conversations/", "conversations/.cache/")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    api = HfApi(token=os.environ.get("HF_TOKEN"))
    files = api.list_repo_files(REPO_ID, repo_type="dataset")
    bad = [f for f in files if f.startswith(BAD_PREFIXES) or ".cache/huggingface" in f]
    if not args.apply:
        print(f"Dry-run: {len(bad)} bad files")
        return 0
    for f in bad:
        api.create_commit(
            repo_id=REPO_ID, repo_type="dataset", operations=[CommitOperationDelete(path_in_repo=f)], commit_message="purge"
        )
    print("Applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
