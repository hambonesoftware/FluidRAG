from typing import List, Dict, Any
from .bm25 import BM25
class Index:
    def __init__(self, chunks: List[Dict[str,Any]]):
        self.chunks = chunks
        self.bm25 = BM25([c.get('text','') for c in chunks])
        self.vectors = None
    def set_vectors(self, vecs):
        self.vectors = vecs
    def __len__(self):
        return len(self.chunks)
