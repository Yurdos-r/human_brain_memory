# Changelog

## 1.0.0-beta.1 — 2026-10-27

First standalone beta of **Human Brain Memory Framework（人脑记忆框架）**.

- Framework-independent SQLite memory engine; AstrBot event and tool adapter.
- Facts, episodes, scoped profiles, self reflections, fading-episode gists and followups.
- Chinese keyword recall plus optional embeddings from AstrBot providers.
- Decay, bounded background reinforcement, frozen-memory revival after selection.
- Atomic episode batches, persistent cursors, bounded exponential retry and backup rotation.
- Strict session isolation for raw and derived data; no model-controlled privacy flags.
- Exact user quotes and explicit commands are distinguished from generated inferences.
- Model-generated corrections cannot replace user-confirmed facts.
- Scoped management commands, change journal and optimistic batch undo.
