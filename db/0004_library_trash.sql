-- Recoverable deletion; original audio and generation records remain intact.
ALTER TABLE takes ADD COLUMN deleted_at INTEGER;
CREATE INDEX takes_deleted_created ON takes(deleted_at, created_at DESC);
