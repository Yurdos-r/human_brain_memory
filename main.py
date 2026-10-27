"""AstrBot integration for Human Brain Memory Framework 1.0 Beta."""

import asyncio
import hashlib
import json
import uuid
from contextlib import suppress

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.provider import LLMResponse, ProviderRequest
from astrbot.api.star import Context, Star, StarTools

from .human_brain_memory import MemoryConfig, MemoryEngine, Store
from .human_brain_memory.recall import dumps

PLUGIN = "astrbot_plugin_human_brain_memory"
HELP = """Human Brain Memory Framework · 1.0 Beta
/memory status — 本会话状态（含会话标识）
/memory list [active|frozen|trash] — 自己的记忆，管理员可看本会话全部
/memory remember 内容 — 确认保存自己的事实
/memory search 关键词 — 检索本会话
/memory forget|restore|pin|unpin 编号 — 管理记忆
/memory replace 编号 新内容 — 明确纠正自己的事实
/memory profile — 查看自己的画像
/memory followups — 查看自己的待跟进
/memory consolidate — 整理一批（管理员）
/memory runs — 整理批次（管理员）
/memory undo 批次编号 — 安全撤销（管理员）
/memory backup — 数据库备份（管理员私聊）
所有数据按会话隔离；不会跨群或跨私聊检索。"""


class HumanBrainMemoryPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.settings = config
        self.memory_config = MemoryConfig.from_mapping(config)
        self.data_dir = StarTools.get_data_dir(PLUGIN)
        self.store = Store(self.data_dir / "memory.sqlite3")
        self.engine = MemoryEngine(self.store, generate=self._generate, config=self.memory_config)
        self.worker = None
        self.rotation = 0
        self.backup_day = ""
        self._refresh_embedding()

    def _identity(self, event):
        # UMO may be user-configured. Include adapter instance and bot account as well.
        origin = str(event.unified_msg_origin)
        parts = [str(event.get_platform_id()), str(event.get_self_id()), origin]
        scope = json.dumps(parts, ensure_ascii=False, separators=(",", ":"))
        subject = json.dumps([parts[0], str(event.get_sender_id())], ensure_ascii=False, separators=(",", ":"))
        return scope, subject, origin

    def _allowed(self, event):
        allowed = self.settings.get("session_allowlist", [])
        return self.memory_config.enabled and (not allowed or str(event.unified_msg_origin) in allowed)

    def _require(self, event):
        if not self._allowed(event):
            raise ValueError("此会话未启用人脑记忆。")
        return self._identity(event)

    def _event_key(self, event):
        key = event.get_extra("hbm_event_key")
        if not key:
            mid = str(getattr(event.message_obj, "message_id", "") or "")
            if mid:
                # Some adapters only provide conversation-local IDs; the DB also scopes them.
                key = mid
            else:
                key = uuid.uuid4().hex
            event.set_extra("hbm_event_key", key)
        return key

    async def _record_user(self, event, provider=""):
        scope, subject, origin = self._identity(event)
        content = event.get_message_str()
        if not content.strip():
            return None
        mid = self.engine.record(scope, origin, provider, self._event_key(event), "user", subject,
                                 event.get_sender_name(), content)
        event.set_extra("hbm_message_id", mid)
        return mid

    def _refresh_embedding(self):
        provider_id = str(self.settings.get("embedding_provider_id", "")).strip()
        provider = self.context.get_provider_by_id(provider_id) if provider_id else None
        if provider and callable(getattr(provider, "get_embeddings", None)):
            self.engine.embed = provider.get_embeddings
            # Model/config changes get a different cache key. Never persist API keys.
            version = str(self.settings.get("embedding_cache_version", "1"))
            self.engine.model_key = hashlib.sha256(
                json.dumps([provider_id, provider.get_model(), version]).encode()
            ).hexdigest()
        else:
            self.engine.embed, self.engine.model_key = None, ""

    async def _generate(self, scope, system, prompt):
        session = self.store.session(scope)
        provider_id = str(self.settings.get("summary_provider_id", "")).strip()
        if not provider_id and session:
            provider_id = await self.context.get_current_chat_provider_id(session["origin"])
        if not provider_id:
            raise RuntimeError("No summary provider available")
        response = await self.context.llm_generate(
            chat_provider_id=provider_id, system_prompt=system, prompt=prompt,
        )
        return response.completion_text

    async def initialize(self):
        if self.memory_config.enabled and self.worker is None:
            self.worker = asyncio.create_task(self._run(), name="human-brain-memory")

    async def terminate(self):
        if self.worker:
            self.worker.cancel()
            with suppress(asyncio.CancelledError):
                await self.worker
            self.worker = None
        self.store.close()

    async def _run(self):
        while True:
            await asyncio.sleep(60)
            try:
                self._refresh_embedding()
                sessions = self.store.rows("SELECT scope,origin FROM sessions ORDER BY scope")
                allowed = self.settings.get("session_allowlist", [])
                sessions = [s for s in sessions if not allowed or s["origin"] in allowed]
                if sessions:
                    self.rotation %= len(sessions)
                    ordered = sessions[self.rotation:] + sessions[:self.rotation]
                    for session in ordered[:10]:
                        await self.engine.maintain(session["scope"])
                    self.rotation = (self.rotation + min(10, len(sessions))) % len(sessions)
                today = self.engine.today().date().isoformat()
                if self.backup_day != today:
                    await asyncio.to_thread(self.store.backup, self.data_dir / "backups", self.memory_config.backup_keep)
                    self.backup_day = today
            except Exception as exc:
                logger.warning("Human Brain Memory background error: %s", type(exc).__name__)

    @filter.event_message_type(filter.EventMessageType.ALL, priority=-10)
    async def observe(self, event: AstrMessageEvent):
        if self._allowed(event) and self.settings.get("record_all_messages", False):
            # Commands are not facts or ordinary chat material.
            if event.get_message_str().lstrip().startswith(("/memory", "memory ")):
                return
            await self._record_user(event)

    @filter.on_llm_request()
    async def inject_memory(self, event: AstrMessageEvent, req: ProviderRequest):
        if not self._allowed(event):
            return
        try:
            scope, subject, _ = self._identity(event)
            provider = await self.context.get_current_chat_provider_id(str(event.unified_msg_origin))
            await self._record_user(event, provider)
            self._refresh_embedding()
            block = await self.engine.context(scope, subject, event.get_message_str())
            # The same request may pass hooks twice. Never alter the conversation history.
            previous = event.get_extra("hbm_context_block", "")
            if previous and (req.system_prompt or "").endswith(previous):
                req.system_prompt = req.system_prompt[:-len(previous)]
            req.system_prompt = (req.system_prompt or "") + block
            event.set_extra("hbm_context_block", block)
        except Exception as exc:
            logger.warning("Human Brain Memory injection skipped: %s", type(exc).__name__)

    @filter.on_llm_response()
    async def record_response(self, event: AstrMessageEvent, response: LLMResponse):
        if not self._allowed(event) or not response.completion_text:
            return
        scope, _, origin = self._identity(event)
        # This is the generated response, not proof that platform delivery succeeded.
        self.engine.record(scope, origin, "", self._event_key(event), "assistant", "@self", "assistant", response.completion_text)

    @filter.llm_tool(name="hbm_remember")
    async def remember_tool(self, event: AstrMessageEvent, content: str, importance: int = 5, exact_quote: bool = False) -> str:
        """记住当前用户在当前会话的事实。改写内容一律标记为推断，不可替换已确认事实。

        Args:
            content(string): 记忆内容；exact_quote=true 时必须等于用户当前整条消息，保留否定和主体。
            importance(integer): 重要性 1–10，推断上限为 7。
            exact_quote(boolean): 是否保存用户当前整条原话，默认 false。
        """
        try:
            scope, subject, _ = self._require(event)
            mid = self.engine.remember(scope, subject, content, importance,
                                       quote=content if exact_quote else "", evidence_id=event.get_extra("hbm_message_id"))
            return f"已记住 #{mid}。"
        except (ValueError, TypeError) as exc:
            return str(exc)

    @filter.llm_tool(name="hbm_recall")
    async def recall_tool(self, event: AstrMessageEvent, query: str) -> str:
        """检索本会话的长期记忆，包含可重新唤醒的冻结记忆。

        Args:
            query(string): 关键词或一句描述。
        """
        try:
            scope, subject, _ = self._require(event)
            return dumps(await self.engine.recall(scope, subject, query, search=True))
        except ValueError as exc:
            return str(exc)

    @filter.llm_tool(name="hbm_plan_followup")
    async def followup_tool(self, event: AstrMessageEvent, content: str, due: str = "") -> str:
        """记下以后要跟进当前用户的事；只加入背景，不会主动发送消息。

        Args:
            content(string): 要跟进的事情。
            due(string): YYYY-MM-DD；留空表示下次遇到当前用户。
        """
        try:
            scope, subject, _ = self._require(event)
            fid, _ = self.engine.plan(scope, subject, content, due)
            return f"已记下待跟进 #{fid}。"
        except ValueError as exc:
            return str(exc)

    @filter.llm_tool(name="hbm_finish_followup")
    async def finish_tool(self, event: AstrMessageEvent, followup_id: int) -> str:
        """把本会话当前用户已完成的跟进事项标记为完成。

        Args:
            followup_id(integer): 待跟进编号。
        """
        try:
            scope, subject, _ = self._require(event)
            return "已完成。" if self.engine.finish(scope, subject, followup_id) else "没有可完成的这条事项。"
        except ValueError as exc:
            return str(exc)

    @filter.command("memory")
    async def memory_command(self, event: AstrMessageEvent):
        # Parse the tail ourselves: text with spaces remains intact.
        raw = event.get_message_str().strip().split(maxsplit=1)
        tail = raw[1] if len(raw) > 1 else "help"
        command, _, value = tail.partition(" ")
        command, value = command.lower(), value.strip()
        if command == "help":
            yield event.plain_result(HELP)
            return
        try:
            scope, subject, _ = self._require(event)
            admin = event.is_admin()
            if command in {"consolidate", "runs", "undo", "backup"} and not admin:
                raise ValueError("此操作需要 AstrBot 管理员权限。")
            if command == "status":
                stats = self.engine.stats(scope)
                stats["session_origin"] = str(event.unified_msg_origin)
                result = dumps(stats)
            elif command == "remember":
                result = f"已确认记住 #{self.engine.remember(scope, subject, value, explicit=True)}。"
            elif command == "search":
                result = dumps(await self.engine.recall(scope, subject, value, search=True))
            elif command == "list":
                status = value or "active"
                if status not in {"active", "frozen", "trash"}:
                    raise ValueError("状态必须为 active / frozen / trash。")
                sql, args = "SELECT id,subject,content,kind,basis,pinned FROM memories WHERE scope=? AND status=?", [scope, status]
                if not admin:
                    sql += " AND subject=?"
                    args.append(subject)
                result = dumps(self.store.rows(sql + " ORDER BY id DESC LIMIT 20", args))
            elif command in {"forget", "restore", "pin", "unpin"}:
                self.engine.change(scope, subject, int(value), "trash" if command == "forget" else command, admin)
                result = "已更新。"
            elif command == "replace":
                mid, _, content = value.partition(" ")
                result = f"已纠正为 #{self.engine.replace_explicit(scope, subject, int(mid), content)}。"
            elif command == "profile":
                result = dumps(self.store.rows("SELECT content FROM profiles WHERE scope=? AND subject=?", (scope, subject)))
            elif command == "followups":
                result = dumps(self.store.rows("SELECT id,content,due,status FROM followups WHERE scope=? AND subject=? ORDER BY id DESC LIMIT 20", (scope, subject)))
            elif command == "consolidate":
                result = "本批整理完成：" + ", ".join(await self.engine.maintain(scope, force=True))
            elif command == "runs":
                result = dumps(self.store.rows("SELECT id,created,undone FROM runs WHERE scope=? ORDER BY created DESC,rowid DESC LIMIT 10", (scope,)))
            elif command == "undo":
                result = "已撤销。" if self.store.undo(scope, value) else "没有可撤销的这个批次。"
            elif command == "backup":
                if not event.is_private_chat():
                    raise ValueError("备份命令请在管理员私聊中使用。")
                path = await asyncio.to_thread(self.store.backup, self.data_dir / "backups", self.memory_config.backup_keep)
                result = "备份已保存到插件数据目录的 backups/" + path.name
            else:
                result = HELP
            yield event.plain_result(result)
        except (ValueError, TypeError) as exc:
            yield event.plain_result(str(exc))
        except Exception as exc:
            logger.warning("Human Brain Memory command failed: %s", type(exc).__name__)
            yield event.plain_result("操作失败，已保留进度。请查看本会话 status 和插件日志。")
