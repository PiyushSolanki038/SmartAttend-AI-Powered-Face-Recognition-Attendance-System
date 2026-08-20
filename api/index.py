"""Vercel serverless entrypoint. Vercel's Python runtime auto-detects an ASGI app named
`app` in a file under /api and wraps it as a serverless function — this just re-exports
the real FastAPI app defined in webportal/main.py so nothing about the app itself needs
to know it's running on Vercel."""
from webportal.main import app  # noqa: F401
