FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

WORKDIR /app

# 依存ライブラリのビルドに必要な最小限パッケージのインストール
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

# コンテナ起動時に初期シード（未作成時のみ実行）を行い、サーバーを起動
CMD ["sh", "-c", "python seed.py && uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]

