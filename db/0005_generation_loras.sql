CREATE TABLE generation_loras (
  request_id TEXT PRIMARY KEY NOT NULL REFERENCES generation_requests(id),
  selection_json TEXT NOT NULL
);
