FROM python:3.13-slim

WORKDIR /engine
COPY pyproject.toml ./
RUN mkdir engine && touch engine/__init__.py && pip install --no-cache-dir -e ".[dev]"
COPY . .
