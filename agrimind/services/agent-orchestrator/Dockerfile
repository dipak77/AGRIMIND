FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml ./
COPY packages ./packages
COPY services/agent-orchestrator ./services/agent-orchestrator
RUN uv sync --package agent-orchestrator --no-dev
EXPOSE 8002
CMD ["uv", "run", "--package", "agent-orchestrator", "uvicorn", "agent_orchestrator.main:app", "--host", "0.0.0.0", "--port", "8002"]
