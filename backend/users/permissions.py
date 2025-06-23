from django.contrib.auth.decorators import login_required, permission_required
from django.utils.decorators import method_decorator


def dataroom_access_required():
    return method_decorator(
        [
            login_required(),
            permission_required("users.dataroom_access", raise_exception=True),
        ],
        name='dispatch',
    )
