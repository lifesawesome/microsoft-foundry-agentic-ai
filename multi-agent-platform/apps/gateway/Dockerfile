FROM python:3.11-slim

WORKDIR /app

# Install the shared library and gateway dependencies.
COPY src /app/src
COPY pyproject.toml /app/pyproject.toml
RUN pip install --no-cache-dir -e .[gateway,observability]

COPY apps/gateway /app/apps/gateway
ENV PYTHONPATH=/app/apps/gateway

EXPOSE 8080

CMD ["python", "apps/gateway/main.py"]
