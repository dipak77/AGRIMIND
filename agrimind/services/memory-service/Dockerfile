FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml ./
COPY packages ./packages
COPY services/memory-service ./services/memory-service
RUN uv sync --package memory-service --no-dev
EXPOSE 8003
CMD ["uv", "run", "--package", "memory-service", "uvicorn", "memory_service.main:app", "--host", "0.0.0.0", "--port", "8003"]
