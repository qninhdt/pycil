"""ASGI entry point; resource I/O starts only during lifespan."""

from pycil.app.factory import create_app

app = create_app()
