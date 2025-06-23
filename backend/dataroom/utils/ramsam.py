from io import BytesIO

import numpy as np
from PIL import Image


def get_ramsam_segmentation(image_width, image_height, captions_file, segments_file, max_size=1000):
    # Load captions
    captions = np.load(BytesIO(captions_file.read()))  # Expecting a .npy file

    # Load masks
    masks = np.load(BytesIO(segments_file.read()))  # Expecting a .npy file
    # If masks is an NPZ file, we need to load the actual array data
    if isinstance(masks, np.lib.npyio.NpzFile):
        # Create a 3D array from the masks values
        masks_list = []
        for key in masks.files:
            masks_list.append(masks[key])
        masks = np.stack(masks_list)

    masks = masks.astype(np.float32)
    if np.max(masks) == 1.0:
        masks *= 255

    if len(masks.shape) != 3:
        raise ValueError("Masks array must be 3D (num_masks, height, width)")

    # Merge duplicate captions and their corresponding masks
    unique_captions = []
    unique_masks = []
    seen_captions = {}

    for i, caption in enumerate(captions):
        if caption in seen_captions:
            # Merge mask with existing mask for this caption
            idx = seen_captions[caption]
            unique_masks[idx] = np.maximum(unique_masks[idx], masks[i])
        else:
            seen_captions[caption] = len(unique_captions)
            unique_captions.append(caption)
            unique_masks.append(masks[i])

    # Update captions and masks with deduplicated versions
    captions = np.array(unique_captions)
    masks = np.array(unique_masks)

    # Resize image and masks if needed
    mask_height, mask_width = masks.shape[1:]
    if (image_width, image_height) != (mask_width, mask_height):
        masks_resized = np.zeros((masks.shape[0], image_height, image_width), dtype=np.float32)
        for i in range(masks.shape[0]):
            mask = Image.fromarray(masks[i].astype(np.float32))  # Keep as float32
            mask_resized = mask.resize((image_width, image_height), Image.Resampling.BICUBIC)
            masks_resized[i] = np.array(mask_resized)
        masks = masks_resized

    # Resize masks while maintaining aspect ratio
    if image_width > max_size or image_height > max_size:
        # Calculate scale factor to maintain aspect ratio
        scale = min(max_size / image_width, max_size / image_height)
        new_width = int(image_width * scale)
        new_height = int(image_height * scale)

        # Resize masks
        masks_resized = np.zeros((masks.shape[0], new_height, new_width), dtype=np.float32)
        for i in range(masks.shape[0]):
            mask = Image.fromarray(masks[i].astype(np.float32))  # Keep as float32
            mask_resized = mask.resize((new_width, new_height), Image.Resampling.BICUBIC)
            masks_resized[i] = np.array(mask_resized)
        masks = masks_resized

    # Convert to uint8 only at the very end
    masks = np.clip(masks, 0, 255).astype(np.uint8)

    return captions.tolist(), [mask.tolist() for mask in masks]
