# One image for Azure: the workbench and API on a single origin, on a recorded run.

FROM node:22-alpine AS web
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web ./
RUN npm run build

FROM python:3.13-slim AS pack
WORKDIR /deal-kit
COPY deal-kit/pyproject.toml ./
RUN mkdir dealkit && touch dealkit/__init__.py && pip install --no-cache-dir -e .
COPY deal-kit ./
# The recorded run is tied to these exact files, so a different pack must fail the build.
RUN cp pack.manifest.json /tmp/expected.json \
    && python -m dealkit.build \
    && cmp pack.manifest.json /tmp/expected.json

FROM python:3.13-slim
WORKDIR /app
COPY services/api/pyproject.toml ./
RUN mkdir -p app/pipeline && touch app/__init__.py app/pipeline/__init__.py \
    && pip install --no-cache-dir -e .
COPY services/api ./
COPY packages/engine /packages/engine
COPY deal-kit/deal.yaml /deal-kit/deal.yaml
COPY --from=pack /deal-kit/output /deal-kit/output
COPY fixtures /fixtures
COPY --from=web /web/dist /static

ENV PYTHONPATH=/packages/engine \
    DEAL_FILE=/deal-kit/deal.yaml \
    STATIC_DIR=/static

RUN useradd --create-home --uid 10001 workbench
USER workbench

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
