-- migrate:up
-- Alpha schema rationalization:
-- `tags`, `task_tags`, and `images` are no longer part of the runtime model.
-- This migration removes those redundant tables.
PRAGMA foreign_keys=OFF;

DROP TABLE IF EXISTS task_tags;
DROP TABLE IF EXISTS images;
DROP TABLE IF EXISTS tags;

PRAGMA foreign_keys=ON;
