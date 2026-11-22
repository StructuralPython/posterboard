from .models import LinkedInConnection


def connection(request):
    return {"linkedin": LinkedInConnection.current()}
