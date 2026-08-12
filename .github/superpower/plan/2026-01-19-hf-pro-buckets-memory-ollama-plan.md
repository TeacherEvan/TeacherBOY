# Plan: Investigate HF Pro, Buckets, Memory, and Ollama-to-HF

## Goal
Answer one concrete question for Evan: given the current situation, can we rely on Hugging Face Pro features, specifically Buckets and Memory, toward the target of using Hugging Face as a hosting destination for an Ollama model in order to handle user questions and translations? On the Hugging Face plan/pricing side, treat the existing plan as authoritative; for official Hugging Face storage limits details I will fall back to survey then external sources if the current tools cannot reach them.

## Findings so far
- Pricing page already supports: Pro, Team, Enterprise tiers.
- Storage docs are visible in the fetched page content, but I have not yet confirmed whether the documents tool can also reach it independently.

## Tasks
1. Extract concrete Pro/Buckets/Memory feature list from existing repo docs and prior session scan.
2. Inspect project code to see which HF features are already used (models, Spaces, dataset viewer, etc.).
3. Define the runtime policy constraints on use of Maton AI API key and LLM providers vs storage/auth/inference.
4. Assess Ollama-to-HF path: model download, upload, inference approach, quota implications.
5. Write a single recommendation for next steps.

## Commands/Tools
- `rerank` if available, else `discover` and `scroll`.
- Project code search for HF references.
- Document tool for repo sources.
- Final output: one short decision statement with evidence.
