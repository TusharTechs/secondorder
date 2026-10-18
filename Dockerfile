FROM python:3.12-slim-trixie
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV FALKORDB_LITE_PATH=/tmp/secondorder.db PORT=8000
EXPOSE 8000
# Uses embedded FalkorDB (falkordblite) unless FALKORDB_HOST points at a FalkorDB server / FalkorDB Cloud.
CMD ["sh", "-c", "uvicorn server.app:app --host 0.0.0.0 --port ${PORT}"]
