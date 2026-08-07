.PHONY: sync lint type test up down eval clean

sync:
	uv sync --all-packages

lint:
	uv run ruff check . --ignore RUF012,B017
	uv run ruff format --check .

format:
	uv run ruff check --fix .
	uv run ruff format .

type:
	uv run mypy packages/kernel

test:
	uv run pytest tests/unit -q

up:
	docker compose up -d

down:
	docker compose down -v

logs:
	docker compose logs -f

eval:
	uv run python -m eval.harness.run --dataset golden/en --threshold 0.9

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name ".coverage" -delete
	rm -rf .pytest_cache .mypy_cache .ruff_cache
