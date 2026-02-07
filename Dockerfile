# --- Build Stage ---
FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    python3-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .

# Install libraries to the /install prefix
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# --- Final Runner Stage ---
FROM python:3.11-slim AS runner

# Install runtime-only dependencies (like libpq for database connection)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Create a non-root user for security
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1

WORKDIR $HOME/app

# COPY the installed packages from the builder stage
# This is the "magic" of multi-stage builds
COPY --from=builder /install /usr/local

# Copy your application code and set ownership
COPY --chown=user . .

# Expose the port Render/HF expects
EXPOSE 7860

# Start the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]