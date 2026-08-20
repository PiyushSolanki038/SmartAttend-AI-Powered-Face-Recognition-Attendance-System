FROM python:3.13-slim

WORKDIR /app

COPY requirements-web.txt .
RUN pip install --no-cache-dir -r requirements-web.txt

# Full repo copy — webportal/main.py mounts StaticFiles(directory="webportal/static") and
# Jinja2Templates(directory="webportal/templates") as paths relative to the process's cwd,
# which is WORKDIR /app here, so webportal/static and webportal/templates resolve correctly
# once the whole repo lands under /app.
COPY . .

ENV PORT=8000
EXPOSE 8000

# Render/Railway (and most PaaS hosts) inject $PORT at runtime and expect the process to bind
# to it rather than a fixed port — the shell form below reads $PORT if set, falling back to
# 8000 for local `docker run`. If your target platform instead requires a literal exec-form
# CMD (no shell), override this CMD with the platform's assigned port baked in at deploy time.
CMD ["sh", "-c", "uvicorn webportal.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
