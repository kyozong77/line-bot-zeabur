FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create logs directory
RUN mkdir -p /app/logs && chmod 777 /app/logs

EXPOSE 5000

CMD ["gunicorn", "--config", "gunicorn_config.py", "app.app:app"]
