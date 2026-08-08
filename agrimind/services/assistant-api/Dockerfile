FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml ./
COPY packages ./packages
COPY services/assistant-api ./services/assistant-api
RUN uv sync --package assistant-api --no-dev
EXPOSE 8001
CMD ["uv", "run", "--package", "assistant-api", "uvicorn", "assistant_api.main:app", "--host", "0.0.0.0", "--port", "8001"]
