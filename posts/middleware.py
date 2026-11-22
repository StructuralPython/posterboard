"""Trust the user that tinyauth signed in (via Caddy), and nobody else."""

from django.conf import settings
from django.http import HttpResponseForbidden


class TrustedUserMiddleware:
    """
    Caddy sends every request to tinyauth first and copies the signed-in user
    into ``Remote-User``. Gunicorn listens on localhost only, so the header can
    only come from Caddy. A request without it is refused, as a second line of
    defence if the proxy is ever misconfigured.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.meta_key = "HTTP_" + settings.AUTH_HEADER.upper().replace("-", "_")

    def __call__(self, request):
        user = request.META.get(self.meta_key) or settings.DEV_USER
        if not user:
            return HttpResponseForbidden("Sign in through tinyauth.")
        request.posterboard_user = user
        return self.get_response(request)
