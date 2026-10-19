# Kshetra API for Hugging Face Spaces (free CPU: 2 vCPU, 16 GB RAM) or any Docker host.
# Build context: repository root.   docker build -t kshetra-api .
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
      libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b fonts-noto-core \
      tesseract-ocr tesseract-ocr-tel tesseract-ocr-hin \
    && rm -rf /var/lib/apt/lists/*
# Spaces run containers as user 1000.
RUN useradd -m -u 1000 user
WORKDIR /app
COPY backend/requirements.txt backend/requirements-ai.txt ./
ARG WITH_AI=1
RUN pip install --no-cache-dir -r requirements.txt \
    && if [ "$WITH_AI" = "1" ]; then pip install --no-cache-dir -r requirements-ai.txt; fi
COPY --chown=user backend/ /app/
COPY --chown=user database/seeds /app/seeds
COPY --chown=user database/schema.sql /app/schema.sql
USER user
ENV HOME=/home/user PORT=7860 HF_HOME=/home/user/.cache/huggingface
EXPOSE 7860
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
