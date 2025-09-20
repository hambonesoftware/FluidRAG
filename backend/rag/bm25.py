import math
from collections import Counter
from .tokenize import tokenize
class BM25:
    def __init__(self, docs, k1=1.5, b=0.75):
        self.k1, self.b = k1, b
        self.docs = [tokenize(d) for d in docs]
        self.doc_lens = [len(d) for d in self.docs]
        self.avgdl = sum(self.doc_lens)/max(1,len(self.doc_lens))
        self.df = Counter()
        for d in self.docs:
            for t in set(d):
                self.df[t]+=1
        self.N = len(self.docs)
        self.idf = {t: math.log(1 + (self.N - df + 0.5)/(df + 0.5)) for t,df in self.df.items()}
        self.tf = [Counter(d) for d in self.docs]
    def get_scores(self, query:str):
        q = tokenize(query)
        scores = [0.0]*self.N
        for i,doc in enumerate(self.docs):
            dl = self.doc_lens[i]
            denom_norm = self.k1*(1 - self.b + self.b*dl/max(1,self.avgdl))
            tf_i = self.tf[i]
            s = 0.0
            for t in q:
                if t not in tf_i: continue
                idf = self.idf.get(t, 0.0)
                tf = tf_i[t]
                s += idf * (tf*(self.k1+1))/(tf + denom_norm)
            scores[i]=s
        # normalize to 0..1
        mx = max(scores) if scores else 1.0
        return [ (x/mx if mx>0 else 0.0) for x in scores ]
