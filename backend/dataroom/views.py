from django.conf import settings
from django.views.generic import TemplateView

from backend.dataroom.models.os_image import OSImage
from backend.users.permissions import dataroom_access_required


@dataroom_access_required()
class SPAView(TemplateView):
    template_name = "dataroom/spa.jinja"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if 'image_id' in self.kwargs:
            try:
                image = OSImage.objects.get(id=self.kwargs['image_id'])
            except OSImage.DoesNotExist:
                image = None
            context['image'] = image

        context.update(
            {
                'deepscatter_url': settings.DEEPSCATTER_URL,
            }
        )

        return context
