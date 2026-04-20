FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    BUG_TRIAGE_SEED=false \
    FORWARDED_ALLOW_IPS=*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY run_dashboard.py ./

RUN python -m pip install --upgrade pip \
    && python -m pip install .

EXPOSE 8000

CMD ["sh", "-c", "python -m uvicorn bug_triage.app:create_app --factory --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers"]
