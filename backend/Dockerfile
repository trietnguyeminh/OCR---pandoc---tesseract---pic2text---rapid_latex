FROM python:3.11-slim

# System deps: pandoc -> editable Word equations, tesseract -> OCR fallback,
# libgl1/libglib -> opencv if you enable it later.
RUN apt-get update && apt-get install -y --no-install-recommends \
        pandoc tesseract-ocr libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
ENV FORMUDOC_DATA=/data PYTHONUNBUFFERED=1
RUN mkdir -p /data
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
