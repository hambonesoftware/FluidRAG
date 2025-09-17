import logging
from typing import List, Dict, Any
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans

log = logging.getLogger("FluidRAG.hep")

def _entropy(vec: np.ndarray) -> float:
    p = vec / (np.sum(vec) + 1e-9)
    p = p[p > 0]
    return float(-np.sum(p * np.log2(p)))

def hep_cluster_chunks(chunks: List[Dict, ]):
    """High-Entropy Pass (HEP): cluster by tf-idf; annotate cluster_id and seed score."""
    texts = [c["text"] for c in chunks]
    if len(texts) < 3:
        for i, c in enumerate(chunks):
            c["meta"]["cluster_id"] = 0
            c["meta"]["hep_entropy"] = 0.0
        return chunks

    vec = TfidfVectorizer(max_features=5000)
    X = vec.fit_transform(texts)
    entropies = []
    for i in range(X.shape[0]):
        entropies.append(_entropy(X[i].toarray()[0]))
    k = max(2, min(8, int(len(chunks) ** 0.5)))
    km = KMeans(n_clusters=k, n_init="auto", random_state=42)
    labels = km.fit_predict(X)

    for i, c in enumerate(chunks):
        c["meta"]["cluster_id"] = int(labels[i])
        c["meta"]["hep_entropy"] = float(entropies[i])
    log.debug(f"[hep] k={k} clustered {len(chunks)} chunks")
    return chunks
