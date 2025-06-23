import numpy as np


def normalize_vector(vector):
    if vector is None or not isinstance(vector, list) or len(vector) == 0:
        return vector

    vector_np = np.array(vector)
    l2_norm = np.linalg.norm(vector_np, 2)

    if l2_norm == 0:
        return vector
    else:
        normalized_vector = (vector_np / l2_norm).tolist()
        return normalized_vector


def normalize_similarity(score):
    """Convert OpenSearch inner product score to cosine similarity"""
    if score >= 1:
        return score - 1
    elif score != 0:
        return 1 - (1 / score)
    return 0
