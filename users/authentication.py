from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError


class CookieJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        access_token = request.COOKIES.get("access_token")
        if not access_token:
            return None
        try:
            validated_token = self.get_validated_token(access_token)
        except TokenError as e:
            raise InvalidToken(e.args[0])
        return self.get_user(validated_token), validated_token


class OptionalCookieJWTAuthentication(CookieJWTAuthentication):
    """
    Same as CookieJWTAuthentication but treats invalid/expired tokens as anonymous.
    Useful for endpoints like /api/auth/me that should not 401 for guests.
    """

    def authenticate(self, request):
        try:
            return super().authenticate(request)
        except InvalidToken:
            return None
