from django.urls import path

from posts import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("posts/new/", views.edit, name="post_new"),
    path("posts/<int:pk>/", views.detail, name="post_detail"),
    path("posts/<int:pk>/edit/", views.edit, name="post_edit"),
    path("posts/<int:pk>/delete/", views.delete, name="post_delete"),
    path("posts/<int:pk>/duplicate/", views.duplicate, name="post_duplicate"),
    path("preview/", views.preview, name="preview"),
    path("linkedin/connect/", views.linkedin_connect, name="linkedin_connect"),
    path("linkedin/callback/", views.linkedin_callback, name="linkedin_callback"),
    path("linkedin/disconnect/", views.linkedin_disconnect, name="linkedin_disconnect"),
    path("media/<path:path>", views.media_file, name="media"),
    path("privacy/", views.privacy, name="privacy"),
    path("healthz", views.healthz, name="healthz"),
]
