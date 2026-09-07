FROM python:3.14-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY pyproject.toml README.md ./
COPY app ./app
COPY tests ./tests
COPY docs ./docs

RUN pip install --no-cache-dir ".[dev]"

EXPOSE 8081

CMD ["python", "-m", "app.public"]
