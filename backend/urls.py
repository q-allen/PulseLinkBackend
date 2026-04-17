from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from django.views.generic import RedirectView

from appointments.views import MyDoctorsView
from doctors.views import ActivateDoctorView
from users.urls import family_urlpatterns
from backend.admin_site import PulseLinkAdminSite

admin.site.__class__ = PulseLinkAdminSite

def health_check(request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("api/health/", health_check, name="health-check"),
    path("favicon.ico", RedirectView.as_view(url="/static/icon.svg", permanent=True)),
    path("admin",  RedirectView.as_view(url="/admin/", permanent=False)),
    path("admin/",                              admin.site.urls),
    path("api/auth/set-doctor-password",        ActivateDoctorView.as_view(), name="set-doctor-password"),
    path("api/auth/",                           include("users.urls")),
    path("api/doctors/",                        include("doctors.urls")),
    path("api/appointments/",                   include("appointments.urls")),
    path("api/records/",                        include("records.urls")),
    path("api/chat/",                           include("chat.urls")),
    path("api/pharmacy/",                       include("pharmacy.urls")),
    path("api/notifications/",                  include("notifications.urls")),
    path("api/payouts/",                        include("payouts.urls")),
    path("api/patients/my-doctors/",            MyDoctorsView.as_view(), name="my-doctors"),
    # Family members: GET/POST /api/patients/family-members/
    #                 PATCH/DELETE /api/patients/family-members/{id}/
    *[path(f"api/patients/{p.pattern}", p.callback, name=p.name) for p in family_urlpatterns],
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.BASE_DIR / "static")

