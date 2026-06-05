#!/usr/bin/env python3
"""
Sync local secrets to Hugging Face Space settings.

This script reads your local ~/.secrets/maton.txt and updates the 
Hugging Face Space "Variables and Secrets" for EvilEvan/TeacherBOY.

Prerequisites:
1. Install huggingface_hub: pip install huggingface_hub
2. Login to HF: huggingface-cli login
3. Ensure you have write access to the EvilEvan/TeacherBOY space.
"""
import os
from pathlib import Path
from huggingface_hub import HfApi

SPACE_ID = "EvilEvan/TeacherBOY"

def main():
    api = HfApi()
    
    print(f"🔄 Syncing secrets to HF Space: {SPACE_ID}...")
    
    # 1. Maton API Key
    maton_path = Path.home() / ".secrets" / "maton.txt"
    if maton_path.exists():
        maton_key = maton_path.read_text().strip()
        if maton_key:
            print("  📌 Setting MATON_API_KEY...")
            api.add_space_secret(SPACE_ID, "MATON_API_KEY", maton_key)
            print("    ✅ MATON_API_KEY updated successfully.")
        else:
            print("    ⚠️  ~/.secrets/maton.txt is empty.")
    else:
        print("    ⚠️  ~/.secrets/maton.txt not found. Skipping MATON_API_KEY.")

    # 2. Convex Deployment (Optional prompt if not set)
    # You can add other secrets here as needed.
    
    print("\n✅ Secret sync complete!")
    print("💡 Note: The code sync to HF is handled automatically by GitHub Actions.")
    print("   Your new .env.example documentation has been pushed and will sync shortly.")

if __name__ == "__main__":
    main()
