FROM python:3.11-slim

WORKDIR /app

COPY src /app/src
COPY pyproject.toml /app/pyproject.toml
RUN pip install --no-cache-dir -e .[observability]

COPY apps/orchestrator /app/apps/orchestrator

CMD ["python", "apps/orchestrator/main.py"]
