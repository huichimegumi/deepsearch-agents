FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

WORKDIR /workspace

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app ./app
COPY docs ./docs

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.api.server:app", "--host", "0.0.0.0", "--port", "8000"]

