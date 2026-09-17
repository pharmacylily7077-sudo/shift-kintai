#!/bin/bash
set -e

# ============================================================
# Google Cloud Run デプロイスクリプト
# 薬局シフト勤怠・個人給与シミュレータ＆有休管理Webアプリ
# ============================================================

SERVICE_NAME="pharmacy-shift-kintai"
REGION="asia-northeast1" # 東京リージョン

echo "===================================================="
echo "🚀 Google Cloud Run へのデプロイを開始します..."
echo "サービス名: ${SERVICE_NAME}"
echo "リージョン: ${REGION}"
echo "===================================================="

# gcloud コマンドの確認
if ! command -v gcloud &> /dev/null; then
    echo "❌ エラー: Google Cloud SDK (gcloud) がインストールされていません。"
    echo "https://cloud.google.com/sdk/docs/install を参照してインストールしてください。"
    exit 1
fi

# デプロイ実行 (ソースコードから直接Cloud Buildでコンテナ化してデプロイ)
gcloud run deploy ${SERVICE_NAME} \
    --source . \
    --region ${REGION} \
    --platform managed \
    --allow-unauthenticated \
    --port 8080 \
    --memory 512Mi \
    --cpu 1 \
    --min-instances 0 \
    --max-instances 2

echo "===================================================="
echo "🎉 デプロイが完了しました！"
echo "発行されたURLからスマホ・PCですぐに利用できます。"
echo "===================================================="
