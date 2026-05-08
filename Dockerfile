FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Minimal system deps for common Python builds and tooling.
RUN apt-get update \
    && apt-get install -yq --no-install-recommends \
        build-essential \
        curl \
        git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install uv (Python dependency manager).
ENV UV_HOME="/root/.uv"
ENV PATH="/root/.local/bin:${PATH}"
RUN curl -LsSf https://astral.sh/uv/install.sh | bash

# Create a project venv and ensure it's used by default.
RUN uv venv /opt/venv -p "$(which python)"
ENV PATH="/opt/venv/bin:${PATH}"
ENV UV_PROJECT_ENVIRONMENT="/opt/venv"

WORKDIR /app

# Install dependencies (cached layer). If `uv.lock` exists, it will be used.
COPY pyproject.toml /app/
COPY uv.lock /app/uv.lock
RUN uv sync --no-install-project --extra dev

# Copy project files (mounted in compose for dev, but useful for image-only usage too).
COPY . /app

# Default to an interactive shell; compose can override this (e.g. to run Jupyter).
CMD ["/bin/bash"]
