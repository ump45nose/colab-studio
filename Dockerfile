FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    STUDIO_HOST=0.0.0.0 \
    STUDIO_PORT=18104 \
    STUDIO_DATA=/data \
    STUDIO_IN_DOCKER=1 \
    COLAB_BIN=/usr/local/bin/colab

RUN apt-get update \
 && apt-get install -y --no-install-recommends openssh-client curl ca-certificates tar \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY server/requirements.txt server/requirements.txt
RUN pip install --no-cache-dir -r server/requirements.txt google-colab-cli \
 && groupadd --gid 1001 studio \
 && useradd --uid 1000 --gid 1001 --create-home --home-dir /home/studio studio \
 && install -d -m 0755 -o 1000 -g 1001 /data /home/studio/.config/colab-cli

COPY VERSION ./
COPY station/ station/
COPY server/ server/

VOLUME ["/data", "/home/studio/.config/colab-cli"]
EXPOSE 18104
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('STUDIO_PORT', '18104') + '/api/state', timeout=3).read()"
CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "18104"]
