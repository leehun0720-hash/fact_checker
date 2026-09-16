FROM python:3.12-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && playwright install --with-deps chromium \
 && rm -rf /var/lib/apt/lists/*
COPY app ./app
COPY scripts ./scripts
# 데이터 볼륨은 호스팅(Railway 등)에서 /data 에 마운트한다. Dockerfile VOLUME 지시어는
# Railway 빌더가 거부하므로 쓰지 않는다.
ENV DATA_DIR=/data
EXPOSE 8000
# Railway/Cloud Run 등은 PORT 환경변수로 포트를 지정한다. 없으면 8000.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
