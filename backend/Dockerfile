FROM python:3.11-slim

WORKDIR /app

# ffmpeg is required by openai-whisper for audio decoding (mp3, ogg, webm, m4a).
# Without it, only .wav files work. Installing here keeps it in the image layer.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install CPU-only torch first — much smaller than the default CUDA build (~700MB vs ~2.5GB).
# Must be installed before openai-whisper so it doesn't pull the CUDA wheel.
RUN pip install --no-cache-dir \
    torch --index-url https://download.pytorch.org/whl/cpu

# Install project deps (layer cache — only re-runs if pyproject.toml changes)
COPY pyproject.toml .
RUN pip install --no-cache-dir -e "."

COPY app/ app/

ENV PORT=8080
EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]