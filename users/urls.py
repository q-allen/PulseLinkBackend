from django.urls import path

from .views import (
    AvatarUploadView,
    CompleteProfileView,
    FamilyMemberDetailView,
    FamilyMemberView,
    ForgotPasswordView,
    LoginView,
    LogoutView,
    MeView,
    RefreshView,
    RegisterView,
    ResetPasswordView,
    SendOtpView,
    WsTokenView,
)

urlpatterns = [
    path("send-otp",        SendOtpView.as_view(),        name="send-otp"),
    path("register",        RegisterView.as_view(),        name="register"),
    path("login",           LoginView.as_view(),           name="login"),
    path("logout",          LogoutView.as_view(),          name="logout"),
    path("refresh",         RefreshView.as_view(),         name="token-refresh"),
    path("me",              MeView.as_view(),              name="me"),
    path("me/complete",     CompleteProfileView.as_view(), name="me-complete"),
    path("me/avatar",       AvatarUploadView.as_view(),   name="me-avatar"),
    path("forgot-password", ForgotPasswordView.as_view(),  name="forgot-password"),
    path("reset-password",  ResetPasswordView.as_view(),   name="reset-password"),
    path("ws-token",        WsTokenView.as_view(),         name="ws-token"),
]

# Family member routes are mounted under /api/patients/ in backend/urls.py
family_urlpatterns = [
    path("family-members/",      FamilyMemberView.as_view(),        name="family-members"),
    path("family-members/<int:pk>/", FamilyMemberDetailView.as_view(), name="family-member-detail"),
]
