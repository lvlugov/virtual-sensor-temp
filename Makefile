up:
	@echo "Starting development environment..."
	docker compose up -d dev

down:
	@echo "Stopping development environment..."
	docker compose down

shell:
	@echo "Opening a shell in the dev container..."
	@docker compose ps -q dev >/dev/null 2>&1 && docker compose ps -q dev | grep -q . && \
		docker compose exec dev /bin/bash || \
		docker compose run --rm dev /bin/bash

build:
	@echo "Building the Docker images..."
	docker compose build

clean:
	@echo "Cleaning development environment..."
	docker compose down -v --remove-orphans

format:
	@echo "Formatting code..."
	docker compose run --rm dev ruff format .
	docker compose run --rm dev ruff check --fix .

lint:
	@echo "Running lint checks..."
	docker compose run --rm dev ruff check .

test:
	@echo "Running tests..."
	docker compose run --rm dev pytest

# Generate a fresh dataset to a temp file, run all tests (including dataset-dependent
# ones), then discard the CSV. Does not overwrite config/outputs/synthetic_*.csv.
test-dataset:
	@echo "Running tests against a freshly generated dataset (not saved)..."
	docker compose run --rm dev bash -c '\
		set -euo pipefail; \
		TMP=$$(mktemp --suffix=.csv); \
		trap "rm -f \"$$TMP\"" EXIT; \
		python lean_virtual_sensor/inputs_generation/generate.py --output-path "$$TMP" && \
		pytest tests/ --dataset "$$TMP"'

sync:
	@echo "Syncing Python dependencies (uv)..."
	docker compose run --rm dev uv sync --extra dev

notebook-server:
	@echo "Starting Jupyter Notebook server in container..."
	docker compose exec dev jupyter notebook --ip=0.0.0.0 --port=8888 --no-browser --allow-root

# Help command
help:
	@echo "Available commands:"
	@echo "  up         - Start development environment"
	@echo "  down       - Stop development environment"
	@echo "  shell      - Open shell in dev container"
	@echo "  build      - Build Docker images"
	@echo "  clean      - Clean development environment (removes volumes)"
	@echo "  format     - Format code with ruff"
	@echo "  lint       - Lint code with ruff"
	@echo "  test          - Run tests (dataset-dependent tests skipped unless --dataset passed)"
	@echo "  test-dataset  - Generate fresh CSV to temp; run full suite; discard CSV"
	@echo "  sync          - Sync Python dependencies with uv"
	@echo "  notebook-server - Start classic notebook server (connect IDE to URL)"
	@echo "  help       - Show this help message"

.PHONY: up down shell build clean format lint test test-dataset sync notebook-server help
