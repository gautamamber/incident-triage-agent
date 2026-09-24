"""Local embeddings via the "hashing trick" (a real, named lightweight
technique — popularized by Vowpal Wabbit, still used in some production
systems): each word hashes into one of N buckets, bucket counts become the
vector, then it's L2-normalized so cosine similarity behaves sensibly.

This is NOT a learned/semantic embedding — it has no notion that "timeout"
and "slow" are related concepts, only literal word overlap, projected into a
fixed-size vector. It's a genuine, deliberate simplification: this project's
own stated goal is local-first with minimal external dependencies, and a
real semantic embedding model would mean either a heavy ML dependency (e.g.
sentence-transformers + torch) or a call out to an external embeddings API —
neither fits a project of this size (a handful of runbooks, not a large
corpus). pgvector's storage/query mechanics work identically either way;
only the embedding source would need to change if this ever needs to scale.
"""

import hashlib
import math
import re

DIMENSIONS = 128
_WORD_RE = re.compile(r"[a-z0-9_]+")


def embed(text: str) -> list[float]:
    vector = [0.0] * DIMENSIONS
    for word in _WORD_RE.findall(text.lower()):
        bucket = int(hashlib.sha1(word.encode()).hexdigest(), 16) % DIMENSIONS
        vector[bucket] += 1.0

    norm = math.sqrt(sum(v * v for v in vector))
    if norm == 0:
        return vector
    return [v / norm for v in vector]
