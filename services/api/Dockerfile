FROM python:3.13-slim

WORKDIR /app
COPY pyproject.toml ./
RUN mkdir -p app/pipeline && touch app/__init__.py app/pipeline/__init__.py \
    && pip install --no-cache-dir -e ".[dev]"
COPY . .
