FROM python:3.11-slim

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the simulator package preserving the package directory so that
# ``python -m simulator.main`` resolves correctly. The build context is the
# ``./simulator`` directory, so we re-nest it under /app/simulator.
COPY . /app/simulator

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

# The simulator is a long-running process. Use the package entrypoint so
# `python -m simulator.main` resolves correctly regardless of cwd.
CMD ["python", "-m", "simulator.main"]
