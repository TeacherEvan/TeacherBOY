# Diagnosis summary

- Symptom confirmed: production/current translation path returns no usable output.
- Verified cause: Google Translate returns 400 with invalid API key from current env.
- Verified evidence:
  - Existing tests fail with same Google 400.
  - Fast probe shows Thai → English falls back to Nous successfully, so the provider chain itself is functional.
- Secondary blocker: current tests assert provider order that no longer matches runtime behavior after recent fix commit.
