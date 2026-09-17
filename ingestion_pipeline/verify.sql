-- 1. doc-level summary
SELECT d.doc_id,
       substr(d.title, 1, 60) AS title,
       (SELECT count(*) FROM sections s WHERE s.doc_id = d.doc_id) AS sections,
       (SELECT count(*) FROM blocks  b WHERE b.doc_id = d.doc_id) AS blocks,
       (SELECT count(*) FROM atoms   a WHERE a.doc_id = d.doc_id) AS atoms
FROM documents d;

-- 2. atom type distribution per doc
SELECT doc_id, atom_type, count(*) AS n
FROM atoms GROUP BY doc_id, atom_type ORDER BY doc_id, n DESC;

-- 3. sections in a doc, ordered, with first/last block
SELECT section_id, heading, heading_level, token_count, first_block_id, last_block_id
FROM sections WHERE doc_id = :doc_id ORDER BY char_start;

-- 4. atoms under a heading
SELECT a.atom_type, substr(a.text, 1, 100) AS preview
FROM atoms a JOIN sections s ON a.section_id = s.section_id
WHERE s.doc_id = :doc_id AND s.heading = :heading
ORDER BY a.block_id, a.order_index;

-- 5. integrity: non-heading, non-boilerplate blocks must produce ≥ 1 atom
SELECT b.block_id, b.block_type, substr(b.text, 1, 60) AS preview
FROM blocks b
LEFT JOIN atoms a ON a.block_id = b.block_id
WHERE b.is_boilerplate = 0
  AND b.block_type <> 'heading'
  AND a.atom_id IS NULL
  AND length(trim(b.text)) > 0;

-- 6. duplicate atom hashes (preview of dedup opportunities)
SELECT content_hash, count(*) AS c
FROM atoms GROUP BY content_hash HAVING c > 1 ORDER BY c DESC LIMIT 20;