"""Deterministic candidate selection; standard library only, no I/O."""

import math
import re
from datetime import date, datetime


def _date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise ValueError("Invalid date")
    try:
        return date.fromisoformat(value)
    except ValueError:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()


def age_days(meeting_date, last_changed):
    """Calendar-day difference; missing/invalid dates yield 9999."""
    try:
        return (_date(meeting_date) - _date(last_changed)).days
    except (TypeError, ValueError, OverflowError):
        return 9999


def tokens(text):
    """Unique lowercase Unicode word tokens, >=4 characters, truncated to 6."""
    return {word[:6] for word in re.findall(r"\w{4,}", (text or "").casefold())}


def lexical_score(query_tokens, work_tokens):
    q, w = set(query_tokens), set(work_tokens)
    return len(q & w) / math.sqrt(len(q) * len(w)) if q and w else 0.0


def _unit(vector):
    if vector is None:
        return None
    values = tuple(float(x) for x in vector)
    if not all(math.isfinite(x) for x in values):
        raise ValueError("Non-finite vector component")
    norm = math.sqrt(sum(x * x for x in values))
    return tuple(x / norm for x in values) if norm else values


def _dot(a, b):
    if len(a) != len(b):
        raise ValueError("Vector dimensions differ")
    return sum(x * y for x, y in zip(a, b))


def cosine(a, b):
    """Cosine similarity; absent/empty/zero vectors yield zero."""
    if a is None or b is None:
        return 0.0
    a, b = _unit(a), _unit(b)
    return _dot(a, b)


def rank_candidates(scores):
    """Return indices in descending score order, breaking ties by input index."""
    values = list(scores)
    if not all(math.isfinite(x) for x in values):
        raise ValueError("Non-finite score")
    return sorted(range(len(values)), key=lambda i: (-values[i], i))


def query_text(observation):
    """Shared lexical/embedding search text: title, subject, search_keywords."""
    return " ".join([observation.get("title") or "", observation.get("subject") or "",
                     *(observation.get("search_keywords") or [])])


def work_text(candidate):
    """Historical lexical candidate text: title, claim, matter (in that order)."""
    return " ".join(candidate.get(key) or "" for key in ("title", "claim", "matter"))


def lexical_query_text(observation):
    """Historical lexical query adds the claim to the embedding search text."""
    return query_text(observation) + " " + (observation.get("claim") or "")


def select(candidates, observations, meeting_date, A, k,
           embed_candidate=None, embed_query=None):
    """Keep age <= A OR rank < k for any observation, including done tasks.

    Embedding providers are pure callbacks receiving a candidate/observation dict
    and returning a numeric vector or None. Missing vectors have no embedding
    rank. Zero similarities still have ranks: there is no score threshold.
    Results retain input order; stats arrays are aligned with candidates.
    """
    if not isinstance(A, int) or not isinstance(k, int) or A < 0 or k < 0:
        raise ValueError("A and k must be nonnegative integers")
    candidates, observations = list(candidates), list(observations)
    ids = [candidate["id"] for candidate in candidates]
    if len(set(ids)) != len(ids):
        raise ValueError("Candidate ids must be unique within a call")
    ages = [age_days(meeting_date, candidate.get("last_changed")) for candidate in candidates]
    lex_ranks, emb_ranks = [None] * len(ids), [None] * len(ids)
    work_tokens = [tokens(work_text(candidate)) for candidate in candidates]
    vectors = ([_unit(embed_candidate(candidate)) for candidate in candidates]
               if embed_candidate is not None and embed_query is not None else [None] * len(ids))
    available = [i for i, vector in enumerate(vectors) if vector is not None]
    query_vectors = 0
    for observation in observations:
        qt = tokens(lexical_query_text(observation))
        scores = [lexical_score(qt, wt) for wt in work_tokens]
        for rank, i in enumerate(rank_candidates(scores)):
            lex_ranks[i] = rank if lex_ranks[i] is None else min(lex_ranks[i], rank)
        qv = _unit(embed_query(observation)) if embed_query is not None and embed_candidate is not None else None
        if qv is None:
            continue
        query_vectors += 1
        scores = [_dot(qv, vectors[i]) for i in available]
        for rank, position in enumerate(rank_candidates(scores)):
            i = available[position]
            emb_ranks[i] = rank if emb_ranks[i] is None else min(emb_ranks[i], rank)
    reasons = {}
    for i, alias in enumerate(ids):
        why = []
        if ages[i] <= A:
            why.append("age")
        if emb_ranks[i] is not None and emb_ranks[i] < k:
            why.append("emb")
        if lex_ranks[i] is not None and lex_ranks[i] < k:
            why.append("lex")
        if why:
            reasons[alias] = why
    selected = [alias for alias in ids if alias in reasons]
    return {"selected": selected, "reasons": reasons, "stats": {
        "candidates": len(ids), "observations": len(observations), "selected": len(selected),
        "retained_fraction": len(selected) / len(ids) if ids else 0.0,
        "ages": ages, "emb_ranks": emb_ranks, "lex_ranks": lex_ranks,
        "candidate_embeddings": len(available), "query_embeddings": query_vectors,
        "reason_counts": {reason: sum(reason in why for why in reasons.values())
                          for reason in ("age", "emb", "lex")},
    }}
