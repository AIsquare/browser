from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import pandas as pd

from sentence_transformers import SentenceTransformer
from sklearn.cluster import AgglomerativeClustering
from sklearn.feature_extraction.text import CountVectorizer, TfidfTransformer

# Assume Document schema exists
from schema import Document

# Use a modern, long-context embedding model that works without
# remote-code patches and is better suited for long-form document clustering.

# ============================================================
# CONFIG
# ============================================================

EMBEDDING_MODEL_NAME = "BAAI/bge-m3"
CLUSTER_DISTANCE_THRESHOLD = 0.35 
TOP_KEYWORDS = 12

@dataclass
class DiscoveryResult:
    documents: list[Document]
    embedding_matrix: np.ndarray
    cluster_ids: np.ndarray
    topic_summaries: dict[int, dict[str, object]]

# ============================================================
# 1. LONG-CONTEXT EMBEDDINGS
# ============================================================

def build_full_document_embeddings(
    documents: list, 
    model_name: str = EMBEDDING_MODEL_NAME
) -> np.ndarray:
    
    model = SentenceTransformer(model_name)
    
    # --- THE RAM FIX ---
    # Cap the context window at 2048 tokens to fit within 8GB RAM
    model.max_seq_length = 2048
    
    texts = []
    for doc in documents:
        title = doc.source.title or ""
        body = doc.content.markdown or ""
        
        text = f"{title}\n\n{body}"
        texts.append(text)
        
    embeddings = model.encode(
        texts,
        batch_size=1,  # Keep this at 1 to prevent memory spikes!
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=True,
    )
    
    return embeddings

# ============================================================
# 2. CLUSTERING (EMBEDDING-DRIVEN)
# ============================================================

def cluster_documents(
    embedding_matrix: np.ndarray,
    distance_threshold: float = CLUSTER_DISTANCE_THRESHOLD,
) -> np.ndarray:
    
    n = embedding_matrix.shape[0]
    if n == 0:
        return np.empty(0, dtype=int)
    if n == 1:
        return np.zeros(1, dtype=int)

    model = AgglomerativeClustering(
        n_clusters=None,
        distance_threshold=distance_threshold,
        metric="cosine",
        linkage="average",
    )

    return model.fit_predict(embedding_matrix)

# ============================================================
# 3. C-TF-IDF (CLASS-BASED KEYWORD EXTRACTION)
# ============================================================

def extract_cluster_keywords(
    documents: list[Document], 
    cluster_ids: np.ndarray, 
    top_n: int = TOP_KEYWORDS
) -> dict[int, list[str]]:
    """
    Concatenates all documents in a cluster into a single 'super-document'
    and applies TF-IDF across the clusters to find distinguishing keywords.
    """
    # Group raw text by cluster ID
    cluster_texts = {}
    for doc, cluster_id in zip(documents, cluster_ids):
        cid = int(cluster_id)
        # We only need the text body to find representative words
        text = f"{doc.source.title or ''} {doc.content.markdown or ''}"
        cluster_texts[cid] = cluster_texts.get(cid, "") + " " + text
        
    cids = list(cluster_texts.keys())
    super_documents = list(cluster_texts.values())
    
    # 1. Count Words per Cluster
    count_vectorizer = CountVectorizer(stop_words="english", ngram_range=(1, 2))
    count_matrix = count_vectorizer.fit_transform(super_documents)
    
    # 2. Apply TF-IDF across Clusters
    tfidf_transformer = TfidfTransformer()
    c_tfidf_matrix = tfidf_transformer.fit_transform(count_matrix)
    
    terms = np.array(count_vectorizer.get_feature_names_out())
    cluster_keywords = {}
    
    # 3. Extract top keywords per cluster
    for idx, cid in enumerate(cids):
        row = c_tfidf_matrix.getrow(idx)
        if len(row.data) == 0:
            cluster_keywords[cid] = []
            continue
            
        top_indices = np.argsort(row.data)[::-1][:top_n]
        best_feature_indices = row.indices[top_indices]
        cluster_keywords[cid] = terms[best_feature_indices].tolist()
        
    return cluster_keywords

# ============================================================
# MAIN PIPELINE
# ============================================================

def discover_topics(
    documents: list[Document],
    distance_threshold: float = CLUSTER_DISTANCE_THRESHOLD,
) -> DiscoveryResult:

    if not documents:
        return DiscoveryResult(
            documents=[], 
            embedding_matrix=np.empty((0, 0)), 
            cluster_ids=np.empty(0, dtype=int), 
            topic_summaries={}
        )

    print("\nBuilding full-document semantic embeddings...")
    embedding_matrix = build_full_document_embeddings(documents)

    print("\nClustering documents...")
    cluster_ids = cluster_documents(
        embedding_matrix, 
        distance_threshold=distance_threshold
    )

    print("\nExtracting cluster-level keywords (c-TF-IDF)...")
    cluster_keywords = extract_cluster_keywords(
        documents, 
        cluster_ids, 
        top_n=TOP_KEYWORDS
    )

    # Attach summary data
    topic_summaries = {}
    for idx, doc in enumerate(documents):
        cid = int(cluster_ids[idx])
        
        # Attach cluster info directly to the document
        doc.discovery.semantic_embedding = embedding_matrix[idx].astype(float).tolist()
        doc.discovery.topic_cluster = cid
        
        # Initialize cluster summary if it doesn't exist
        if cid not in topic_summaries:
            topic_summaries[cid] = {
            "document_count": 0,
            "top_terms": cluster_keywords.get(cid, []),  # <-- changed from 'keywords' to 'top_terms'
            "keywords": cluster_keywords.get(cid, []),   # keep as alias
            "document_ids": [],
            "sample_titles": []
        }
            
        topic_summaries[cid]["document_count"] += 1
        topic_summaries[cid]["document_ids"].append(doc.document_id)
        if doc.source.title and len(topic_summaries[cid]["sample_titles"]) < 10:
            topic_summaries[cid]["sample_titles"].append(doc.source.title)

    return DiscoveryResult(
        documents=documents,
        embedding_matrix=embedding_matrix,
        cluster_ids=cluster_ids,
        topic_summaries=topic_summaries,
    )