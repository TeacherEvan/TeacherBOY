# Brainstorm: HF Pro, Buckets, Memory, and Ollama-to-HF Path

## Topic
Investigate whether Hugging Face Pro features — especially Storage Buckets and conversational “memory”-style capabilities — make it practical to host an Ollama model on HF and use it directly for user questions and translations in TeacherBOY.

## Approaches
1. **Treat HF as full backend** — upload a fine-tuned Hermes Ollama model to HF Hub, use HF Inference Endpoints/Spaces for inference, and store chat memory in HF Buckets/datasets.
2. **Use HF as cold storage only** — upload Ollama weights to HF for distribution/backup, keep runtime inference on local/EC2/VPS, and optionally offload conversation logs to HF Buckets.
3. **Hybrid inference + memory** — run Ollama locally for latency/cost, and push user conversations/memory to HF Space/Bucket for persistence, webhooks, or analytics.

## Recommendation
Approach 1 only if the user needs a fully hosted, zero-ops backend and can tolerate cold-start latency and runtime cost; for a Telegram/LINE bot serving low-latency translations, approach 3 is more practical: keep inference local and use HF mainly for asset hosting and long-term memory.

But before recommending any path, hard constraints must be checked:
- TeacherBOY may not use the Maton AI API key for HF Space operations (project constraint).
- Only provider APIs excluded by config may be omitted; the active provider order matters.
- Provider behavior changes require provider-contract tests (TDD).
