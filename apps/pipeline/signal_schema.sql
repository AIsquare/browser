-- =====================================================================
-- Signal store — permanent record of user URL selections
--
-- This database never expires. Every row here is a training example for
-- a future indexing algorithm. Do not add TTL, do not cascade deletes
-- from the working DB into this one.
-- =====================================================================

CREATE TABLE IF NOT EXISTS selection_events (
  event_id       TEXT PRIMARY KEY,
  url_id         TEXT NOT NULL,          -- sha16(canonical_url)
  url            TEXT NOT NULL,          -- raw URL as selected
  canonical_url  TEXT NOT NULL,
  domain         TEXT NOT NULL,
  search_query   TEXT,                   -- what the user was looking for
  topic_id       TEXT,                   -- what they're building
  user_id        TEXT,                   -- for dedup; can be 'anonymous'
  session_id     TEXT,
  selected_at    TEXT NOT NULL,
  surface        TEXT,                   -- 'extension' | 'web' | 'api'
  metadata_json  TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_url      ON selection_events(url_id);
CREATE INDEX IF NOT EXISTS idx_events_query    ON selection_events(search_query);
CREATE INDEX IF NOT EXISTS idx_events_topic    ON selection_events(topic_id);
CREATE INDEX IF NOT EXISTS idx_events_domain   ON selection_events(domain);
CREATE INDEX IF NOT EXISTS idx_events_selected ON selection_events(selected_at DESC);

CREATE MATERIALIZED VIEW IF NOT EXISTS selected_urls AS
SELECT
  url_id,
  canonical_url,
  domain,
  COUNT(*)                AS selection_count,
  COUNT(DISTINCT user_id) AS unique_users,
  MIN(selected_at)        AS first_seen,
  MAX(selected_at)        AS last_seen,
  ARRAY_AGG(DISTINCT topic_id)    FILTER (WHERE topic_id    IS NOT NULL) AS topic_ids,
  ARRAY_AGG(DISTINCT search_query) FILTER (WHERE search_query IS NOT NULL) AS queries
FROM selection_events
GROUP BY url_id, canonical_url, domain;

CREATE UNIQUE INDEX IF NOT EXISTS idx_selected_urls_url ON selected_urls(url_id);
CREATE INDEX IF NOT EXISTS idx_selected_urls_count ON selected_urls(selection_count DESC);
CREATE INDEX IF NOT EXISTS idx_selected_urls_users ON selected_urls(unique_users DESC);