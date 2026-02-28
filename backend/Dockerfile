# ---------- Base image with heavy libraries cached ----------
FROM python:3.9-slim AS base

WORKDIR /app

# Install system dependencies first (cached forever)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc libffi-dev libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements (so code changes do NOT break the cache)
COPY requirements.txt .

# Install Python dependencies ONCE and let Docker cache this layer
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && python -m spacy download en_core_web_sm


# ---------- Final runtime image ----------
FROM python:3.9-slim

WORKDIR /app

# Copy installed Python libs from the cached base image
COPY --from=base /usr/local/lib/python3.9 /usr/local/lib/python3.9
COPY --from=base /usr/local/bin /usr/local/bin

# Copy your backend source code
COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
