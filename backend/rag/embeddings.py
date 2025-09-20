from typing import List, Callable
import math
def l2_norm(v):
    return math.sqrt(sum(x*x for x in v)) or 1.0
def cosine(a, b):
    na, nb = l2_norm(a), l2_norm(b)
    return sum(x*y for x,y in zip(a,b))/(na*nb)
class Embedder:
    def __init__(self, fn: Callable[[List[str]], List[List[float]]]):
        self.fn = fn
    def embed(self, texts: List[str]) -> List[List[float]]:
        return self.fn(texts)
