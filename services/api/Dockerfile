FROM python:3.13-slim

WORKDIR /app
COPY pyproject.toml ./
RUN mkdir app && touch app/__init__.py && pip install --no-cache-dir -e ".[dev]"
COPY . .
