FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8080

# exec replaces the shell so SIGTERM from Cloud Run reaches uvicorn directly
CMD exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT}
