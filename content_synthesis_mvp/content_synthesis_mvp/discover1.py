from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import re
from collections import Counter

from sentence_transformers import SentenceTransformer
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.feature_extraction.text import CountVectorizer, TfidfTransformer

from schema import Document

# ============================================================
# CONFIG
# ============================================================

EMBEDDING_MODEL_NAME = "BAAI/bge-m3"
TOP_KEYWORDS = 12

@dataclass
class DiscoveryResult:
    documents: list[Document]
    embedding_matrix: np.ndarray
    cluster_ids: np.ndarray
    topic_summaries: dict[int, dict[str, object]]

# ============================================================
# 1. EMBEDDINGS (Long-Context, RAM-Optimized)
# ============================================================

def build_full_document_embeddings(
    documents: list, 
    model_name: str = EMBEDDING_MODEL_NAME
) -> np.ndarray:
    
    model = SentenceTransformer(model_name)
    model.max_seq_length = 2048  # Safe cap for 8GB RAM
    
    texts = []
    for doc in documents:
        title = doc.source.title or ""
        body = doc.content.markdown or ""
        text = f"{title}\n\n{body}"
        texts.append(text)
        
    embeddings = model.encode(
        texts,
        batch_size=1, 
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=True,
    )
    return embeddings

# ============================================================
# 2. ADAPTIVE CLUSTERING (KMeans + Silhouette Selection)
# ============================================================

def cluster_documents(embedding_matrix: np.ndarray) -> np.ndarray:
    n = embedding_matrix.shape[0]
    if n <= 1:
        return np.zeros(n, dtype=int)

    # Auto-select best K using Silhouette Score (bounded by data size)
    k_max = max(2, min(int(np.sqrt(n)) + 1, n - 1))
    best_labels, best_score = None, -2.0
    
    for k in range(2, k_max + 1):
        labels = KMeans(n_clusters=k, n_init=10, random_state=42).fit_predict(embedding_matrix)
        if len(set(labels)) < 2:
            continue
        score = silhouette_score(embedding_matrix, labels, metric="cosine")
        if score > best_score:
            best_labels, best_score = labels, score
            
    return best_labels if best_labels is not None else np.zeros(n, dtype=int)

# ============================================================
# 3. SMART KEYWORD EXTRACTION (Corpus-Size Adaptive)
# ============================================================

def extract_cluster_keywords(
    documents: list[Document], 
    cluster_ids: np.ndarray, 
    top_n: int = TOP_KEYWORDS
) -> dict[int, list[str]]:
    
    cluster_texts = {}
    for doc, cluster_id in zip(documents, cluster_ids):
        cid = int(cluster_id)
        text = f"{doc.source.title or ''} {doc.content.markdown or ''}"
        cluster_texts.setdefault(cid, []).append(text)
        
    unique_clusters = len(cluster_texts)

    # Fallback to Frequency-Ratio for small corpora (< 15 clusters) where c-TF-IDF fails
    if unique_clusters < 15:
        global_counts = Counter()
        cluster_counts = {}
        for cid, texts in cluster_texts.items():
            joined = " ".join(texts).lower()
            tokens = re.findall(r"[a-z][a-z\-]{2,}", joined)
            c = Counter(tokens)
            cluster_counts[cid] = c
            global_counts.update(c)

        results = {}
        for cid, c in cluster_counts.items():
            scored = [(t, cnt / (global_counts[t] + 1)) for t, cnt in c.items()]
            scored.sort(key=lambda x: -x[1])
            results[cid] = [t for t, _ in scored[:top_n]]
        return results

    # Standard c-TF-IDF for scaling corpora (>= 15 clusters)
    super_documents = [" ".join(texts) for texts in cluster_texts.values()]
    cids = list(cluster_texts.keys())
    
    count_vectorizer = CountVectorizer(stop_words="english", ngram_range=(1, 2))
    count_matrix = count_vectorizer.fit_transform(super_documents)
    
    tfidf_transformer = TfidfTransformer()
    c_tfidf_matrix = tfidf_transformer.fit_transform(count_matrix)
    
    terms = np.array(count_vectorizer.get_feature_names_out())
    cluster_keywords = {}
    
    for idx, cid in enumerate(cids):
        row = c_tfidf_matrix.getrow(idx)
        if len(row.data) == 0:
            cluster_keywords[cid] = []
            continue
        top_indices = np.argsort(row.data)[::-1][:top_n]
        cluster_keywords[cid] = terms[row.indices[top_indices]].tolist()
        
    return cluster_keywords

# ============================================================
# MAIN PIPELINE & QUALITY REPORTING
# ============================================================

def discover_topics(documents: list[Document]) -> DiscoveryResult:
    if not documents:
        return DiscoveryResult([], np.empty((0, 0)), np.empty(0, dtype=int), {})

    print("\nBuilding full-document semantic embeddings...")
    embedding_matrix = build_full_document_embeddings(documents)

    print("\nClustering documents (Adaptive KMeans)...")
    cluster_ids = cluster_documents(embedding_matrix)

    print("\nExtracting keywords...")
    cluster_keywords = extract_cluster_keywords(documents, cluster_ids, top_n=TOP_KEYWORDS)

    topic_summaries = {}
    for idx, doc in enumerate(documents):
        cid = int(cluster_ids[idx])
        doc.discovery.semantic_embedding = embedding_matrix[idx].astype(float).tolist()
        doc.discovery.topic_cluster = cid
        
        if cid not in topic_summaries:
            topic_summaries[cid] = {
                "document_count": 0,
                "top_terms": cluster_keywords.get(cid, []),
                "keywords": cluster_keywords.get(cid, []),
                "document_ids": [],
                "sample_titles": []
            }
            
        topic_summaries[cid]["document_count"] += 1
        topic_summaries[cid]["document_ids"].append(doc.document_id)
        if doc.source.title and len(topic_summaries[cid]["sample_titles"]) < 10:
            topic_summaries[cid]["sample_titles"].append(doc.source.title)

    # Quality Audit Report
    if len(set(cluster_ids)) >= 2:
        sil = silhouette_score(embedding_matrix, cluster_ids, metric="cosine")
        sizes = sorted((s["document_count"] for s in topic_summaries.values()), reverse=True)
        print(f"\n[Quality Report] K={len(set(cluster_ids))}, Silhouette={sil:.3f}, Sizes={sizes}")
        if sil < 0.05:
            print("[Warning] Silhouette score < 0.05. Clusters may lack semantic separation.")
    else:
        print("\n[Quality Report] Only 1 cluster formed.")

    return DiscoveryResult(
        documents=documents,
        embedding_matrix=embedding_matrix,
        cluster_ids=cluster_ids,
        topic_summaries=topic_summaries,
    )