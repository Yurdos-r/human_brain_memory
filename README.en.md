# Human Brain Memory Framework

**0.1.1** (`v0.1.1`) · MIT · Python 3.11+ · AstrBot 4.29.x

[中文说明](README.md) · [Architecture and API](docs/ARCHITECTURE.md) · [Changelog](CHANGELOG.md)

Give conversational applications a lasting memory: remember facts and experiences, recall them when relevant, and gradually turn past conversations into longer-term understanding.

Human Brain Memory Framework provides an **AstrBot plugin** and an independent **Python memory engine** for integration into other applications.

## Capabilities

| Capability | What it does |
| --- | --- |
| Facts | Store preferences, habits and important information with explicit confirmation and correction |
| Episodes | Summarize conversations into experiences with message references and emotional context |
| Profiles and reflections | Periodically update impressions of users and the bot's own reflections |
| Keyword and semantic recall | Retrieve memories for the current topic, with optional embeddings for semantically related wording |
| Forgetting and reinforcement | Let ordinary memories fade, reinforce relevant recollections, pin important records and revive frozen memories |
| Episode gists | Condense fading experiences into a broader impression of a period |
| Followups | Add pending topics to reply context when their date arrives or the conversation resumes |
| Session isolation | Keep memories scoped to a platform instance, bot account and conversation |
| Memory management | Search, correct, pin, restore, undo consolidation batches and back up the database |

## How memory works

1. Record user and assistant messages that enter the model conversation by default.
2. Summarize episodes after 30 idle minutes and at least two new messages by default.
3. Consolidate facts, profiles, reflections and followups in batches after 04:00 Asia/Shanghai by default.
4. Retrieve relevant memories before a reply and include profiles and pending followups in the model's context.
5. Gradually fade ordinary memories into frozen or trash states, reinforce relevant recollections, and summarize fading episodes into gists.

Profiles are updated during daily consolidation. Followups support subsequent replies and can be inspected with `/memory followups`.

## Install in AstrBot

1. Prepare Python 3.11+ and AstrBot 4.29.x with a chat model enabled.
2. Install `https://github.com/Yurdos-r/human_brain_memory` through AstrBot's plugin manager, or download the [release ZIP](https://github.com/Yurdos-r/human_brain_memory/releases/tag/v0.1.1).
3. For manual installation, extract the ZIP into `data/plugins/astrbot_plugin_human_brain_memory/`, install `requirements.txt` in AstrBot's Python environment, and reload plugins. `main.py` and `metadata.yaml` should be directly inside that plugin directory.
4. Configure `summary_provider_id`, or leave it empty to use the current conversation's model.
5. Optionally configure an AstrBot embedding provider and set `embedding_provider_id`.
6. Send `/memory status` to check the plugin.

## Try it

```text
/memory remember I do not drink coffee
/memory search coffee
/memory list
```

Related memories become context for later replies. Keyword mode matches words such as “coffee”; an embedding provider adds semantic retrieval for related wording.

Use the ID returned by search or list commands to pin a memory, correct it or restore it from trash.

## Commands

| Command | Purpose |
| --- | --- |
| `/memory help` | Show command help |
| `/memory status` | Show session statistics and processing status |
| `/memory remember content` | Explicitly save a fact about yourself |
| `/memory search keywords` | Search memories visible in this session |
| `/memory list [active\|frozen\|trash]` | List recent memories; users see their own, administrators see the current session |
| `/memory replace ID content` | Correct a fact |
| `/memory pin ID`, `/memory unpin ID` | Pin or unpin a memory |
| `/memory forget ID`, `/memory restore ID` | Move a memory to trash or restore it |
| `/memory profile`, `/memory followups` | View your profile or pending followups |
| `/memory consolidate` | Administrator: process a consolidation batch |
| `/memory runs`, `/memory undo BATCH_ID` | Administrator: inspect or undo a batch in this session |
| `/memory backup` | Administrator private chat: back up the plugin database |

The model has four tools: `hbm_remember`, `hbm_recall`, `hbm_plan_followup` and `hbm_finish_followup`.

## Configuration

Configure the plugin through AstrBot's settings panel. All options are listed in [`_conf_schema.json`](_conf_schema.json).

| Setting | Default | Purpose |
| --- | --- | --- |
| `summary_provider_id` | Empty | Use the conversation's model, or select a provider for consolidation |
| `embedding_provider_id` | Empty | Use keyword recall, or select an embedding provider for semantic recall |
| `inject_limit` / `context_chars` | 12 / 6000 | Limit memories and characters included in reply context, including pinned records |
| `episode_idle_minutes` | 30 | Idle time before episode processing |
| `consolidate_hour` / `timezone` | 4 / `Asia/Shanghai` | Daily consolidation schedule |
| `forget` / `emotions` / `gist` / `followups` | Enabled | Enable forgetting, episode emotions, gists and followups |
| `session_allowlist` | Empty list | Restrict recording to selected conversation UMOs shown by `/memory status` |
| `record_all_messages` | Disabled | Also record ordinary text that does not trigger a reply in allowed sessions |
| `backup_keep` | 7 | Number of database backups to retain |

Consolidation calls the selected chat model; semantic retrieval calls the selected embedding provider. Relevant text is sent to those providers. Keyword recall requires no embedding provider. New embeddings are filled in gradually in the background while keyword retrieval remains available.

Default semantic thresholds target bge-m3. Adjust `semantic_floor` and `semantic_ceiling` for other models. Update `embedding_cache_version` after changing a service or vector dimension under the same provider and model name.

## Confirm and manage memories

Explicitly saved information is marked `said`; model-generated summaries are marked `inferred`. Consolidation can update earlier inferences. User-confirmed facts are corrected with `/memory replace`, keeping confirmed information distinct from generated interpretations.

Private chats, groups and bot instances have separate scopes for facts, episodes, profiles, reflections and followups. Users manage their own memories; administrators can inspect and undo batches within the current conversation.

## Data and backups

Data is stored in `data/plugin_data/astrbot_plugin_human_brain_memory/`:

```text
memory.sqlite3
backups/
```

Daily backups retain the latest seven copies by default. Stop the plugin before restoring a complete backup, preserve the current database and WAL files, and ensure stale WAL/SHM files are not reused with the restored database.

Raw messages and trash records remain in the database, including after uninstalling the plugin. To clear them, stop the plugin and remove its data directory and backups.

## Use the Python core

Install the core with `pip install .`. For AstrBot, install the complete repository or plugin ZIP.

```python
from human_brain_memory import MemoryEngine, Store

store = Store("memory.sqlite3")
engine = MemoryEngine(store)
engine.remember("my-app:chat-1", "user-1", "I do not drink coffee", explicit=True)
# Inside an async function:
# items = await engine.recall("my-app:chat-1", "user-1", "coffee")
store.close()
```

Provide asynchronous generation and optional embedding callbacks to enable model-powered processing. See the [architecture and host API](docs/ARCHITECTURE.md) for integration details.

## Development and license

See the [development and publishing guide](docs/PUBLISHING.md) for checks and packaging.

Licensed under [MIT](LICENSE).
