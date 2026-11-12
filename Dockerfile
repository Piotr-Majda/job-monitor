# syntax=docker/dockerfile:1
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN apt-get update && apt-get install -y --no-install-recommends libatomic1 ca-certificates && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
# Optional CA mount supports TLS-inspecting development environments without
# putting environment-specific certificates into the image.
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then \
      PIP_CERT=/run/secrets/proxy_ca pip install --no-cache-dir -r requirements.txt; \
    else pip install --no-cache-dir -r requirements.txt; fi
COPY app ./app
RUN useradd --create-home --uid 10001 scout && chmod -R a+rX /app && mkdir -p /app/data && chown scout:scout /app/data
USER scout
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"
CMD ["uvicorn", "app.web:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
