FROM python:3.12-slim

# System libs required by OpenCV / onnxruntime / insightface.
# build-essential provides g++, needed to compile insightface's mesh_core_cython extension.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Pre-download the buffalo_l model pack at build time so the first request
# doesn't pay the download cost. Safe to fail here (e.g. offline build) -
# the model will then be downloaded lazily on first startup instead.
RUN python -c "from insightface.app import FaceAnalysis; FaceAnalysis(name='buffalo_l', providers=['CPUExecutionProvider']).prepare(ctx_id=-1)" || true

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
