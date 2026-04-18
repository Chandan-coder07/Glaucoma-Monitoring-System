FROM python:3.11-slim

# System dependencies for serial port access and reportlab
RUN apt-get update && apt-get install -y \
    gcc \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Pre-train the ML model during build (so it's ready at startup)
RUN python -c "from services.ml_service import predict_risk; print('ML model ready:', predict_risk(18.0, 60, 540))"

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
