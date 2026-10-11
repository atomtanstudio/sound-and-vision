"""The app's records in one SQLite file (WAL): projects, takes, jobs, influence runs and settings. Media lives in
files beside it (data/projects/<pid>/...). Documents are JSON columns so the shape can grow without
migrations; the columns that get queried are real columns."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL DEFAULT '',
  doc TEXT NOT NULL DEFAULT '{}',
  rev INTEGER NOT NULL DEFAULT 1,
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL,
  trashed_at REAL
);
CREATE TABLE IF NOT EXISTS takes (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id),
  n INTEGER NOT NULL,
  model TEXT NOT NULL,
  status TEXT NOT NULL,
  doc TEXT NOT NULL DEFAULT '{}',
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL,
  trashed_at REAL
);
CREATE INDEX IF NOT EXISTS takes_project ON takes(project_id, n);
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  lane TEXT NOT NULL,
  project_id TEXT,
  take_id TEXT,
  status TEXT NOT NULL,
  doc TEXT NOT NULL DEFAULT '{}',
  attempts INTEGER NOT NULL DEFAULT 0,
  created_at REAL NOT NULL,
  started_at REAL,
  finished_at REAL
);
CREATE INDEX IF NOT EXISTS jobs_status ON jobs(status, lane, created_at);
CREATE TABLE IF NOT EXISTS influence_runs (
  id TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  doc TEXT NOT NULL DEFAULT '{}',
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL,
  trashed_at REAL
);
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""


def new_id(prefix: str = "") -> str:
    return prefix + uuid.uuid4().hex[:12]


class Conflict(Exception):
    """A save was based on an older version of the record."""


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript(SCHEMA)
        self.lock = threading.RLock()

    def _q(self, sql: str, *args: Any) -> list[sqlite3.Row]:
        with self.lock:
            return self.db.execute(sql, args).fetchall()

    # ---- projects ----------------------------------------------------------------

    @staticmethod
    def _project(r: sqlite3.Row) -> dict:
        return {"id": r["id"], "title": r["title"], "rev": r["rev"], "createdAt": r["created_at"],
                "updatedAt": r["updated_at"], **json.loads(r["doc"])}

    def create_project(self, title: str, doc: dict) -> dict:
        pid, now = new_id("p"), time.time()
        self._q("INSERT INTO projects(id,title,doc,created_at,updated_at) VALUES(?,?,?,?,?)",
                pid, title, json.dumps(doc), now, now)
        return self.project(pid)

    def project(self, pid: str) -> dict | None:
        rows = self._q("SELECT * FROM projects WHERE id=? AND trashed_at IS NULL", pid)
        return self._project(rows[0]) if rows else None

    def projects(self) -> list[dict]:
        return [self._project(r) for r in self._q(
            "SELECT * FROM projects WHERE trashed_at IS NULL ORDER BY updated_at DESC")]

    def save_project(self, pid: str, title: str, doc: dict, rev: int | None) -> dict:
        """Save the whole document. With rev, refuse a save based on an older version."""
        with self.lock:
            cur = self._q("SELECT rev FROM projects WHERE id=?", pid)
            if not cur:
                raise KeyError(pid)
            if rev is not None and cur[0]["rev"] != rev:
                raise Conflict(pid)
            self._q("UPDATE projects SET title=?, doc=?, rev=rev+1, updated_at=? WHERE id=?",
                    title, json.dumps(doc), time.time(), pid)
        return self.project(pid)

    def patch_project(self, pid: str, **fields: Any) -> dict:
        """Merge fields into the document (server-side changes, e.g. the master take)."""
        with self.lock:
            p = self.project(pid)
            if p is None:
                raise KeyError(pid)
            title = fields.pop("title", p["title"])
            doc = {k: v for k, v in p.items() if k not in ("id", "title", "rev", "createdAt", "updatedAt")}
            doc.update(fields)
            return self.save_project(pid, title, doc, None)

    def trash_project(self, pid: str) -> None:
        self._q("UPDATE projects SET trashed_at=? WHERE id=?", time.time(), pid)

    def trashed_projects(self) -> list[dict]:
        return [{**self._project(r), "trashedAt": r["trashed_at"]} for r in self._q(
            "SELECT * FROM projects WHERE trashed_at IS NOT NULL ORDER BY trashed_at DESC")]

    def restore_project(self, pid: str) -> bool:
        return bool(self._q("SELECT id FROM projects WHERE id=? AND trashed_at IS NOT NULL", pid)) and (
            self._q("UPDATE projects SET trashed_at=NULL, updated_at=? WHERE id=?", time.time(), pid) is not None)

    # ---- takes -------------------------------------------------------------------

    @staticmethod
    def _take(r: sqlite3.Row) -> dict:
        return {"id": r["id"], "projectId": r["project_id"], "n": r["n"], "model": r["model"], "status": r["status"],
                "createdAt": r["created_at"], "updatedAt": r["updated_at"], **json.loads(r["doc"])}

    def create_take(self, pid: str, model: str, doc: dict) -> dict:
        tid, now = new_id("t"), time.time()
        with self.lock:
            n = (self._q("SELECT COALESCE(MAX(n),0)+1 AS n FROM takes WHERE project_id=?", pid)[0]["n"])
            self._q("INSERT INTO takes(id,project_id,n,model,status,doc,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                    tid, pid, n, model, "queued", json.dumps(doc), now, now)
        return self.take(tid)

    def take(self, tid: str) -> dict | None:
        rows = self._q("SELECT * FROM takes WHERE id=?", tid)
        return self._take(rows[0]) if rows else None

    def takes(self, pid: str) -> list[dict]:
        return [self._take(r) for r in self._q(
            "SELECT * FROM takes WHERE project_id=? AND trashed_at IS NULL ORDER BY n DESC", pid)]

    def update_take(self, tid: str, status: str | None = None, **fields: Any) -> dict:
        with self.lock:
            t = self.take(tid)
            if t is None:
                raise KeyError(tid)
            doc = {k: v for k, v in t.items() if k not in ("id", "projectId", "n", "model", "status", "createdAt", "updatedAt")}
            doc.update(fields)
            self._q("UPDATE takes SET status=?, doc=?, updated_at=? WHERE id=?",
                    status or t["status"], json.dumps(doc), time.time(), tid)
        return self.take(tid)

    def trash_take(self, tid: str) -> None:
        self._q("UPDATE takes SET trashed_at=? WHERE id=?", time.time(), tid)

    # ---- jobs --------------------------------------------------------------------

    @staticmethod
    def _job(r: sqlite3.Row) -> dict:
        return {"id": r["id"], "kind": r["kind"], "lane": r["lane"], "projectId": r["project_id"], "takeId": r["take_id"],
                "status": r["status"], "attempts": r["attempts"], "createdAt": r["created_at"],
                "startedAt": r["started_at"], "finishedAt": r["finished_at"], **json.loads(r["doc"])}

    def create_job(self, kind: str, lane: str, doc: dict, project_id: str | None = None, take_id: str | None = None) -> dict:
        jid = new_id("j")
        self._q("INSERT INTO jobs(id,kind,lane,project_id,take_id,status,doc,created_at) VALUES(?,?,?,?,?,?,?,?)",
                jid, kind, lane, project_id, take_id, "queued", json.dumps(doc), time.time())
        return self.job(jid)

    def job(self, jid: str) -> dict | None:
        rows = self._q("SELECT * FROM jobs WHERE id=?", jid)
        return self._job(rows[0]) if rows else None

    def jobs(self, statuses: tuple[str, ...] = ("queued", "running"), project_id: str | None = None) -> list[dict]:
        marks = ",".join("?" * len(statuses))
        sql = f"SELECT * FROM jobs WHERE status IN ({marks})"
        args: list[Any] = list(statuses)
        if project_id:
            sql += " AND project_id=?"
            args.append(project_id)
        return [self._job(r) for r in self._q(sql + " ORDER BY created_at", *args)]

    def next_job(self, lane: str) -> dict | None:
        rows = self._q("SELECT * FROM jobs WHERE status='queued' AND lane=? ORDER BY created_at LIMIT 1", lane)
        return self._job(rows[0]) if rows else None

    def update_job(self, jid: str, status: str | None = None, **fields: Any) -> dict:
        with self.lock:
            j = self.job(jid)
            if j is None:
                raise KeyError(jid)
            keep = ("id", "kind", "lane", "projectId", "takeId", "status", "attempts", "createdAt", "startedAt", "finishedAt")
            doc = {k: v for k, v in j.items() if k not in keep}
            doc.update(fields)
            now = time.time()
            started = now if status == "running" and not j["startedAt"] else j["startedAt"]
            finished = now if status in ("done", "failed", "cancelled") else j["finishedAt"]
            attempts = j["attempts"] + (1 if status == "running" and j["status"] != "running" else 0)
            self._q("UPDATE jobs SET status=?, doc=?, started_at=?, finished_at=?, attempts=? WHERE id=?",
                    status or j["status"], json.dumps(doc), started, finished, attempts, jid)
        return self.job(jid)

    def requeue(self, jid: str, message: str) -> None:
        """A running job handed back by a clean shutdown: queued again, and the start doesn't count as an attempt."""
        with self.lock:
            j = self.job(jid)
            if j and j["status"] == "running":
                self.update_job(jid, "queued", message=message)
                self._q("UPDATE jobs SET attempts=MAX(0, attempts-1) WHERE id=?", jid)

    # ---- influence runs (the Influence Engine) ---------------------------------------

    @staticmethod
    def _run(r: sqlite3.Row) -> dict:
        return {"id": r["id"], "status": r["status"], "createdAt": r["created_at"], "updatedAt": r["updated_at"],
                **json.loads(r["doc"])}

    def create_run(self, status: str, doc: dict) -> dict:
        rid, now = new_id("r"), time.time()
        self._q("INSERT INTO influence_runs(id,status,doc,created_at,updated_at) VALUES(?,?,?,?,?)",
                rid, status, json.dumps(doc), now, now)
        return self.run(rid)

    def run(self, rid: str) -> dict | None:
        rows = self._q("SELECT * FROM influence_runs WHERE id=? AND trashed_at IS NULL", rid)
        return self._run(rows[0]) if rows else None

    def runs(self) -> list[dict]:
        return [self._run(r) for r in self._q(
            "SELECT * FROM influence_runs WHERE trashed_at IS NULL ORDER BY created_at DESC")]

    def update_run(self, rid: str, status: str | None = None, **fields: Any) -> dict:
        with self.lock:
            r = self.run(rid)
            if r is None:
                raise KeyError(rid)
            doc = {k: v for k, v in r.items() if k not in ("id", "status", "createdAt", "updatedAt")}
            doc.update(fields)
            self._q("UPDATE influence_runs SET status=?, doc=?, updated_at=? WHERE id=?",
                    status or r["status"], json.dumps(doc), time.time(), rid)
        return self.run(rid)

    def trash_run(self, rid: str) -> None:
        self._q("UPDATE influence_runs SET trashed_at=? WHERE id=?", time.time(), rid)

    # ---- settings ----------------------------------------------------------------

    def setting(self, key: str, default: Any = None) -> Any:
        rows = self._q("SELECT value FROM settings WHERE key=?", key)
        return json.loads(rows[0]["value"]) if rows else default

    def set_setting(self, key: str, value: Any) -> None:
        self._q("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                key, json.dumps(value))
