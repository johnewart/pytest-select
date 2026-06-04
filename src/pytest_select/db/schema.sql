-- files
CREATE TABLE IF NOT EXISTS files (
  path TEXT PRIMARY KEY,
  mtime REAL,
  sha256 TEXT
);

-- module-level and symbol-level nodes
CREATE TABLE IF NOT EXISTS symbols (
  id INTEGER PRIMARY KEY,
  file_path TEXT NOT NULL,
  qualname TEXT NOT NULL,
  kind TEXT NOT NULL,
  UNIQUE(file_path, qualname)
);

-- directed edges: source depends on target
CREATE TABLE IF NOT EXISTS deps (
  id INTEGER PRIMARY KEY,
  source_file TEXT NOT NULL,
  source_symbol TEXT,
  target_file TEXT NOT NULL,
  target_symbol TEXT,
  edge_kind TEXT NOT NULL,
  line INTEGER
);

CREATE INDEX IF NOT EXISTS idx_deps_target ON deps(target_file);
CREATE INDEX IF NOT EXISTS idx_deps_source ON deps(source_file);

-- tests (from pytest collection)
CREATE TABLE IF NOT EXISTS tests (
  nodeid TEXT PRIMARY KEY,
  file_path TEXT NOT NULL,
  name TEXT NOT NULL,
  markers TEXT
);

-- test → code it touches
CREATE TABLE IF NOT EXISTS test_coverage (
  test_nodeid TEXT NOT NULL,
  file_path TEXT NOT NULL,
  symbol_qualname TEXT NOT NULL DEFAULT '',
  depth INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (test_nodeid, file_path, symbol_qualname)
);

CREATE INDEX IF NOT EXISTS idx_test_coverage_file ON test_coverage(file_path);

-- per-test scores (computed at index time)
CREATE TABLE IF NOT EXISTS test_scores (
  test_nodeid TEXT PRIMARY KEY,
  impact REAL NOT NULL,
  cost REAL NOT NULL,
  files_reached INTEGER NOT NULL DEFAULT 0,
  symbols_reached INTEGER NOT NULL DEFAULT 0
);

-- optional historical durations (v2)
CREATE TABLE IF NOT EXISTS test_runs (
  nodeid TEXT NOT NULL,
  duration_ms REAL NOT NULL,
  timestamp REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_test_runs_nodeid ON test_runs(nodeid);
