FROM python:3.13-slim

WORKDIR /deal-kit
COPY pyproject.toml ./
RUN mkdir dealkit && touch dealkit/__init__.py && pip install --no-cache-dir -e ".[dev]"
COPY . .
