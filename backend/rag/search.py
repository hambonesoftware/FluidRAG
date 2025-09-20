from typing import List, Dict, Any, Tuple
from .config import DEFAULTS
from .boosts import query_features, chunk_boost
from .embeddings import cosine
def hybrid_search(index, query: str, embedder=None, overrides:dict=None) -> List[Dict[str,Any]]:
    cfg = {**DEFAULTS, **(overrides or {})}
    # 1) BM25
    bm25_scores = index.bm25.get_scores(query)
    # 2) Embedding
    if embedder and index.vectors is None:
        index.set_vectors(embedder.embed([c.get('text','') for c in index.chunks]))
    if embedder and index.vectors is not None:
        qv = embedder.embed([query])[0]
        emb_scores = [cosine(qv, v) for v in index.vectors]
        # normalize 0..1
        m = max(emb_scores) if emb_scores else 1.0
        emb_scores = [ (x/m if m>0 else 0.0) for x in emb_scores ]
    else:
        emb_scores = [0.0]*len(index)
    # 3) Combine
    alpha = cfg['alpha_embed']
    base = [ (1-alpha)*bm25_scores[i] + alpha*emb_scores[i] for i in range(len(index)) ]
    # 4) Boosts
    feats = query_features(query)
    boosted = []
    for i, c in enumerate(index.chunks):
        mult = chunk_boost(c, feats, cfg)
        boosted.append((i, base[i]*mult))
    # 5) Initial top-k
    boosted.sort(key=lambda x: x[1], reverse=True)
    top = boosted[:cfg['top_k_initial']]
    # 6) Neighborhood expansion (prev/next in same section)
    k_nb = cfg['k_neighborhood']
    cand_ids = {i for i,_ in top}
    sec_map = {}
    for idx, ch in enumerate(index.chunks):
        key = (ch.get('section_id'), ch.get('page_start'), ch.get('page_end'))
        sec_map.setdefault(key, []).append(idx)
    for key, lst in sec_map.items():
        lst_sorted = sorted(lst)
        around = set()
        for ci in list(cand_ids):
            if ci in lst_sorted:
                pos = lst_sorted.index(ci)
                for d in range(1, k_nb+1):
                    if pos-d >= 0: around.add(lst_sorted[pos-d])
                    if pos+d < len(lst_sorted): around.add(lst_sorted[pos+d])
        cand_ids |= around
    # 7) Xref expansion (1 hop)
    if cfg['max_xref_hops'] > 0:
        id_by_section = {}
        for i,c in enumerate(index.chunks):
            sid = c.get('section_id'); id_by_section.setdefault(sid, []).append(i)
        for ci in list(cand_ids):
            deps = index.chunks[ci].get('deps') or []
            for d in deps:
                for j in id_by_section.get(d, []):
                    cand_ids.add(j)
    # 8) Final rerank within candidate set (apply boosts again for stability)
    final = []
    for i in cand_ids:
        mult = chunk_boost(index.chunks[i], feats, cfg)
        final.append((i, base[i]*mult))
    final.sort(key=lambda x: x[1], reverse=True)
    out = []
    for i,score in final[:cfg['top_k_final']]:
        ch = dict(index.chunks[i])
        ch['score'] = float(score)
        out.append(ch)
    return out
