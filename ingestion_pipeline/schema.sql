PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS documents (
  doc_id        TEXT PRIMARY KEY,
  source_path   TEXT,
  source_uri    TEXT,
  title         TEXT,
  language      TEXT,
  content_hash  TEXT,
  ingested_at   TEXT
);

CREATE TABLE IF NOT EXISTS sections (
  section_id        TEXT PRIMARY KEY,
  doc_id            TEXT NOT NULL REFERENCES documents(doc_id),
  parent_section_id TEXT,
  heading           TEXT,
  heading_level     INTEGER,
  heading_path      TEXT,
  first_block_id    TEXT,
  last_block_id     TEXT,
  token_count       INTEGER,
  char_start        INTEGER,
  char_end          INTEGER
);

CREATE TABLE IF NOT EXISTS blocks (
  block_id        TEXT PRIMARY KEY,
  doc_id          TEXT NOT NULL REFERENCES documents(doc_id),
  section_id      TEXT REFERENCES sections(section_id),
  parent_block_id TEXT,
  prev_block_id   TEXT,
  next_block_id   TEXT,
  list_id         TEXT,
  block_type      TEXT,
  heading_path    TEXT,
  order_index     INTEGER,
  char_start      INTEGER,
  char_end        INTEGER,
  token_count     INTEGER,
  char_count      INTEGER,
  text            TEXT,
  content_hash    TEXT,
  is_orphan       INTEGER DEFAULT 0,
  is_boilerplate  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS atoms (
  atom_id       TEXT PRIMARY KEY,
  block_id      TEXT NOT NULL REFERENCES blocks(block_id),
  doc_id        TEXT NOT NULL REFERENCES documents(doc_id),
  section_id    TEXT REFERENCES sections(section_id),
  atom_type     TEXT,
  order_index   INTEGER,
  char_start    INTEGER,
  char_end      INTEGER,
  token_count   INTEGER,
  text          TEXT,
  content_hash  TEXT
);

CREATE INDEX IF NOT EXISTS idx_blocks_doc      ON blocks(doc_id);
CREATE INDEX IF NOT EXISTS idx_blocks_section  ON blocks(section_id);
CREATE INDEX IF NOT EXISTS idx_atoms_doc       ON atoms(doc_id);
CREATE INDEX IF NOT EXISTS idx_atoms_section   ON atoms(section_id);
CREATE INDEX IF NOT EXISTS idx_atoms_block     ON atoms(block_id);
CREATE INDEX IF NOT EXISTS idx_atoms_hash      ON atoms(content_hash);
CREATE INDEX IF NOT EXISTS idx_sections_doc    ON sections(doc_id);
CREATE INDEX IF NOT EXISTS idx_sections_parent ON sections(parent_section_id);
