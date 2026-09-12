-- Planned metadata schema: SQLite / Cloudflare D1. No service is connected yet.
-- Binary audio, images and video live in object storage; this stores their keys.
PRAGMA foreign_keys = ON;
CREATE TABLE projects (
  id TEXT PRIMARY KEY NOT NULL,
  name TEXT NOT NULL CHECK(length(trim(name)) BETWEEN 1 AND 80),
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE TABLE generation_requests (
  id TEXT PRIMARY KEY NOT NULL,
  project_id TEXT NOT NULL REFERENCES projects(id),
  title TEXT NOT NULL,
  request_json TEXT NOT NULL,
  take_count INTEGER NOT NULL CHECK(take_count IN (1, 2)),
  status TEXT NOT NULL CHECK(status IN ('draft','preparing','queued','running','completed','failed','cancelled')),
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE TABLE takes (
  id TEXT PRIMARY KEY NOT NULL,
  request_id TEXT NOT NULL REFERENCES generation_requests(id),
  project_id TEXT NOT NULL REFERENCES projects(id),
  take_index INTEGER NOT NULL CHECK(take_index IN (1, 2)),
  title TEXT NOT NULL,
  style_summary TEXT NOT NULL DEFAULT '',
  favorite INTEGER NOT NULL DEFAULT 0 CHECK(favorite IN (0, 1)),
  status TEXT NOT NULL CHECK(status IN ('draft','queued','running','ready','failed','cancelled')),
  seed TEXT, -- Exact 63-bit integer carried as text through JavaScript/JSON.
  duration_ms INTEGER CHECK(duration_ms >= 0),
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  UNIQUE(request_id, take_index)
);
CREATE TABLE assets (
  id TEXT PRIMARY KEY NOT NULL,
  take_id TEXT NOT NULL REFERENCES takes(id),
  kind TEXT NOT NULL CHECK(kind IN ('audio','cover','video')),
  format TEXT NOT NULL,
  storage_key TEXT,
  status TEXT NOT NULL CHECK(status IN ('requested','running','ready','failed')),
  provider TEXT,
  model TEXT,
  prompt TEXT,
  created_at INTEGER NOT NULL,
  CHECK(status != 'ready' OR storage_key IS NOT NULL),
  UNIQUE(take_id, kind, format)
);
CREATE INDEX takes_project_created ON takes(project_id, created_at DESC);
CREATE INDEX takes_status_created ON takes(status, created_at DESC);
CREATE INDEX takes_favorites ON takes(favorite, created_at DESC);
CREATE INDEX requests_project ON generation_requests(project_id, created_at DESC);
CREATE INDEX assets_take ON assets(take_id);
