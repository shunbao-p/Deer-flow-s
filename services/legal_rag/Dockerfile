FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY services/legal_rag/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY services/legal_rag /app

EXPOSE 8003

CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8003"]
