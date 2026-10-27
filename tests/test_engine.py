import asyncio
import json
import sqlite3
from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from human_brain_memory import MemoryConfig, MemoryEngine, Store
from human_brain_memory.engine import InvalidOutput, parse_object
from human_brain_memory.recall import DAY, retention

SCOPE, OTHER, USER = 'platform:private:one', 'platform:group:two', 'user:one'
EMPTY = {"facts": [], "profiles": [], "reflections": [], "followups": []}


class Model:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    async def __call__(self, scope, system, prompt):
        self.calls.append((scope, system, prompt))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False)


@pytest.fixture
def clock():
    return [datetime(2026, 10, 27, 12, tzinfo=ZoneInfo("Asia/Shanghai")).timestamp()]


@pytest.fixture
def engine(clock):
    e = MemoryEngine(Store(":memory:"), config=MemoryConfig(), now=lambda: clock[0])
    yield e
    e.store.close()


def record(e, text="我不是医生", subject=USER, scope=SCOPE, key="1", role="user"):
    return e.record(scope, scope, "fake", key, role, subject, subject, text)


def episode(ids):
    return {"episodes": [{"content": "用户明确说自己不是医生", "importance": 5, "evidence": ids, "emotion": "平静", "intensity": 0}]}


def test_event_deduplication_and_scope(engine):
    first = record(engine)
    assert record(engine) == first
    assert record(engine, scope=OTHER) != first
    assert len(engine.store.messages(SCOPE)) == 1


@pytest.mark.parametrize("text", ['{}', '{"episodes":null}', '{"episodes":"oops"}', 'not json'])
async def test_invalid_episode_keeps_cursor(engine, text):
    record(engine)
    engine.generate = Model(text)
    with pytest.raises(InvalidOutput):
        await engine.maintain(SCOPE, force=True)
    state = engine.store.session(SCOPE)
    assert state['episode_cursor'] == 0 and state['failures'] == 1
    assert not engine.store.candidates(SCOPE)


async def test_episode_atomic_write(engine, monkeypatch):
    mid = record(engine)
    engine.generate = Model({"episodes": [episode([mid])["episodes"][0],
                                          {"content": "第二条", "evidence": [mid]}]})
    real = engine.store.add_memory
    count = 0

    def flaky(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 2:
            raise RuntimeError("disk")
        return real(*args, **kwargs)

    monkeypatch.setattr(engine.store, "add_memory", flaky)
    with pytest.raises(RuntimeError):
        await engine.maintain(SCOPE, force=True)
    assert not engine.store.candidates(SCOPE)
    assert engine.store.session(SCOPE)["episode_cursor"] == 0
    assert engine.store.rows("SELECT * FROM runs") == []


async def test_partial_success_retries_only_failed_stage(engine, clock):
    mid = record(engine)
    model = Model(episode([mid]), {}, EMPTY)
    engine.generate = model
    with pytest.raises(InvalidOutput):
        await engine.maintain(SCOPE, force=True)
    state = engine.store.session(SCOPE)
    assert state['episode_cursor'] == mid and state['consolidate_cursor'] == 0
    clock[0] += DAY
    await engine.maintain(SCOPE)
    assert engine.store.session(SCOPE)['consolidate_cursor'] == mid
    assert len(model.calls) == 3 and len(engine.store.candidates(SCOPE)) == 1


async def test_claims_are_inferred_and_cannot_replace_said(engine):
    old = engine.remember(SCOPE, USER, "我在上海工作", explicit=True)
    mid = record(engine, "你好")
    data = {**EMPTY, "facts": [{"subject": USER, "content": "用户在北京工作", "importance": 9,
                               "evidence": [mid], "replaces": [old]}]}
    engine.generate = Model({"episodes": []}, data)
    await engine.maintain(SCOPE, force=True)
    memories = engine.store.candidates(SCOPE)
    assert len(memories) == 2
    assert engine.store.memory(SCOPE, old)['status'] == 'active'
    new = next(m for m in memories if m['id'] != old)
    assert new['basis'] == 'inferred' and new['importance'] == 7


def test_exact_quote_cannot_drop_negation_or_steal_speaker(engine):
    mid = record(engine)
    with pytest.raises(ValueError):
        engine.remember(SCOPE, USER, "我是医生", quote="我是医生", evidence_id=mid)
    with pytest.raises(ValueError):
        engine.remember(SCOPE, "other-user", "我不是医生", quote="我不是医生", evidence_id=mid)
    remembered = engine.remember(SCOPE, USER, "我不是医生", quote="我不是医生", evidence_id=mid)
    assert engine.store.memory(SCOPE, remembered)['basis'] == 'said'


async def test_all_derived_data_stays_in_source_scope(engine):
    mid = record(engine)
    data = {"facts": [{"subject": USER, "content": "私密事实", "evidence": [mid]}],
            "reflections": [{"content": "私密回顾", "evidence": [mid], "private": False, "scope": OTHER}],
            "profiles": [{"subject": USER, "content": "私密画像", "evidence": [mid]}],
            "followups": [{"subject": USER, "content": "私密跟进", "evidence": [mid], "due": ""}]}
    engine.generate = Model(episode([mid]), data)
    await engine.maintain(SCOPE, force=True)
    assert engine.store.candidates(OTHER) == []
    context = await engine.context(OTHER, USER, "私密")
    for secret in ("私密事实", "私密回顾", "私密画像", "私密跟进"):
        assert secret not in context
    assert '私密画像' in await engine.context(SCOPE, USER, "私密")


async def test_cross_scope_evidence_rejected_before_writes(engine):
    record(engine)
    foreign = record(engine, scope=OTHER)
    engine.generate = Model({"episodes": []}, {**EMPTY, "facts": [
        {"subject": USER, "content": "错误引用", "evidence": [foreign]}]})
    with pytest.raises(InvalidOutput):
        await engine.maintain(SCOPE, force=True)
    assert not engine.store.candidates(SCOPE)


async def test_filler_cap_and_selected_only_revival(engine, clock):
    mid = engine.remember(SCOPE, USER, "喜欢咖啡", explicit=True)
    for _ in range(30):
        clock[0] += DAY
        await engine.recall(SCOPE, USER, "xyz")
    m = engine.store.memory(SCOPE, mid)
    assert m['strength'] == 30 and m['recall_count'] == 0
    assert retention(m, clock[0]+100*DAY) < 0.05
    ids = [engine.remember(SCOPE, USER, s) for s in ("考研数学", "考研英语")]
    for i in ids:
        engine.store.execute("UPDATE memories SET status='frozen' WHERE id=?", (i,))
    engine.config = replace(engine.config, inject_limit=1)
    chosen = await engine.recall(SCOPE, USER, "考研数学考研英语")
    assert len(chosen) == 1
    assert sorted(engine.store.memory(SCOPE, i)['status'] for i in ids) == ['active', 'frozen']


async def test_character_budget_precedes_revival(engine):
    mid = engine.remember(SCOPE, USER, "考研" * 100)
    engine.store.execute("UPDATE memories SET status='frozen' WHERE id=?", (mid,))
    assert await engine.recall(SCOPE, USER, "考研", budget=10) == []
    assert engine.store.memory(SCOPE, mid)['status'] == 'frozen'


async def test_context_budget_includes_profiles(engine):
    engine.config = replace(engine.config, context_chars=500)
    engine.store.execute("INSERT INTO profiles(scope,subject,content) VALUES(?,?,?)", (SCOPE, USER, "甲"*1200))
    for i in range(4):
        engine.remember(SCOPE, USER, f'事实{i}' + '甲'*100)
    assert len(await engine.context(SCOPE, USER, '甲')) <= 500


async def test_vector_backfill_edit_invalidation_and_fallback(engine):
    async def embed(texts):
        return [[1., 0.] if '考试' in t or '压力' in t else [0., 1.] for t in texts]
    engine.embed, engine.model_key = embed, 'model-1'
    mid = engine.remember(SCOPE, USER, '准备考试')
    await engine.backfill(SCOPE)
    got = await engine.recall(SCOPE, USER, '压力', search=True)
    assert got[0]['id'] == mid
    engine.store.execute("UPDATE memories SET content='去吃饭' WHERE id=?", (mid,))
    assert await engine.recall(SCOPE, USER, '压力', search=True) == []
    await engine.backfill(SCOPE)

    async def fail(texts):
        raise RuntimeError('provider private payload')
    engine.embed = fail
    assert (await engine.recall(SCOPE, USER, '吃饭', search=True))[0]['id'] == mid
    assert engine.embedding_error == 'RuntimeError'


async def test_vector_bad_values_are_rejected(engine):
    async def embed(texts):
        return [[float('nan')] for _ in texts]
    engine.embed, engine.model_key = embed, 'bad'
    engine.remember(SCOPE, USER, '考研')
    await engine.backfill(SCOPE)
    assert engine.store.rows('SELECT * FROM vectors') == []
    assert engine.embedding_error == 'ValueError'


async def test_forgetting_during_embedding_cannot_reinject_deleted_fact(engine):
    mid = engine.remember(SCOPE, USER, '私人事实')
    async def embed(texts):
        engine.change(SCOPE, USER, mid, 'trash')
        return [[1., 0.] for _ in texts]
    engine.embed, engine.model_key = embed, 'test'
    assert await engine.recall(SCOPE, USER, '私人事实') == []
    assert engine.store.memory(SCOPE, mid)['status'] == 'trash'


async def test_cancelled_batch_does_not_commit(engine):
    record(engine)
    async def wait(*args):
        raise asyncio.CancelledError()
    engine.generate = wait
    with pytest.raises(asyncio.CancelledError):
        await engine.maintain(SCOPE, force=True)
    assert engine.store.session(SCOPE)['episode_cursor'] == 0


def test_nested_transaction_rollback(engine):
    with engine.store.transaction():
        engine.remember(SCOPE, USER, '保留')
        with pytest.raises(RuntimeError), engine.store.transaction():
            engine.remember(SCOPE, USER, '撤回')
            raise RuntimeError()
    assert [m['content'] for m in engine.store.candidates(SCOPE)] == ['保留']


async def test_undo_batch_and_conflicts(engine):
    mid = record(engine)
    engine.generate = Model({"episodes": []}, {**EMPTY, 'facts': [
        {'subject': USER, 'content': '事实', 'evidence': [mid]}], 'profiles': [
        {'subject': USER, 'content': '画像', 'evidence': [mid]}]})
    runs = await engine.maintain(SCOPE, force=True)
    assert not engine.store.undo(OTHER, runs[-1])
    assert engine.store.undo(SCOPE, runs[-1])
    assert not engine.store.candidates(SCOPE)
    assert not engine.store.rows('SELECT * FROM profiles')
    assert not engine.store.undo(SCOPE, runs[-1])
    fact = engine.remember(SCOPE, USER, '其他事实')
    run = engine.store.one('SELECT id FROM runs ORDER BY created DESC,rowid DESC LIMIT 1')['id']
    engine.change(SCOPE, USER, fact, 'pin')
    with pytest.raises(ValueError):
        engine.store.undo(SCOPE, run)
    assert engine.store.memory(SCOPE, fact)['pinned']


def test_permissions_and_deleted_facts_not_resurrected(engine):
    mid = engine.remember(SCOPE, USER, '咖啡')
    with pytest.raises(ValueError):
        engine.change(OTHER, USER, mid, 'trash', admin=True)
    with pytest.raises(ValueError):
        engine.change(SCOPE, 'stranger', mid, 'trash')
    engine.change(SCOPE, USER, mid, 'trash')
    assert engine.remember(SCOPE, USER, '咖啡') == mid
    assert engine.store.memory(SCOPE, mid)['status'] == 'trash'


def test_explicit_correction(engine):
    mid = engine.remember(SCOPE, USER, '以前喝咖啡', explicit=True)
    new = engine.replace_explicit(SCOPE, USER, mid, '现在戒咖啡了')
    assert engine.store.memory(SCOPE, mid)['status'] == 'trash'
    assert engine.store.memory(SCOPE, new)['basis'] == 'said'
    run = engine.store.one('SELECT id FROM runs ORDER BY created DESC,rowid DESC LIMIT 1')['id']
    assert engine.store.undo(SCOPE, run)
    assert engine.store.memory(SCOPE, mid)['status'] == 'active'
    assert engine.store.memory(SCOPE, new) is None


def test_explicit_confirmation_upgrades_inference(engine):
    mid = engine.remember(SCOPE, USER, '不喝咖啡')
    assert engine.store.memory(SCOPE, mid)['basis'] == 'inferred'
    assert engine.remember(SCOPE, USER, '不喝咖啡', explicit=True) == mid
    assert engine.store.memory(SCOPE, mid)['basis'] == 'said'


async def test_backlog_processed_without_skipping(engine, clock):
    engine.config = replace(engine.config, batch_messages=2)
    for i in range(5):
        record(engine, f'消息{i}', key=str(i))
    clock[0] += DAY
    engine.generate = Model({'episodes': []}, EMPTY, {'episodes': []}, EMPTY, {'episodes': []}, EMPTY)
    for _ in range(3):
        await engine.maintain(SCOPE)
    assert engine.store.session(SCOPE)['episode_cursor'] == 5
    assert engine.store.session(SCOPE)['consolidate_cursor'] == 5
    assert len(engine.generate.calls) == 6


async def test_gist_retries_after_daily_consolidation_completed(engine, clock):
    record(engine)
    engine.store.add_memory(SCOPE, '@scene', '旧经历', 'episode', 1, now=clock[0]-4*DAY)
    clock[0] += DAY
    engine.generate = Model({'episodes': []}, EMPTY, RuntimeError('model'), {'content': '旧日概括'})
    await engine.maintain(SCOPE)
    state = engine.store.session(SCOPE)
    assert state['consolidate_cursor'] == 1 and state['failures'] == 1
    clock[0] += 180
    await engine.maintain(SCOPE)
    assert any(m['kind'] == 'gist' for m in engine.store.candidates(SCOPE))


async def test_followup_scope_limits_and_expiry(engine, clock):
    record(engine)
    fid, _ = engine.plan(SCOPE, USER, '问考试', '2026-10-28')
    assert '问考试' not in await engine.context(SCOPE, USER, '你好')
    clock[0] += DAY
    assert '问考试' in await engine.context(SCOPE, USER, '你好')
    assert not engine.finish(OTHER, USER, fid)
    assert not engine.finish(SCOPE, 'stranger', fid)
    assert engine.finish(SCOPE, USER, fid)
    for i in range(5):
        engine.plan(SCOPE, USER, f'follow{i}')
    with pytest.raises(ValueError):
        engine.plan(SCOPE, USER, 'full')
    clock[0] += 31*DAY
    await engine.maintain(SCOPE)
    assert not engine.store.rows("SELECT * FROM followups WHERE status='pending'")


async def test_gist_and_undo(engine, clock):
    record(engine)
    for i in range(3):
        engine.store.add_memory(SCOPE, '@scene', f'经历{i}', 'episode', 2, now=clock[0]-5*DAY)
    engine.generate = Model({'content': '那段时间聊了许多', 'importance': 5})
    await engine._gist(SCOPE)
    m = engine.store.candidates(SCOPE)
    assert len(m) == 4 and all(r['gist_id'] for r in m if r['kind'] == 'episode')
    run = engine.store.one('SELECT id FROM runs')['id']
    assert engine.store.undo(SCOPE, run)
    assert len(engine.store.candidates(SCOPE)) == 3
    assert all(r['gist_id'] is None for r in engine.store.candidates(SCOPE))


async def test_restart_preserves_progress_and_backups(tmp_path, clock):
    path = tmp_path/'memory.sqlite3'
    s = Store(path)
    e = MemoryEngine(s, now=lambda: clock[0])
    mid = record(e)
    e.generate = Model({'episodes': []}, EMPTY)
    await e.maintain(SCOPE, force=True)
    for _ in range(3):
        backup = s.backup(tmp_path/'backups', keep=2)
    assert len(list((tmp_path/'backups').glob('*.sqlite3'))) == 2
    with sqlite3.connect(backup) as db:
        assert db.execute('SELECT COUNT(*) FROM messages').fetchone()[0] == 1
    s.close()
    s = Store(path)
    assert s.session(SCOPE)['episode_cursor'] == mid and s.session(SCOPE)['consolidate_cursor'] == mid
    s.close()


@pytest.mark.parametrize('kwargs', [{'inject_limit': 0}, {'context_chars': 10}, {'semantic_floor': .8}, {'consolidate_hour': 24}])
def test_invalid_config(kwargs):
    with pytest.raises(ValueError):
        MemoryConfig(**kwargs)


def test_parse_fenced_json():
    assert parse_object('```json\n{"episodes": []}\n```') == {'episodes': []}
    with pytest.raises(InvalidOutput):
        parse_object('[]')
