def update_datadog():
    from backend.dataroom.models import AttributesField
    from backend.dataroom.models.os_image import OSImage

    # count of images per source
    image_sources = OSImage.objects.counts_by_field('source')
    print('\nAll images:')  # noqa
    for source, count in image_sources.items():
        print(f"{source}: {count}")  # noqa

    # count of images with a caption, per source
    caption_field = AttributesField.objects.filter(name='caption').first()
    if caption_field:
        images_with_caption = OSImage.objects.filter_counts_by_field(
            filter_type='bool',
            filter_kwargs=dict(
                must=[{"exists": {"field": caption_field.os_field_name}}],
            ),
            field_name='source',
        )
        print('\nImages with caption:')  # noqa
        for source, count in images_with_caption.items():
            print(f"{source}: {count}")  # noqa

    # count of images with a caption_cogvlm, per source
    caption_cogvlm_field = AttributesField.objects.filter(name='caption_cogvlm').first()
    if caption_cogvlm_field:
        images_with_caption_cogvlm = OSImage.objects.filter_counts_by_field(
            filter_type='bool',
            filter_kwargs=dict(
                must=[{"exists": {"field": caption_cogvlm_field.os_field_name}}],
            ),
            field_name='source',
        )
        print('\nImages with caption_cogvlm:')  # noqa
        for source, count in images_with_caption_cogvlm.items():
            print(f"{source}: {count}")  # noqa


def update_datadog_dashboard(_):
    update_datadog()
