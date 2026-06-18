# Virtual Sensor (Model Development)

This repository is for **data science / model development** work (experimentation, training, evaluation). It is **not** intended to be the production deployment repository.

The current focus is the **Lean Virtual Sensor**.

## Development environment (Docker)

All development is intended to happen in Docker to keep the environment reproducible across the team.

### Prerequisites

- Docker Desktop (or Docker Engine) with `docker compose`

### Quick start

```bash
make build
make up
make shell
```

### Available commands

```bash
make help
```

Common ones:

- `make build`: build the dev image
- `make up`: start a long-lived dev container (`virtual-sensor-dev`)
- `make shell`: open a shell inside the running container
- `make sync`: install/sync Python dependencies (from `uv.lock`)
- `make test`: run tests (fast; dataset-dependent tests skip unless `--dataset` is passed)
- `make test-dataset`: generate a fresh CSV to a temp file, run the full suite, discard the CSV
- `make lint`: ruff lint
- `make format`: ruff format + autofix
- `make down`: stop the container
- `make clean`: stop container and remove volumes/orphans

### Where commands run

Run `make ...` commands from your **host machine**. They execute tools inside Docker for you.

If you are already inside the container (e.g. after `make shell`), you can run Python directly:

```bash
python -c "import numpy, pandas; print(numpy.__version__, pandas.__version__)"
pytest
ruff check .
```

### Notebooks (Cursor / VSCode) using Docker kernel (no “attach container” window)

This workflow keeps your IDE in the normal local window, while notebook execution happens inside Docker.

1) Start the container:

```bash
make up
```

2) Start the Notebook server in the container:

```bash
make notebook-server
```

3) Copy the URL printed in the terminal (it includes `?token=...`).

4) In Cursor/VSCode, connect to that server:

- Command Palette → `Jupyter: Specify Jupyter Server URI` (or `Jupyter: Select Jupyter Server`)
- Paste the URL, but if it contains `0.0.0.0`, replace the host with `127.0.0.1`:
  - use `http://127.0.0.1:8888/?token=...`

### Dependencies (`uv`)

Dependencies are managed with `uv` via `pyproject.toml`, and pinned in `uv.lock`.

Sync dependencies in the container (main + `dev` extras):

```bash
make sync
```

To add/change dependencies, update `pyproject.toml`, regenerate `uv.lock`, then rebuild the image (`make build`).
