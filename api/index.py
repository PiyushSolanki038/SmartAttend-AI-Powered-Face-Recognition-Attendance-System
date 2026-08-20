"""Vercel serverless entrypoint. Vercel's Python runtime auto-detects an ASGI app named
`app` in a file under /api and wraps it as a serverless function — this just re-exports
the real FastAPI app defined in webportal/main.py so nothing about the app itself needs
to know it's running on Vercel.

The env vars below MUST be set before webportal.main (and its transitive services.dashboard
-> matplotlib import) runs: on Vercel's read-only filesystem, matplotlib crashes the entire
function at import time trying to build its font cache under the default (unwritable) cache
directory, and HOME may not point anywhere writable either — only /tmp is guaranteed
writable in this runtime."""
import os

os.environ.setdefault("HOME", "/tmp")
os.environ.setdefault("MPLCONFIGDIR", "/tmp/mplconfig")

from webportal.main import app  # noqa: F401,E402
