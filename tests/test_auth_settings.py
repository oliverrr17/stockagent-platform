from datetime import timedelta

from django.conf import settings


def test_simple_jwt_lifetimes_are_extended():
    assert settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"] == timedelta(minutes=60)
    assert settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"] == timedelta(days=14)
