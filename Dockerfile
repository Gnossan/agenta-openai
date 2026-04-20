FROM python:3.11-slim

WORKDIR /app

COPY ha_reader.py .
COPY requirements.txt .

RUN pip install -r requirements.txt
RUN mkdir -p /data && echo '{"secret":"","ha_url":"","ha_token":"","openai_api_key":""}' > /data/options.json

CMD ["python", "ha_reader.py"]