try:
    from .celery import app as celery_app  # noqa: F401
except ImportError:
    pass
