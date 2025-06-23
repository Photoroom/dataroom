from allauth.account.views import LoginView
from allauth.socialaccount.models import SocialApp
from allauth.socialaccount.templatetags.socialaccount import provider_login_url


class UserLoginView(LoginView):
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        tag_context = {
            'request': self.request,
        }
        try:
            google_login_url = provider_login_url(tag_context, 'google')
        except SocialApp.DoesNotExist:
            google_login_url = None
        ctx.update(
            {
                'google_login_url': google_login_url,
            }
        )
        return ctx
