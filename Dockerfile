FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Ensure the data folder exists
RUN mkdir -p /app/data

CMD ["python", "app.py"]
