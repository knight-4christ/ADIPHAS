# ---------- Base image with heavy libraries cached ----------
FROM python:3.9-slim AS base

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc libffi-dev libssl-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt


# ---------- Final runtime image ----------
FROM python:3.9-slim

WORKDIR /app

COPY --from=base /usr/local/lib/python3.9 /usr/local/lib/python3.9
COPY --from=base /usr/local/bin /usr/local/bin

COPY . .

CMD ["streamlit", "run", "app.py", "--server.port", "8501", "--server.address", "0.0.0.0"]
