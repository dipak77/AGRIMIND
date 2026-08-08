FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml ./
COPY packages ./packages
COPY services/inference-service ./services/inference-service
RUN uv sync --package inference-service --no-dev
EXPOSE 8004
CMD ["uv", "run", "--package", "inference-service", "uvicorn", "inference_service.main:app", "--host", "0.0.0.0", "--port", "8004"]
