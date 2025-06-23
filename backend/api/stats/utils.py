from backend.dataroom.models import Stats


def get_queue_stats():
    return {
        'total_images': Stats.objects.get_total_images(),
        'images_missing_thumbnail': Stats.objects.get_images_missing_thumbnail(),
        'images_missing_coca_embedding': Stats.objects.get_images_missing_coca_embedding(),
        'images_missing_duplicate_state': Stats.objects.get_images_missing_duplicate_state(),
        'images_marked_as_duplicates': Stats.objects.get_images_marked_as_duplicates(),
        'images_marked_for_deletion': Stats.objects.get_images_marked_for_deletion(),
        'images_with_disabled_latents': Stats.objects.get_images_with_disabled_latents(),
    }
