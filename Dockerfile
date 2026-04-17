FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

RUN curl -L https://github.com/qdrant/qdrant/releases/download/v1.9.0/qdrant-x86_64-unknown-linux-musl.tar.gz \
    | tar -xz && mv qdrant /usr/local/bin/qdrant

COPY ha_reader.py .
COPY requirements.txt .

RUN pip install -r requirements.txt
RUN mkdir -p /data && echo '{"secret":"","ha_url":"","ha_token":"","openai_api_key":""}' > /data/options.json

CMD ["/bin/bash", "-c", "qdrant & sleep 3 && python ha_reader.py"]