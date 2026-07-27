FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml .
COPY app ./app
RUN pip install --no-cache-dir .
COPY alembic.ini .
COPY migrations ./migrations
COPY scripts ./scripts
RUN addgroup --system petdressed && adduser --system --ingroup petdressed petdressed \
    && chown -R petdressed:petdressed /app
USER petdressed
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
