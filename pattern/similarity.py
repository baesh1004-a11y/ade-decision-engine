import numpy as np
import pandas as pd


def cosine_similarity(a: pd.Series | np.ndarray, b: pd.Series | np.ndarray) -> float:
    """Return cosine similarity between two vectors."""
    av = np.asarray(a, dtype=float)
    bv = np.asarray(b, dtype=float)
    denominator = np.linalg.norm(av) * np.linalg.norm(bv)
    if denominator == 0:
        return 0.0
    return float(np.dot(av, bv) / denominator)


def euclidean_distance(a: pd.Series | np.ndarray, b: pd.Series | np.ndarray) -> float:
    """Return Euclidean distance between two vectors."""
    av = np.asarray(a, dtype=float)
    bv = np.asarray(b, dtype=float)
    return float(np.linalg.norm(av - bv))


def similarity_score(a: pd.Series | np.ndarray, b: pd.Series | np.ndarray) -> float:
    """Convert cosine similarity to 0-100 score."""
    score = cosine_similarity(a, b)
    return round(max(0.0, min(1.0, score)) * 100, 2)
