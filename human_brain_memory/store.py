"""SQLite persistence with atomic batches, scoped IDs and optimistic undo."""

import json
import sqlite3
import threading
import time
import uuid
from contextlib import closing, contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
 scope TEXT PRIMARY KEY, origin TEXT NOT NULL, provider TEXT NOT NULL DEFAULT '',
 last_active REAL NOT NULL, episode_cursor INTEGER NOT NULL DEFAULT 0,
 consolidate_cursor INTEGER NOT NULL DEFAULT 0, consolidated_day TEXT NOT NULL DEFAULT '',
 retry_at REAL NOT NULL DEFAULT 0, failures INTEGER NOT NULL DEFAULT 0,
 last_error TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS messages (
 id INTEGER PRIMARY KEY, scope TEXT NOT NULL, event_key TEXT NOT NULL,
 role TEXT NOT NULL, subject TEXT NOT NULL, name TEXT NOT NULL,
 content TEXT NOT NULL, ts REAL NOT NULL, UNIQUE(scope,event_key,role)
);
CREATE INDEX IF NOT EXISTS messages_scope ON messages(scope,id);
CREATE TABLE IF NOT EXISTS memories (
 id INTEGER PRIMARY KEY, scope TEXT NOT NULL, subject TEXT NOT NULL,
 content TEXT NOT NULL, kind TEXT NOT NULL, basis TEXT NOT NULL,
 importance INTEGER NOT NULL, strength REAL NOT NULL, created REAL NOT NULL,
 last_recalled REAL, last_seen REAL, recall_count INTEGER NOT NULL DEFAULT 0,
 status TEXT NOT NULL DEFAULT 'active', status_ts REAL NOT NULL,
 pinned INTEGER NOT NULL DEFAULT 0, emotion TEXT NOT NULL DEFAULT '', intensity INTEGER NOT NULL DEFAULT 0,
 evidence TEXT NOT NULL DEFAULT '[]', gist_id INTEGER,
 version INTEGER NOT NULL DEFAULT 1,
 UNIQUE(scope,subject,kind,content)
);
CREATE INDEX IF NOT EXISTS memories_scope ON memories(scope,status);
CREATE TABLE IF NOT EXISTS profiles (
 id INTEGER PRIMARY KEY, scope TEXT NOT NULL, subject TEXT NOT NULL,
 content TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1, UNIQUE(scope,subject)
);
CREATE TABLE IF NOT EXISTS followups (
 id INTEGER PRIMARY KEY, scope TEXT NOT NULL, subject TEXT NOT NULL,
 content TEXT NOT NULL, due TEXT NOT NULL DEFAULT '', created REAL NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending', version INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS vectors (
 memory_id INTEGER NOT NULL, model TEXT NOT NULL, content TEXT NOT NULL, vector TEXT NOT NULL,
 PRIMARY KEY(memory_id,model)
);
CREATE TABLE IF NOT EXISTS runs (
 id TEXT PRIMARY KEY, scope TEXT NOT NULL, created REAL NOT NULL,
 changes TEXT NOT NULL, undone INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS recall_log (
 id INTEGER PRIMARY KEY, scope TEXT NOT NULL, created REAL NOT NULL, items TEXT NOT NULL
);
PRAGMA user_version = 1;
"""


class Store:
    def __init__(self, path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self.depth = 0
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA busy_timeout=5000")
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version > 1:
            self.db.close()
            raise ValueError("Database belongs to a newer plugin; refusing to downgrade")
        self.db.executescript(SCHEMA)

    @contextmanager
    def transaction(self):
        # No await inside this block. Savepoints make caught nested failures safe too.
        with self.lock:
            point = f"memory_tx_{self.depth}"
            self.db.execute(f"SAVEPOINT {point}")
            self.depth += 1
            try:
                yield
            except BaseException:
                self.db.execute(f"ROLLBACK TO {point}")
                self.db.execute(f"RELEASE {point}")
                raise
            else:
                self.db.execute(f"RELEASE {point}")
            finally:
                self.depth -= 1

    def execute(self, sql, args=()):
        with self.lock:
            return self.db.execute(sql, args)

    def rows(self, sql, args=()):
        with self.lock:
            return [dict(r) for r in self.db.execute(sql, args).fetchall()]

    def one(self, sql, args=()):
        rows = self.rows(sql, args)
        return rows[0] if rows else None

    def session(self, scope):
        return self.one("SELECT * FROM sessions WHERE scope=?", (scope,))

    def record(self, scope, origin, provider, key, role, subject, name, content, now=None):
        now = time.time() if now is None else now
        with self.transaction():
            self.execute(
                "INSERT INTO sessions(scope,origin,provider,last_active) VALUES(?,?,?,?) "
                "ON CONFLICT(scope) DO UPDATE SET origin=excluded.origin, "
                "provider=CASE WHEN excluded.provider!='' THEN excluded.provider ELSE sessions.provider END, "
                "last_active=MAX(sessions.last_active,excluded.last_active)",
                (scope, origin, provider, now),
            )
            self.execute(
                "INSERT OR IGNORE INTO messages(scope,event_key,role,subject,name,content,ts) VALUES(?,?,?,?,?,?,?)",
                (scope, key, role, subject, name, content, now),
            )
        return self.one("SELECT id FROM messages WHERE scope=? AND event_key=? AND role=?", (scope, key, role))["id"]

    def messages(self, scope, after=0, limit=80):
        return self.rows("SELECT * FROM messages WHERE scope=? AND id>? ORDER BY id LIMIT ?", (scope, after, limit))

    def recent(self, scope, limit=4):
        return list(reversed(self.rows("SELECT * FROM messages WHERE scope=? ORDER BY id DESC LIMIT ?", (scope, limit))))

    def memory(self, scope, mid):
        return self.one("SELECT * FROM memories WHERE scope=? AND id=?", (scope, mid))

    def candidates(self, scope):
        return self.rows("SELECT * FROM memories WHERE scope=? AND status IN ('active','frozen')", (scope,))

    def add_memory(self, scope, subject, content, kind="fact", importance=5, basis="inferred",
                   evidence=(), emotion="", intensity=0, now=None):
        from .recall import initial_strength
        now = time.time() if now is None else now
        existing = self.one("SELECT * FROM memories WHERE scope=? AND subject=? AND kind=? AND content=?",
                            (scope, subject, kind, content))
        # Re-extraction never silently resurrects a user's deleted/corrected fact.
        if existing:
            return existing["id"], False
        importance = max(1, min(10 if basis == "said" else 7, int(importance)))
        cur = self.execute(
            "INSERT INTO memories(scope,subject,content,kind,basis,importance,strength,created,status_ts,evidence,emotion,intensity) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (scope, subject, content, kind, basis, importance, initial_strength(importance, kind, intensity),
             now, now, json.dumps(list(evidence)), emotion, intensity),
        )
        return cur.lastrowid, True

    def snapshot(self, table, row_id):
        if table not in {"memories", "profiles", "followups"}:
            raise ValueError("Unsupported journal table")
        return self.one(f"SELECT * FROM {table} WHERE id=?", (row_id,))

    def journal(self, scope, changes):
        run = uuid.uuid4().hex
        self.execute("INSERT INTO runs VALUES(?,?,?,?,0)", (run, scope, time.time(), json.dumps(changes, ensure_ascii=False)))
        return run

    def undo(self, scope, run):
        with self.transaction():
            row = self.one("SELECT * FROM runs WHERE id=? AND scope=? AND undone=0", (run, scope))
            if not row:
                return False
            changes = json.loads(row["changes"])
            # Validate the whole batch before changing anything. Refuse stale/cascading undo.
            expected = {}
            for c in reversed(changes):
                key = (c["table"], c["id"])
                current = expected[key] if key in expected else self.snapshot(*key)
                if current != c["after"]:
                    raise ValueError("这批记录后来已变化，不能安全撤销；请逐条处理。")
                expected[key] = c["before"]
            for c in reversed(changes):
                table = c["table"]
                if c["before"] is None:
                    self.execute(f"DELETE FROM {table} WHERE id=?", (c["id"],))
                    if table == "memories":
                        self.execute("DELETE FROM vectors WHERE memory_id=?", (c["id"],))
                else:
                    old = c["before"]
                    cols = list(old)
                    self.execute(f"UPDATE {table} SET " + ",".join(f"{k}=?" for k in cols) + " WHERE id=?",
                                 (*[old[k] for k in cols], c["id"]))
            self.execute("UPDATE runs SET undone=1 WHERE id=?", (run,))
            return True

    def backup(self, directory, keep=7):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"memory-{time.time_ns()}.sqlite3"
        with self.lock, closing(sqlite3.connect(target)) as dest:
            self.db.backup(dest)
        for old in sorted(directory.glob("memory-*.sqlite3"), reverse=True)[keep:]:
            old.unlink()
        return target

    def close(self):
        with self.lock:
            self.db.close()
