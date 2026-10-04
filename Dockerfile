FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev
RUN useradd --create-home app && mkdir /data && chown app /data
USER app
ENV PYTHONUNBUFFERED=1 PAGEINDEX_STORAGE_PATH=/data PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/health')" || exit 1
CMD ["uvicorn", "document_intelligence.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
