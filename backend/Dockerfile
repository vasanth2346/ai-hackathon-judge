FROM mcr.microsoft.com/playwright/python:v1.52.0-noble
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir 'google-auth[requests]==2.60.0'
COPY app ./app
RUN mkdir -p /app/evidence
ENV PYTHONPATH=/app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
