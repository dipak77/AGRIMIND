FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml ./
COPY packages ./packages
COPY services/gateway-service ./services/gateway-service
RUN uv sync --package gateway-service --no-dev
ENV PYTHONPATH=/app/packages/agrimind-kernel
EXPOSE 8000
CMD ["uv", "run", "--package", "gateway-service", "uvicorn", "gateway_service.main:app", "--host", "0.0.0.0", "--port", "8000"]
