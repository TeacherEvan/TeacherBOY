"""
Setup Hugging Face Dataset Repositories for TeacherBOY
Creates calendar and memory dataset repos for data persistence.
"""

import os

try:
    from huggingface_hub import HfApi, RepositoryNotFoundError, create_repo
except ImportError:
    print("❌ huggingface_hub is not installed. Install with: pip install huggingface_hub")
    raise


def main():
    # Get HF token from environment
    hf_token = os.getenv("HF_TOKEN")
    if not hf_token:
        print("❌ HF_TOKEN environment variable not set!")
        print("Set it with: $env:HF_TOKEN = 'hf_...'")
        return 1

    api = HfApi(token=hf_token)

    # Get authenticated user info
    try:
        user_info = api.whoami()
        username = user_info["name"]
        print(f"✅ Authenticated as: {username}")
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        return 1

    # Define repos to create
    repos = [
        {
            "name": "teacherBOY-calendar",
            "description": "TeacherBOY calendar events and reminders data",
            "env_var": "CALENDAR_HF_REPO_ID",
        },
        {
            "name": "teacherBOY-memory",
            "description": "TeacherBOY conversation memory and history logs",
            "env_var": "HF_MEMORY_REPO_ID",
        },
    ]

    created_repos = []

    for repo_info in repos:
        repo_id = f"{username}/{repo_info['name']}"

        try:
            # Check if repo already exists
            api.repo_info(repo_id=repo_id, repo_type="dataset")
            print(f"✓ Repository already exists: {repo_id}")
            created_repos.append(repo_id)
        except RepositoryNotFoundError:
            # Create new repo
            try:
                url = create_repo(repo_id=repo_info["name"], repo_type="dataset", private=True, token=hf_token)
                print(f"✅ Created private dataset: {repo_id}")
                print(f"   URL: {url}")
                created_repos.append(repo_id)
            except Exception as e:
                print(f"❌ Failed to create {repo_id}: {e}")
                continue

    # Display environment variable setup
    print("\n" + "=" * 60)
    print("📋 ENVIRONMENT VARIABLE SETUP")
    print("=" * 60)
    print("\nFor Local Development (PowerShell):")
    print("-" * 60)
    for i, repo_info in enumerate(repos):
        if i < len(created_repos):
            print(f'$env:{repo_info["env_var"]} = "{created_repos[i]}"')
    print(f'$env:HF_TOKEN = "{hf_token[:10]}..."  # Already set')

    print("\n\nFor HF Spaces Deployment:")
    print("-" * 60)
    print("Go to: https://huggingface.co/spaces/YourSpace/settings")
    print("\nAdd as VARIABLES (public config):")
    for i, repo_info in enumerate(repos):
        if i < len(created_repos):
            print(f"  • {repo_info['env_var']} = {created_repos[i]}")
    print("\nAdd as SECRET (sensitive):")
    print(f"  • HF_TOKEN = {hf_token[:10]}...")

    print("\n\n✅ Setup complete! Run sync with:")
    print("   python scripts/hf_sync.py")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    exit(main())
