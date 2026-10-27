# Human Brain Memory Framework

**人脑记忆框架 · 1.0 Beta** · MIT · Python 3.11+ · AstrBot 4.29.x

[English](README.en.md) · [架构与接口](docs/ARCHITECTURE.md) · [版本记录](CHANGELOG.md)

让机器人记住发生过的事，按话题想起，随时间淡忘，再把经历整理成长期认识。

Human Brain Memory Framework 为对话应用提供持久化记忆：保存用户事实与聊天经历，整理人物画像，在回复前找回相关内容。框架提供可直接安装的 **AstrBot 插件**，也提供可嵌入其他应用的 **Python 记忆核心**。

## 核心能力

| 能力 | 作用 |
| --- | --- |
| 事实记忆 | 保存用户的偏好、习惯和重要信息，支持明确确认与纠正 |
| 经历记忆 | 将一段对话整理为经历，保留关联消息和情绪信息 |
| 人物画像与自我回顾 | 定期从已记录的对话中整理对用户的认识，以及机器人自身的回顾 |
| 关键词与语义召回 | 按当前话题检索记忆；可选向量模型帮助找回表述不同但语义相关的内容 |
| 遗忘与强化 | 普通记忆随时间淡化，相关回忆得到强化；支持固定重要记忆和唤醒冻结记忆 |
| 经历概括 | 将逐渐淡忘的经历归纳成“那段时间”的概括，保留整体印象 |
| 待跟进事项 | 在日期到达或再次聊天时，将待跟进内容加入回复背景，帮助延续对话 |
| 会话隔离 | 按平台实例、机器人账号和会话分别管理记忆 |
| 记忆管理 | 支持检索、纠正、置顶、回收站恢复、整理批次撤销和数据库备份 |

## 记忆如何工作

1. **记录对话**：默认记录进入模型的用户消息和机器人回复。
2. **整理经历**：默认在聊天空闲 30 分钟、积累至少 2 条新消息后，提炼值得记住的经历。
3. **形成长期认识**：默认每天北京时间 04:00 后分批整理事实、人物画像、自我回顾和待跟进事项。
4. **在需要时想起**：回复前结合当前话题召回相关记忆，并将画像与待跟进事项一起加入模型背景。
5. **逐步淡忘与概括**：普通记忆按遗忘曲线降低保留度，进入冻结或回收站；相关回忆可以被强化或唤醒，部分经历会整理成概括。

人物画像通过每日整理持续更新。待跟进事项用于后续对话中的回应，可通过 `/memory followups` 查看。

## 安装到 AstrBot

1. 准备 **Python 3.11+** 与 **AstrBot 4.29.x**，并在 AstrBot 中启用聊天模型。
2. 在 AstrBot WebUI 的插件管理中，通过仓库地址 `https://github.com/Yurdos-r/human_brain_memory` 安装，或下载 [Release 安装包](https://github.com/Yurdos-r/human_brain_memory/releases/tag/v1.0.0-beta.1)。
3. 若当前 WebUI 不提供 ZIP 安装，将 ZIP 解压到 AstrBot 的 `data/plugins/`，确保结构如下，然后重新加载插件：

   ```text
   data/plugins/astrbot_plugin_human_brain_memory/
     main.py
     metadata.yaml
     _conf_schema.json
     human_brain_memory/
   ```

   部署目录使用 `astrbot_plugin_human_brain_memory`。
4. 在插件配置中选择 `summary_provider_id`（留空跟随当前会话模型）。
5. 可选：先在 AstrBot 中配置 embedding 提供商，再填 `embedding_provider_id`。默认阈值适合 bge-m3，其他模型应自行校准。
6. 发送 `/memory status` 查看状态，按下面的示例保存并检索第一条记忆。

手工部署时，在 **AstrBot 使用的 Python 环境**安装 `requirements.txt`。Windows 的时区支持由依赖项 `tzdata` 提供。

## 快速体验

```text
/memory remember 我不喝咖啡
/memory search 咖啡
/memory list
```

保存后，相关记忆会在后续话题中作为回复背景。关键词模式适合直接查找“咖啡”等词；配置向量模型后，可以进一步按相关语义检索。

从检索结果获取记忆编号后，可执行 `/memory pin 编号` 固定它，或用 `/memory replace 编号 新内容` 更新事实。误删的记忆可以通过 `/memory restore 编号` 恢复。

## 命令

| 命令 | 权限与用途 |
| --- | --- |
| `/memory help` | 查看帮助 |
| `/memory status` | 查看本会话统计、游标、重试状态、UMO |
| `/memory remember 内容` | 当前用户明确保存自己的事实（`said`） |
| `/memory search 关键词` | 检索本会话可见记忆，冻结的可被唤醒 |
| `/memory list [active\|frozen\|trash]` | 普通用户看自己的；管理员看本会话全部；最近 20 条 |
| `/memory forget 编号` | 自己的记忆进入回收站，管理员可管理本会话全部 |
| `/memory restore 编号` | 恢复记忆 |
| `/memory pin 编号`、`/memory unpin 编号` | 固定／取消固定 |
| `/memory replace 编号 新内容` | 明确纠正自己的事实，旧说法进回收站 |
| `/memory profile`、`/memory followups` | 查看自己的画像／待跟进 |
| `/memory consolidate` | 管理员手动整理一批，消息积压时可多次执行 |
| `/memory runs`、`/memory undo 批次编号` | 管理员查看／撤销本会话的批次 |
| `/memory backup` | 管理员私聊：创建整个插件数据库的备份 |

模型可调用四个工具：`hbm_remember` 保存记忆、`hbm_recall` 检索记忆、`hbm_plan_followup` 创建待跟进事项、`hbm_finish_followup` 标记事项完成。

## 常用配置

在 AstrBot 插件配置面板中调整以下选项。完整配置见 [`_conf_schema.json`](_conf_schema.json)。

| 配置 | 默认值 | 用途 |
| --- | --- | --- |
| `summary_provider_id` | 留空 | 跟随当前会话模型，也可指定负责记忆整理的模型 |
| `embedding_provider_id` | 留空 | 留空使用关键词召回；填写 AstrBot 向量提供商 ID 后启用语义召回 |
| `inject_limit` / `context_chars` | 12 / 6000 | 控制每轮记忆条数和背景字符预算，置顶记忆也计入预算 |
| `episode_idle_minutes` | 30 | 空闲多少分钟后整理经历 |
| `consolidate_hour` / `timezone` | 4 / `Asia/Shanghai` | 每日整理的时间与时区 |
| `forget` / `emotions` / `gist` / `followups` | 开启 | 遗忘、经历情绪、经历概括和待跟进功能开关 |
| `session_allowlist` | 空列表 | 设置允许记录的会话；会话 UMO 可通过 `/memory status` 查看 |
| `record_all_messages` | 关闭 | 开启后也记录允许会话内未触发机器人回复的普通文本消息 |
| `backup_keep` | 7 | 保留的数据库备份份数 |

后台整理会调用选定的聊天模型；语义召回会调用选定的向量服务，相关文本随请求发送给这些服务。关键词召回无需向量服务。新记忆的向量会在后台逐步补齐，期间仍可按关键词检索。

默认语义阈值适合 bge-m3，使用其他模型时可调整 `semantic_floor` 和 `semantic_ceiling`。更换同名向量服务或向量维度后，更新 `embedding_cache_version` 以重新计算向量。

## 确认、纠正与管理记忆

用户通过 `/memory remember` 明确保存的信息标记为 `said`；模型整理的内容标记为 `inferred`。自动整理可更新已有推断，已确认的事实则由用户通过 `/memory replace` 纠正。这样可以区分用户确认的信息与模型归纳的认识。

私聊、群聊及不同机器人实例分别保存记忆；事实、经历、画像、回顾和待跟进事项使用同一会话范围。普通用户管理自己的记忆，管理员可在当前会话内查看整理记录并撤销批次。

## 数据与备份

运行数据位于 AstrBot 的 `data/plugin_data/astrbot_plugin_human_brain_memory/`，不在源码目录：

```text
memory.sqlite3       # SQLite 数据库，运行时可能有 -wal / -shm
backups/             # 每天备份，默认最近 7 份；启动当天也会备份
```

恢复：停止插件或 AstrBot，保留当前数据库及 WAL 的副本，将完整备份放回 `memory.sqlite3`，确保旧 WAL/SHM 不会被错误复用，再启动。不要在运行中直接覆盖数据库。
原始消息和回收站记录保存在数据库中，卸载插件后仍会保留。需要清除数据时，停止插件并删除上述专属数据目录与备份。

## 独立使用核心

```python
from human_brain_memory import MemoryEngine, Store

store = Store("memory.sqlite3")
engine = MemoryEngine(store)  # 不传模型时仍支持手工记忆与关键词召回
engine.remember("my-app:chat-1", "user-1", "我不喝咖啡", explicit=True)
# 在异步函数中：
# items = await engine.recall("my-app:chat-1", "user-1", "咖啡")
store.close()
```

安装 `pip install .` 只安装 `human_brain_memory` 核心；AstrBot 插件需要整个仓库／ZIP，不能用核心 wheel 代替。
完整模型适配契约见 [ARCHITECTURE](docs/ARCHITECTURE.md)。

## 开发与许可

核心接口与模型回调说明见 [架构文档](docs/ARCHITECTURE.md)，开发验证和打包流程见 [开发与发布指南](docs/PUBLISHING.md)。

项目采用 [MIT](LICENSE) 许可证。
