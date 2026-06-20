# GHG Emissions Reporting Platform — single container (FastAPI API + SQLite + dashboard)
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
# Run from backend/ so file-relative paths (../frontend, ../data) resolve.
# The database is created and seeded automatically on first startup.
WORKDIR /app/backend
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
