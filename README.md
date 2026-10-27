# Human Brain Memory Framework

**人脑记忆框架 · 1.0 Beta** · MIT · Python 3.11+ · AstrBot 4.29.x

[English](README.en.md) · [架构与接口](docs/ARCHITECTURE.md) · [发布指南](docs/PUBLISHING.md) · [版本记录](CHANGELOG.md)

让机器人记住发生过的事，按话题想起，随时间淡忘，再把经历整理成长期认识。
本项目从个人 QQ Agent 的记忆系统抽象而来，提供不依赖机器人平台的 Python 核心，以及 AstrBot 插件入口。

> 当前为 `v1.0.0-beta.1`（1.0 Beta）。后台总结依赖模型输出，可能存在错误；所有自动改写标为推断。
> 当前会话的数据会发送给你在 AstrBot 中选择的模型／向量服务。原始聊天最多记录每条 4000 字，可配置。

## 功能

| 能力 | 行为 |
| --- | --- |
| 事实记忆 | 工具保存当前用户的事实或原文；命令可明确确认和纠正 |
| 经历 | 默认空闲 30 分钟、至少 2 条消息后，生成 0–3 条经历并保留消息依据 |
| 每日整理 | 默认北京时间 04:00 后，按批提炼事实、人物画像、自我回顾、待跟进事项 |
| 语义召回 | 中文单字／双字关键词 + 可选 AstrBot embedding，失败自动降级 |
| 遗忘 | `exp(-天数/强度)`；低于 5% 冻结，冻结 30 天进回收站；置顶和重要性 ≥8 的不冻结 |
| 强化 | 相关回忆每天最多 ×1.8；背景补位每天最多 ×1.2，补位强度最高 30 天 |
| 情绪 | 强烈情绪让经历衰减更慢；核心 API 支持按当前心情轻微调整排序 |
| 概括 | 快遗忘的经历合成“那段时间”，保留大概，原经历不改写 |
| 待跟进 | 日期到了或再次聊天时加入背景；每人每会话最多 5 条，每轮最多 3 条 |
| 可恢复 | 原子写入、持久化游标、指数退避重试、回收站、整理批次日志、冲突检测撤销、轮换备份 |

## 安装到 AstrBot

1. 运行 AstrBot **4.29.x**（元数据允许 `>=4.29,<5`），启用一个聊天模型。其他版本暂未验证。
2. 在 AstrBot WebUI 的插件管理中使用 `https://github.com/Yurdos-r/human_brain_memory` 安装；仓库尚未发布时，可用 Release ZIP 本地安装。
3. 若当前 WebUI 不提供 ZIP 安装，将 ZIP 解压到 AstrBot 的 `data/plugins/`，确保结构如下，然后重新加载插件：

   ```text
   data/plugins/astrbot_plugin_human_brain_memory/
     main.py
     metadata.yaml
     _conf_schema.json
     human_brain_memory/
   ```

   外层工作目录可以叫 `Human Brain Memory Framework`；**部署目录请使用上面的下划线名称**，避免 Python 模块名含空格。
4. 在插件配置中选择 `summary_provider_id`（留空跟随当前会话模型）。
5. 可选：先在 AstrBot 中配置 embedding 提供商，再填 `embedding_provider_id`。默认阈值适合 bge-m3，其他模型应自行校准。
6. 发送 `/memory status`；发送 `/memory remember 我不喝咖啡`，再换个话题回来询问，确认注入生效。

手工部署时，在 **AstrBot 使用的 Python 环境**安装 `requirements.txt`。Windows 需要 `tzdata`；插件本身不包含额外聊天模型 SDK。

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

`hbm_remember`、`hbm_recall`、`hbm_plan_followup`、`hbm_finish_followup` 是注册给模型的工具。
工具名带前缀，避免与其他插件冲突。模型不具备管理、跨会话读取或删除记忆的工具。

## 记忆真实性与隐私边界

- 以 **平台实例 ID + 机器人账号 + AstrBot UMO** 构成会话范围，用户标识使用字符串，支持非 QQ 平台。
- 私聊、群聊、不同机器人实例分别隔离。事实、经历、画像、自我回顾、待跟进和撤销日志遵循同一范围。
- 模型不能通过输出 `private:false` 或伪造 `scope` 扩大范围。管理员命令也不会跨会话读取记忆。
- 只默认记录实际进入 LLM 的对话。`record_all_messages=true` 才记录允许会话内未唤醒机器人的消息。
- **相似度只用于检索，不用于证明事实。** 模型改写一律 `inferred`、重要性最多 7；这意味着自动总结不会生成“永不遗忘”的新事实。
- 工具若要标记 `said`，必须保存当前用户的整条原文，不能删掉“不是”等否定词；`said` 表示用户说过／确认过，并不代表客观真理。
- 自动整理可更新旧推断，但不能替换已确认事实。用户通过 `/memory replace` 明确纠正。
- 默认不继承原 QQ Bot 的“主人可读所有人的私聊记忆”能力。共享记忆暂未开放。

## 配置、费用与数据

全部配置项见 [`_conf_schema.json`](_conf_schema.json)，会显示在 AstrBot 插件配置面板。

- 默认每轮最多 12 条、6000 字背景预算，**置顶也受预算限制**。
- 一批最多 80 条消息；失败阶段不会推进游标，指数退避到最长 6 小时后重试，成功阶段无需重做。
- 每分钟轮转最多 10 个会话；每批经历通常一次模型调用，每批每日整理通常一次调用，概括另一次。
- 关键词模式不额外请求向量。向量模式每轮最多两段查询，一批后台补算最多 32 条。
- 新记忆的向量由后台逐步补齐；补齐前仍可关键词召回。更换同名向量服务时更新 `embedding_cache_version`。
- 模型／工具调用开销交由 AstrBot 及供应商统计；本插件没有独立费用看板。
- 原文和回收站数据没有自动物理清除，长期使用应关注磁盘空间。

运行数据位于 AstrBot 的 `data/plugin_data/astrbot_plugin_human_brain_memory/`，不在源码目录：

```text
memory.sqlite3       # SQLite 数据库，运行时可能有 -wal / -shm
backups/             # 每天备份，默认最近 7 份；启动当天也会备份
```

恢复：停止插件或 AstrBot，保留当前数据库及 WAL 的副本，将完整备份放回 `memory.sqlite3`，确保旧 WAL/SHM 不会被错误复用，再启动。不要在运行中直接覆盖数据库。
卸载插件不会主动删除数据。需要彻底清除时，停止插件并删除上述专属数据目录与备份。

## 独立使用核心

```python
from human_brain_memory import MemoryEngine, Store

store = Store("memory.sqlite3")
engine = MemoryEngine(store)  # 不传模型时仍支持手工记忆与关键词召回
engine.remember("my-app:chat-1", "user-1", "我不喝咖啡", explicit=True)
# 在异步函数中：
# items = await engine.recall("my-app:chat-1", "user-1", "饮料")
store.close()
```

安装 `pip install .` 只安装 `human_brain_memory` 核心；AstrBot 插件需要整个仓库／ZIP，不能用核心 wheel 代替。
完整模型适配契约见 [ARCHITECTURE](docs/ARCHITECTURE.md)。

## 开发与验证

```bash
python -m venv .venv
# 激活虚拟环境后：
python -m pip install -e ".[dev]"
python -m ruff check .
python -m pytest -q
python scripts/package_release.py
```

GitHub Actions 配置了 Windows/Linux、Python 3.11/3.12 测试矩阵。测试使用临时数据库和假模型，**不会调用真实模型或修改原 QQ Bot 数据**。
`dist/` 输出 ZIP、内容清单和 SHA-256。打包采用源码白名单，不包含数据库、密钥、虚拟环境和旧 QQ Bot。

## Beta 范围

保留记忆核心机制，AstrBot 接管短期上下文和平台通信。没有移植 QQ 登录、天气、说说、媒体收藏、作息模拟或原 Web 控制台。
自我回顾仅依据本插件记录的对话；不自动读取 AstrBot 其他插件的日记／工具活动。
人物画像不走普通事实的遗忘曲线；后续每日整理会更新它。跟进事项只影响后续回复，不主动发消息。
目前不自动迁移原 QQ Bot 数据库，两者 schema 和隐私范围不同。

适配接口已对照 AstrBot 4.29.3 源码，自动化测试包含适配层契约测试；真实平台发送、实际模型输出质量和多插件并行效果仍需部署后验证。

## 来源与许可

基于本地 QQ Agent 的记忆分层、召回、遗忘、经历整理和跟进设计重新抽象。未打包 AstrBot 源码或原项目的运行数据。
AstrBot 是宿主框架，通过公开 SDK 使用。项目采用 [MIT](LICENSE) 许可证。
