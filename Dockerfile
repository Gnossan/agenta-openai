FROM python:3.11-slim

WORKDIR /app

COPY ha_reader.py .
COPY requirements.txt .

RUN pip install -r requirements.txt

CMD ["python", "ha_reader.py"]
