-- =====================================================================
-- General web corpus pipeline — v1 schema
-- SQLite. Domain-agnostic. Every stage has its own tables.
--
-- Conventions:
--   * All IDs are TEXT (hash-based, stable across re-runs)
--   * Timestamps are TEXT in ISO8601 UTC
--   * JSON blobs stored as TEXT (SQLite JSON1 extension available if needed)
--   * Booleans stored as INTEGER 0/1
--   * Foreign keys ON — requires PRAGMA foreign_keys = ON at connect time
-- =====================================================================


-- =====================================================================
-- SECTION 1 — Config and runs (observability spine)
-- =====================================================================

CREATE TABLE IF NOT EXISTS corpus_config (
  config_id     TEXT PRIMARY KEY,        -- hash of config content
  name          TEXT,                    -- optional human label, not used by code
  config_json   TEXT NOT NULL,           -- full config blob (YAML→JSON)
  created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
  run_id        TEXT PRIMARY KEY,        -- uuid or hash(timestamp+config)
  config_id     TEXT REFERENCES corpus_config(config_id),
  started_at    TEXT NOT NULL,
  finished_at   TEXT,
  status        TEXT NOT NULL,           -- running | completed | failed
  stages_json   TEXT,                    -- ["fetch","extract","parse","load",...]
  notes         TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_status ON pipeline_runs(status);
CREATE INDEX IF NOT EXISTS idx_runs_started ON pipeline_runs(started_at DESC);

CREATE TABLE IF NOT EXISTS doc_stages (
  run_id        TEXT NOT NULL REFERENCES pipeline_runs(run_id),
  doc_id        TEXT NOT NULL,
  stage         TEXT NOT NULL,           -- fetch|extract|parse|load|enrich|outline|select|synthesize
  status        TEXT NOT NULL,           -- ok | failed | skipped
  started_at    TEXT,
  finished_at   TEXT,
  counts_json   TEXT,                    -- {"blocks":42,"atoms":130}
  error         TEXT,
  PRIMARY KEY (run_id, doc_id, stage)
);
CREATE INDEX IF NOT EXISTS idx_doc_stages_doc ON doc_stages(doc_id);
CREATE INDEX IF NOT EXISTS idx_doc_stages_stage_status ON doc_stages(stage, status);

-- =====================================================================
-- SECTION 2 — Discovery and fetch
-- =====================================================================

CREATE TABLE IF NOT EXISTS url_queue (
  url_id           TEXT PRIMARY KEY,     -- hash(canonical_url)
  url              TEXT NOT NULL,        -- original url
  canonical_url    TEXT NOT NULL,        -- normalized (tracking params stripped)
  discovered_from  TEXT,                 -- url_id of parent, or null for seeds
  domain           TEXT NOT NULL,
  priority         INTEGER DEFAULT 0,
  status           TEXT NOT NULL DEFAULT 'pending',
                                         -- pending|fetching|fetched|rejected|done
  retry_count      INTEGER DEFAULT 0,
  next_attempt_at  TEXT,
  created_at       TEXT NOT NULL,
  updated_at       TEXT NOT NULL,
  UNIQUE(canonical_url)
);
CREATE INDEX IF NOT EXISTS idx_queue_status_priority ON url_queue(status, priority DESC);
CREATE INDEX IF NOT EXISTS idx_queue_domain ON url_queue(domain);
CREATE INDEX IF NOT EXISTS idx_queue_next_attempt ON url_queue(next_attempt_at);

CREATE TABLE IF NOT EXISTS fetches (
  fetch_id           TEXT PRIMARY KEY,   -- hash(url_id + attempt_number)
  url_id             TEXT NOT NULL REFERENCES url_queue(url_id),
  url                TEXT NOT NULL,
  final_url          TEXT,               -- after redirects
  fetched_at         TEXT NOT NULL,
  status_code        INTEGER,
  content_type       TEXT,
  content_length     INTEGER,
  raw_html_path      TEXT,               -- on-disk location of raw HTML
  raw_html_hash      TEXT,
  response_headers_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_fetches_url ON fetches(url_id);
CREATE INDEX IF NOT EXISTS idx_fetches_status ON fetches(status_code);

CREATE TABLE IF NOT EXISTS rejects (
  reject_id      TEXT PRIMARY KEY,
  url_id         TEXT REFERENCES url_queue(url_id),
  url            TEXT NOT NULL,
  reason         TEXT NOT NULL,          -- http_404|http_403|access_denied|
                                         -- paywall|empty_body|redirect_loop|
                                         -- timeout|non_html|other
  status_code    INTEGER,
  detail         TEXT,
  fetched_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rejects_reason ON rejects(reason);
CREATE INDEX IF NOT EXISTS idx_rejects_domain ON rejects(url);

-- =====================================================================
-- SECTION 3 — Documents, structure, atoms
-- =====================================================================

CREATE TABLE IF NOT EXISTS documents (
  doc_id              TEXT PRIMARY KEY,  -- hash(url_id + content_hash)
  url_id              TEXT REFERENCES url_queue(url_id),
  source_url          TEXT NOT NULL,
  canonical_url       TEXT,
  title               TEXT,
  author              TEXT,
  published_at        TEXT,
  updated_at          TEXT,
  language            TEXT,              -- primary language code
  description         TEXT,
  source_type         TEXT,              -- article|docs|forum|wiki|paper|
                                         -- product|social|unknown
  config_id           TEXT REFERENCES corpus_config(config_id),
  frontmatter_json    TEXT,              -- YAML/TOML if present
  content_hash        TEXT NOT NULL,     -- hash of raw markdown
  blocks_hash         TEXT,              -- hash of parsed block sequence
  first_ingested_at   TEXT NOT NULL,
  last_ingested_at    TEXT NOT NULL,
  is_error_page       INTEGER DEFAULT 0, -- fetch succeeded, page is an error
  extra_metadata_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_documents_source_url ON documents(source_url);
CREATE INDEX IF NOT EXISTS idx_documents_domain ON documents(canonical_url);
CREATE INDEX IF NOT EXISTS idx_documents_source_type ON documents(source_type);
CREATE INDEX IF NOT EXISTS idx_documents_content_hash ON documents(content_hash);

CREATE TABLE IF NOT EXISTS sections (
  section_id          TEXT PRIMARY KEY,  -- = heading block_id, or root id
  doc_id              TEXT NOT NULL REFERENCES documents(doc_id),
  parent_section_id   TEXT REFERENCES sections(section_id),
  heading             TEXT,
  heading_level       INTEGER,
  heading_path        TEXT,              -- JSON array of ancestor headings
  first_block_id      TEXT,
  last_block_id       TEXT,
  token_count         INTEGER,
  char_start          INTEGER,
  char_end            INTEGER,
  is_boilerplate      INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sections_doc ON sections(doc_id);
CREATE INDEX IF NOT EXISTS idx_sections_parent ON sections(parent_section_id);
CREATE INDEX IF NOT EXISTS idx_sections_heading_level ON sections(heading_level);

CREATE TABLE IF NOT EXISTS blocks (
  block_id            TEXT PRIMARY KEY,
  doc_id              TEXT NOT NULL REFERENCES documents(doc_id),
  section_id          TEXT REFERENCES sections(section_id),
  parent_block_id     TEXT,
  prev_block_id       TEXT,
  next_block_id       TEXT,
  list_id             TEXT,
  block_type          TEXT NOT NULL,     -- heading|paragraph|list_item|table|
                                         -- code|image|blockquote|math|footnote_def
  heading_path        TEXT,
  order_index         INTEGER NOT NULL,
  char_start          INTEGER,
  char_end            INTEGER,
  char_count          INTEGER,
  token_count         INTEGER,
  text                TEXT NOT NULL,     -- cleaned text
  raw_text            TEXT,              -- original markdown content
  content_hash        TEXT NOT NULL,
  is_orphan           INTEGER DEFAULT 0,
  is_boilerplate      INTEGER DEFAULT 0,
  is_math             INTEGER DEFAULT 0,
  is_footnote         INTEGER DEFAULT 0,
  language            TEXT,              -- per-block language if detected
  extra_json          TEXT               -- code language, math notation, etc.
);
CREATE INDEX IF NOT EXISTS idx_blocks_doc ON blocks(doc_id);
CREATE INDEX IF NOT EXISTS idx_blocks_section ON blocks(section_id);
CREATE INDEX IF NOT EXISTS idx_blocks_type ON blocks(block_type);
CREATE INDEX IF NOT EXISTS idx_blocks_hash ON blocks(content_hash);
CREATE INDEX IF NOT EXISTS idx_blocks_order ON blocks(doc_id, order_index);

CREATE TABLE IF NOT EXISTS atoms (
  atom_id             TEXT PRIMARY KEY,
  block_id            TEXT NOT NULL REFERENCES blocks(block_id),
  doc_id              TEXT NOT NULL REFERENCES documents(doc_id),
  section_id          TEXT REFERENCES sections(section_id),
  atom_type           TEXT NOT NULL,     -- sentence|list_item|caption|table|code|math
  order_index         INTEGER NOT NULL,
  char_start          INTEGER,
  char_end            INTEGER,
  token_count         INTEGER,
  text                TEXT NOT NULL,
  content_hash        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_atoms_doc ON atoms(doc_id);
CREATE INDEX IF NOT EXISTS idx_atoms_block ON atoms(block_id);
CREATE INDEX IF NOT EXISTS idx_atoms_section ON atoms(section_id);
CREATE INDEX IF NOT EXISTS idx_atoms_hash ON atoms(content_hash);
CREATE INDEX IF NOT EXISTS idx_atoms_type ON atoms(atom_type);

CREATE TABLE IF NOT EXISTS images (
  image_id           TEXT PRIMARY KEY,   -- hash(url)
  block_id           TEXT REFERENCES blocks(block_id),
  doc_id             TEXT NOT NULL REFERENCES documents(doc_id),
  section_id         TEXT REFERENCES sections(section_id),
  url                TEXT NOT NULL,
  alt                TEXT,
  title              TEXT,
  width              INTEGER,
  height             INTEGER,
  is_boilerplate     INTEGER DEFAULT 0,
  created_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_images_doc ON images(doc_id);
CREATE INDEX IF NOT EXISTS idx_images_section ON images(section_id);
CREATE INDEX IF NOT EXISTS idx_images_block ON images(block_id);

CREATE TABLE IF NOT EXISTS links (
  link_id       TEXT PRIMARY KEY,
  block_id      TEXT NOT NULL REFERENCES blocks(block_id),
  doc_id        TEXT NOT NULL REFERENCES documents(doc_id),
  url           TEXT NOT NULL,
  text          TEXT,
  is_internal   INTEGER DEFAULT 0,
  is_citation   INTEGER DEFAULT 0,
  order_index   INTEGER
);
CREATE INDEX IF NOT EXISTS idx_links_doc ON links(doc_id);
CREATE INDEX IF NOT EXISTS idx_links_url ON links(url);

CREATE TABLE IF NOT EXISTS footnotes (
  footnote_id           TEXT PRIMARY KEY,
  doc_id                TEXT NOT NULL REFERENCES documents(doc_id),
  marker                TEXT NOT NULL,   -- "1", "2", "a"
  definition_block_id   TEXT REFERENCES blocks(block_id),
  definition_text       TEXT
);
CREATE INDEX IF NOT EXISTS idx_footnotes_doc ON footnotes(doc_id);

CREATE TABLE IF NOT EXISTS footnote_refs (
  ref_id         TEXT PRIMARY KEY,
  block_id       TEXT NOT NULL REFERENCES blocks(block_id),
  footnote_id    TEXT REFERENCES footnotes(footnote_id),
  order_index    INTEGER
);
CREATE INDEX IF NOT EXISTS idx_footnote_refs_block ON footnote_refs(block_id);

-- =====================================================================
-- SECTION 4 — Enrichment
-- =====================================================================

CREATE TABLE IF NOT EXISTS clusters (
  cluster_id      TEXT PRIMARY KEY,
  norm_hash       TEXT UNIQUE,
  norm_text       TEXT,
  representative  TEXT,                  -- atom_id of longest member
  atom_count      INTEGER,
  doc_count       INTEGER
);
CREATE INDEX IF NOT EXISTS idx_clusters_atom_count ON clusters(atom_count DESC);
CREATE INDEX IF NOT EXISTS idx_clusters_doc_count ON clusters(doc_count DESC);

CREATE TABLE IF NOT EXISTS cluster_members (
  cluster_id  TEXT NOT NULL REFERENCES clusters(cluster_id),
  atom_id     TEXT NOT NULL REFERENCES atoms(atom_id),
  doc_id      TEXT NOT NULL REFERENCES documents(doc_id),
  PRIMARY KEY (cluster_id, atom_id)
);
CREATE INDEX IF NOT EXISTS idx_cluster_members_atom ON cluster_members(atom_id);

CREATE TABLE IF NOT EXISTS boilerplate_patterns (
  pattern_id     TEXT PRIMARY KEY,
  domain         TEXT NOT NULL,
  pattern_type   TEXT NOT NULL,          -- exact_hash|regex|position
  pattern        TEXT NOT NULL,
  hit_count      INTEGER DEFAULT 0,
  doc_count      INTEGER DEFAULT 0,
  confidence     DOUBLE PRECISION,
  created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_boilerplate_domain ON boilerplate_patterns(domain);

-- Optional: embeddings table — leave unpopulated in v1
CREATE TABLE IF NOT EXISTS embeddings (
  target_type  TEXT NOT NULL,            -- atom | section | doc | heading
  target_id    TEXT NOT NULL,
  model        TEXT NOT NULL,
  dim          INTEGER NOT NULL,
  vector       BYTEA NOT NULL,
  created_at   TEXT NOT NULL,
  PRIMARY KEY (target_type, target_id, model)
);
CREATE INDEX IF NOT EXISTS idx_embeddings_target ON embeddings(target_type, target_id);

-- =====================================================================
-- SECTION 5 — Synthesis (topic clustering, outline, selection, article)
-- =====================================================================

CREATE TABLE IF NOT EXISTS topics (
  topic_id      TEXT PRIMARY KEY,
  config_id     TEXT REFERENCES corpus_config(config_id),
  name          TEXT,                    -- LLM-derived or user-provided
  description   TEXT,
  created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS doc_topics (
  doc_id     TEXT NOT NULL REFERENCES documents(doc_id),
  topic_id   TEXT NOT NULL REFERENCES topics(topic_id),
  confidence DOUBLE PRECISION,
  PRIMARY KEY (doc_id, topic_id)
);
CREATE INDEX IF NOT EXISTS idx_doc_topics_topic ON doc_topics(topic_id);

CREATE TABLE IF NOT EXISTS atom_buckets (
  atom_id     TEXT PRIMARY KEY REFERENCES atoms(atom_id),
  topic_id    TEXT REFERENCES topics(topic_id),   -- null for single-topic corpus
  bucket      TEXT NOT NULL,             -- narrative bucket name
  method      TEXT,                      -- heading|text|prototype|default
  confidence  DOUBLE PRECISION
);
CREATE INDEX IF NOT EXISTS idx_buckets_bucket ON atom_buckets(bucket);
CREATE INDEX IF NOT EXISTS idx_buckets_topic ON atom_buckets(topic_id);

CREATE TABLE IF NOT EXISTS selected_atoms (
  atom_id         TEXT PRIMARY KEY REFERENCES atoms(atom_id),
  topic_id        TEXT REFERENCES topics(topic_id),
  bucket          TEXT NOT NULL,
  rank            INTEGER,
  score           DOUBLE PRECISION,
  doc_id          TEXT,
  reason          TEXT,                  -- formula|singleton|llm_rerank|manual
  rerank_reason   TEXT,                  -- LLM explanation if rerank was used
  selection_run_id TEXT                   -- ties back to pipeline_runs
);
CREATE INDEX IF NOT EXISTS idx_selected_bucket ON selected_atoms(bucket);
CREATE INDEX IF NOT EXISTS idx_selected_topic ON selected_atoms(topic_id);

CREATE TABLE IF NOT EXISTS section_images (
  topic_id    TEXT REFERENCES topics(topic_id),
  section_id  TEXT REFERENCES sections(section_id),
  image_id    TEXT REFERENCES images(image_id),
  bucket      TEXT,
  rank        INTEGER,
  PRIMARY KEY (topic_id, section_id, image_id)
);

CREATE TABLE IF NOT EXISTS articles (
  article_id         TEXT PRIMARY KEY,
  topic_id           TEXT REFERENCES topics(topic_id),
  synthesis_run_id   TEXT REFERENCES pipeline_runs(run_id),
  title              TEXT,
  markdown           TEXT NOT NULL,
  model              TEXT,
  created_at         TEXT NOT NULL,
  atom_ids_json      TEXT,               -- atom_ids used, ordered
  notes              TEXT
);
CREATE INDEX IF NOT EXISTS idx_articles_topic ON articles(topic_id);
CREATE INDEX IF NOT EXISTS idx_articles_run ON articles(synthesis_run_id);

CREATE TABLE IF NOT EXISTS synthesis_traces (
  trace_id          TEXT PRIMARY KEY,
  article_id        TEXT REFERENCES articles(article_id),
  run_id            TEXT,
  topic_id          TEXT,
  model             TEXT NOT NULL,
  system_prompt     TEXT NOT NULL,
  user_prompt       TEXT NOT NULL,
  raw_content       TEXT,
  raw_reasoning     TEXT,
  finish_reason     TEXT,
  prompt_tokens     INTEGER,
  completion_tokens INTEGER,
  created_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_traces_article ON synthesis_traces(article_id);
CREATE INDEX IF NOT EXISTS idx_traces_created ON synthesis_traces(created_at DESC);
-- =====================================================================
-- END
-- =====================================================================