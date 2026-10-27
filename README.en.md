# Human Brain Memory Framework

**1.0 Beta** (`v1.0.0-beta.1`) · MIT · Python 3.11+ · AstrBot 4.29.x

[中文说明](README.md)

A standalone memory engine extracted from a personal QQ agent, with an AstrBot adapter.
It supports facts, episodes, scoped profiles, self reflections, fading-episode gists,
followups, lexical/semantic retrieval, bounded reinforcement, decay, frozen memories,
atomic processing, retries, audit records, safe undo, and rotating SQLite backups.

## Install

Install the published GitHub repository through AstrBot's plugin manager, or unpack the
release ZIP under `data/plugins/astrbot_plugin_human_brain_memory/` and reload plugins.
The deployed directory must use this underscore name, not the display name containing spaces.
For manual deployment, install `requirements.txt` in AstrBot's Python environment.

Configure `summary_provider_id` (empty follows the current conversation's provider) and
optionally `embedding_provider_id`. These are AstrBot provider IDs, not API keys.
The default cosine thresholds target bge-m3; calibrate them for other models.

Try `/memory help`, `/memory remember I do not drink coffee`, and `/memory search coffee`.
Administrators can run `/memory consolidate`, inspect `/memory runs`, and undo a batch.
Backups are only available in administrator private chats.

## Privacy and correctness

All raw and derived data is isolated by platform instance, bot account, and conversation UMO.
The model cannot widen visibility with generated flags. Administrators do not bypass scopes.
Only LLM-triggering conversations are recorded by default; passive capture is opt-in.

Similarity is used for retrieval, **not entailment**. Generated paraphrases remain inferences
and cannot replace user-confirmed facts. Exact-quote storage preserves the entire current
user message, including negation; explicit corrections use `/memory replace`.
Inference is not truth verification: review important memories before relying on them.

Data is stored under `data/plugin_data/astrbot_plugin_human_brain_memory/`. Configured model
and embedding providers receive the relevant text. Nothing is sent to a hardcoded service.
Uninstallation does not intentionally delete data. Stop the plugin before restoring backups.

## Core API

`pip install .` installs only the independent `human_brain_memory` package. Provide asynchronous
generation/embedding callbacks to `MemoryEngine`; the core imports neither AstrBot nor an LLM SDK.
See [architecture](docs/ARCHITECTURE.md) for the callback contract.

## Development and release

```bash
python -m pip install -e ".[dev]"
python -m ruff check .
python -m pytest -q
python scripts/package_release.py
```

The ZIP uses an explicit source allowlist and excludes credentials, databases and virtual environments.
Read [publishing](docs/PUBLISHING.md) before uploading the first beta.

This beta has deterministic core and adapter tests, and SDK contracts checked against AstrBot 4.29.3.
It has not been certified against a live AstrBot deployment. No automatic import of the original QQ
bot database, standalone dashboard, cross-session sharing, or proactive message delivery is included.
