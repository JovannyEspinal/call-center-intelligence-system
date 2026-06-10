.PHONY: install test test-integration test-all lint format run smoke-real eval-demo clean

install:
	uv sync --all-groups

test:
	uv run pytest tests/unit tests/security -v

test-integration:
	uv run pytest tests/integration -v

test-all:
	uv run pytest tests/ -v

lint:
	uv run ruff check .

format:
	uv run ruff format .
	uv run ruff check . --fix

run:
	uv run python app.py

smoke-real:
	test -n "$(AUDIO)" || (echo "Usage: make smoke-real AUDIO=/path/to/call.wav" && exit 2)
	uv run python scripts/smoke_real_providers.py --audio "$(AUDIO)"

eval-demo:
	uv run python scripts/evaluate_demo_outputs.py

clean:
	find . -type d \( -name ".pytest_cache" -o -name ".ruff_cache" -o -name "__pycache__" \) -prune -exec rm -rf {} +
	find . -type f \( -name "*.pyc" -o -name ".coverage" \) -delete
