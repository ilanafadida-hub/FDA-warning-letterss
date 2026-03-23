FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt uvicorn fastapi

# Copy all application code
COPY . .

# Create data directory
RUN mkdir -p data

# Create startup script: fetch data if needed, then run both services
RUN echo '#!/bin/sh\n\
echo "[STARTUP] Checking for data..."\n\
if [ ! -f data/warning_letters.csv ]; then\n\
  echo "[STARTUP] No data found. Fetching first 100 letters..."\n\
  python fetch_fda_data.py --limit 100 2>&1\n\
  echo "[STARTUP] Summarizing..."\n\
  python summarize_letters.py 2>&1\n\
  echo "[STARTUP] Data ready!"\n\
fi\n\
echo "[STARTUP] Launching dashboard on port ${PORT:-8501}..."\n\
streamlit run dashboard.py --server.port ${PORT:-8501} --server.address 0.0.0.0 --server.headless true\n\
' > /app/start.sh && chmod +x /app/start.sh

EXPOSE ${PORT:-8501}

CMD ["sh", "/app/start.sh"]
