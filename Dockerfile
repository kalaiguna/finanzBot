FROM python:3.12-slim

# poppler-utils provides pdfinfo/pdftoppm which pdfplumber needs
RUN apt-get update && apt-get install -y --no-install-recommends \
        poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8080
EXPOSE 8080

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--timeout", "120", "main:app"]
