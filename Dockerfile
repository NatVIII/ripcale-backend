FROM python:3.14-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

COPY scripts/bannerStart.txt scripts/bannerBuildWin.txt ./scripts/

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
COPY --from=ghcr.io/google/osv-scanner:latest /osv-scanner /usr/local/bin/osv-scanner

COPY pyproject.toml uv.lock README.md ./
COPY app ./app
COPY tests ./tests
COPY docs ./docs
COPY osv-scanner.toml ./

RUN uv sync --frozen --all-extras

# Security scan (F58.01): print the severity-sorted vulnerability report, then fail
# on un-acknowledged findings at/above SCAN_FAIL_ON (default high). Scan errors fail
# closed unless BUILD_DESPITE_OSV_DOWN is set (e.g. OSV temporarily unreachable).
ARG SCAN_FAIL_ON="high"
ARG BUILD_DESPITE_OSV_DOWN=""
RUN python -m app.audit --lockfile uv.lock --config osv-scanner.toml \
    --fail-severity "$SCAN_FAIL_ON" ${BUILD_DESPITE_OSV_DOWN:+--allow-scan-errors}

RUN cat scripts/bannerBuildWin.txt

EXPOSE 8081

CMD ["python", "-m", "app.public"]
