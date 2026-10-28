"""Adapter contract tests: minimal public SDK doubles, no real providers or bot data."""

import asyncio
import importlib
import importlib.util
import logging
import re
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


class Event:
    def __init__(self, text='hello', user='alice', group='', platform='p1', bot='bot1', admin=False, mid='1'):
        self.text, self.user, self.group, self.platform, self.bot, self.admin = text, user, group, platform, bot, admin
        self.unified_msg_origin = f'{platform}:{"group" if group else "private"}:{group or user}'
        self.message_obj = SimpleNamespace(message_id=mid)
        self.extras = {}

    def get_platform_id(self):
        return self.platform

    def get_self_id(self):
        return self.bot

    def get_sender_id(self):
        return self.user

    def get_sender_name(self):
        return self.user

    def get_message_str(self):
        return self.text

    def get_extra(self, key, default=None):
        return self.extras.get(key, default)

    def set_extra(self, key, value):
        self.extras[key] = value

    def plain_result(self, text):
        return text

    def is_admin(self):
        return self.admin

    def is_private_chat(self):
        return not self.group


class Context:
    def __init__(self):
        self.calls = []

    def get_provider_by_id(self, provider_id):
        return None

    async def get_current_chat_provider_id(self, umo):
        return 'test-provider'

    async def llm_generate(self, *, chat_provider_id, system_prompt, prompt):
        self.calls.append((chat_provider_id, system_prompt, prompt))
        return SimpleNamespace(completion_text='{"episodes": []}')


@pytest.fixture
def plugin_class(monkeypatch, tmp_path):
    def decorator(*args, **kwargs):
        def wrap(fn):
            return fn
        return wrap

    def llm_tool(*args, **kwargs):
        # AstrBot rejects tool docstring types outside JSON schema's basic set at import time.
        def wrap(fn):
            for name, kind in re.findall(r'^\s+(\w+)\((\w+)\):', fn.__doc__ or '', re.M):
                assert kind in {'string', 'number', 'object', 'array', 'boolean'}, f'{fn.__name__}.{name}: {kind}'
            return fn
        return wrap

    class Star:
        def __init__(self, context):
            self.context = context

    fake = {
        'astrbot': {},
        'astrbot.api': {'AstrBotConfig': dict, 'logger': logging.getLogger('adapter-test')},
        'astrbot.api.event': {'AstrMessageEvent': Event, 'filter': SimpleNamespace(
            event_message_type=decorator, on_llm_request=decorator, on_llm_response=decorator,
            llm_tool=llm_tool, command=decorator, EventMessageType=SimpleNamespace(ALL=7))},
        'astrbot.api.provider': {'LLMResponse': SimpleNamespace, 'ProviderRequest': SimpleNamespace},
        'astrbot.api.star': {'Star': Star, 'Context': Context, 'StarTools': SimpleNamespace(get_data_dir=lambda name: tmp_path)},
    }
    for name, members in fake.items():
        module = ModuleType(name)
        module.__dict__.update(members)
        monkeypatch.setitem(sys.modules, name, module)
    package = 'hbm_test_plugin'
    spec = importlib.util.spec_from_file_location(package, ROOT/'__init__.py', submodule_search_locations=[str(ROOT)])
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, package, mod)
    spec.loader.exec_module(mod)
    for name in list(sys.modules):
        if name.startswith(package+'.'):
            monkeypatch.delitem(sys.modules, name)
    cls = importlib.import_module(package+'.main').HumanBrainMemoryPlugin
    yield cls
    for name in list(sys.modules):
        if name.startswith(package+'.'):
            sys.modules.pop(name, None)


@pytest.fixture
def plugin(plugin_class):
    p = plugin_class(Context(), {})
    yield p
    p.store.close()


async def command(p, event):
    return '\n'.join([result async for result in p.memory_command(event)])


async def test_capture_inject_response_dedupe(plugin):
    event = Event('我不喝咖啡')
    req = SimpleNamespace(system_prompt='ORIGINAL', contexts=[{'role': 'user', 'content': 'untouched'}])
    await plugin.inject_memory(event, req)
    first = req.system_prompt
    await plugin.inject_memory(event, req)
    assert req.system_prompt == first and req.contexts == [{'role': 'user', 'content': 'untouched'}]
    scope, subject, _ = plugin._identity(event)
    assert len(plugin.store.messages(scope)) == 1
    assert '已记住' in await plugin.remember_tool(event, '我不喝咖啡', exact_quote=True)
    await plugin.record_response(event, SimpleNamespace(completion_text='记住了'))
    await plugin.record_response(event, SimpleNamespace(completion_text='记住了'))
    assert len(plugin.store.messages(scope)) == 2
    assert plugin.store.candidates(scope)[0]['basis'] == 'said'
    assert plugin.store.candidates(scope)[0]['subject'] == subject


async def test_private_not_in_group_or_other_instance(plugin):
    event = Event('/memory remember PRIVATE_SECRET')
    await command(plugin, event)
    for other in (Event('PRIVATE_SECRET', group='g1'), Event('PRIVATE_SECRET', platform='p2'), Event('PRIVATE_SECRET', bot='bot2')):
        req = SimpleNamespace(system_prompt='')
        await plugin.inject_memory(other, req)
        assert 'PRIVATE_SECRET' not in req.system_prompt


async def test_default_no_passive_capture_and_allowlist(plugin_class):
    event = Event()
    p = plugin_class(Context(), {'session_allowlist': ['different']})
    await p.observe(event)
    req = SimpleNamespace(system_prompt='base')
    await p.inject_memory(event, req)
    assert req.system_prompt == 'base' and not p.store.rows('SELECT * FROM messages')
    assert '未启用' in await p.recall_tool(event, 'hello')
    p.store.close()


async def test_commands_own_memories_and_admin_scope(plugin):
    owner = Event('/memory remember Alice fact', group='g1')
    await command(plugin, owner)
    scope, subject, _ = plugin._identity(owner)
    mid = plugin.store.candidates(scope)[0]['id']
    stranger = Event(f'/memory forget {mid}', group='g1', user='bob')
    assert '没有可管理' in await command(plugin, stranger)
    assert '管理员' in await command(plugin, Event('/memory consolidate', group='g1'))
    admin_other = Event(f'/memory forget {mid}', group='g2', admin=True)
    assert '没有可管理' in await command(plugin, admin_other)
    assert plugin.store.memory(scope, mid)['status'] == 'active'
    assert '已更新' in await command(plugin, Event(f'/memory forget {mid}', group='g1', admin=True))


async def test_provider_callback_and_tool_permission(plugin):
    event = Event('你好')
    await plugin.inject_memory(event, SimpleNamespace(system_prompt=''))
    scope, _, _ = plugin._identity(event)
    result = await plugin._generate(scope, 'system', 'prompt')
    assert result == '{"episodes": []}'
    assert plugin.context.calls == [('test-provider', 'system', 'prompt')]
    assert '原文记录必须' in await plugin.remember_tool(event, '我是医生', exact_quote=True)


async def test_lifecycle_cancel_and_close(plugin_class):
    p = plugin_class(Context(), {})
    await p.initialize()
    task = p.worker
    await p.initialize()
    assert p.worker is task and not task.done()
    await p.terminate()
    assert task.cancelled() and p.worker is None
    assert not any(t.get_name() == 'human-brain-memory' for t in asyncio.all_tasks())


async def test_commands_do_not_lose_spaces(plugin):
    result = await command(plugin, Event('/memory remember I do not drink coffee'))
    assert '已确认' in result
    scope, _, _ = plugin._identity(Event())
    assert plugin.store.candidates(scope)[0]['content'] == 'I do not drink coffee'


async def test_number_tool_arguments_accept_floats(plugin):
    event = Event('下周提醒我体检')
    await plugin.inject_memory(event, SimpleNamespace(system_prompt=''))
    assert '已记住' in await plugin.remember_tool(event, '要去体检', importance=6.0)
    fid = int((await plugin.followup_tool(event, '体检')).split('#')[1].rstrip('。'))
    assert await plugin.finish_tool(event, float(fid)) == '已完成。'
