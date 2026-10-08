# Kshetra API. Build context: the backend/ folder (docker-compose) .
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
      libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b fonts-noto-core \
      tesseract-ocr tesseract-ocr-tel tesseract-ocr-hin \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt requirements-ai.txt ./
ARG WITH_AI=0
RUN pip install --no-cache-dir -r requirements.txt \
    && if [ "$WITH_AI" = "1" ]; then pip install --no-cache-dir -r requirements-ai.txt; fi
COPY . .
ENV PORT=8000
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
