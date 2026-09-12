CREATE TABLE generation_jobs (
  id TEXT PRIMARY KEY NOT NULL,
  take_id TEXT NOT NULL UNIQUE REFERENCES takes(id),
  state TEXT NOT NULL CHECK(state IN ('queued','waiting-for-resource','running','needs-review','succeeded','failed','cancelled')),
  stage TEXT NOT NULL DEFAULT 'queued',
  attempt INTEGER NOT NULL DEFAULT 0,
  cancel_requested INTEGER NOT NULL DEFAULT 0 CHECK(cancel_requested IN (0,1)),
  progress_json TEXT NOT NULL DEFAULT '{}',
  error TEXT,
  output_key TEXT,
  resume_plan_key TEXT,
  edited_abc TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX jobs_state_created ON generation_jobs(state, created_at);
