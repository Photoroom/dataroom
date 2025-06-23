import numpy as np
import random


def get_random_vector(size=768):
    vector = np.array([random.randint(-99, 99) / 100 for _ in range(size)])
    norm = np.linalg.norm(vector)
    if norm == 0:
        return get_random_vector(size=size)
    normalized_vector = vector / norm
    return normalized_vector
