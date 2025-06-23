import numpy as np
import umap


def images_to_2d_coordinates(images):
    valid_images = [img for img in images if img.coca_embedding_vector is not None]
    vectors = np.array([img.coca_embedding_vector for img in valid_images])

    # Fit UMAP on the dataset
    reducer = umap.UMAP(n_components=2)
    reducer.fit(vectors)

    transformed_vectors = reducer.transform(vectors)

    result = [[img, x, y] for img, (x, y) in zip(valid_images, transformed_vectors, strict=True)]

    return result
