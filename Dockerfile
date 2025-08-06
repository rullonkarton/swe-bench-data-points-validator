# Base Ubuntu image with Python 3.11
FROM --platform=linux/x86_64 python:3.11-slim

# Install system packages and dependencies
RUN apt-get update && apt-get install -y \
    wget \
    git \
    build-essential \
    curl \
    bash \
    && rm -rf /var/lib/apt/lists/*

# Create working directory
WORKDIR /workspace

# Install UV package manager for Python
RUN pip install uv

# Copy project configuration files
COPY pyproject.toml uv.lock ./

# Sync dependencies via UV
RUN uv sync

# Install SWE-bench for testing
RUN pip install swebench>=4.0.4

# Copy source code and data
COPY data_points_validator.py ./
COPY data_points/ ./data_points/
COPY scripts/ ./scripts/
COPY test_*.py ./

# Default entry point
CMD ["bash"] 