#!/usr/bin/env bash
# نصب و راه‌اندازی فارکس بات روی اوبونتو
# استفاده (از داخل پوشه پروژه که شامل app/، requirements.txt و ... است):
#   sudo bash install.sh
#
# اگر پروژه را در گیت‌هاب خودتان قرار دهید، می‌توانید با یک خط نصب کنید:
#   curl -fsSL https://raw.githubusercontent.com/<user>/<repo>/main/install.sh | sudo bash -s -- <repo_url>
set -euo pipefail

APP_DIR="/opt/forex-bot"
SERVICE_NAME="forex-bot"
RUN_USER="${SUDO_USER:-$(whoami)}"
REPO_URL="${1:-}"

echo "==> نصب پیش‌نیازهای سیستم..."
apt-get update -y
apt-get install -y python3 python3-venv python3-pip git

echo "==> آماده‌سازی مسیر نصب: ${APP_DIR}"
mkdir -p "$APP_DIR"

if [ -n "$REPO_URL" ]; then
  echo "==> دریافت پروژه از ریپازیتوری: $REPO_URL"
  git clone --depth 1 "$REPO_URL" "$APP_DIR/src_tmp"
  cp -r "$APP_DIR/src_tmp"/* "$APP_DIR/"
  rm -rf "$APP_DIR/src_tmp"
else
  echo "==> کپی پروژه از پوشه فعلی به ${APP_DIR}"
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  cp -r "$SCRIPT_DIR"/* "$APP_DIR/"
fi

cd "$APP_DIR"

if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "==> فایل .env از روی نمونه ساخته شد. DASHBOARD_PASSWORD را حتماً تنظیم کنید."
fi

mkdir -p config
if [ ! -f "config/accounts.json" ]; then
  echo '{"accounts": []}' > config/accounts.json
  echo "==> حساب‌ها و جفت‌ارزها را از داخل خود داشبورد اضافه کنید (config/accounts.json خالی ساخته شد)."
fi

echo "==> ساخت محیط مجازی پایتون و نصب وابستگی‌ها..."
python3 -m venv venv
"$APP_DIR/venv/bin/pip" install --upgrade pip
"$APP_DIR/venv/bin/pip" install -r requirements.txt

echo "==> تنظیم سرویس systemd..."
sed "s/%i/${RUN_USER}/g" forex-bot.service > "/etc/systemd/system/${SERVICE_NAME}.service"
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

if command -v ufw >/dev/null 2>&1 && ufw status | grep -q "Status: active"; then
  echo "==> باز کردن پورت ۸۹۹۹ در فایروال ufw..."
  ufw allow 8999/tcp
fi

echo ""
echo "==================================================================="
echo " نصب کامل شد."
echo " داشبورد در آدرس: http://<IP-سرور-شما>:8999"
echo " فایل تنظیمات: ${APP_DIR}/.env  (حتماً قبل از فعال‌سازی حالت live تکمیل کنید)"
echo " مشاهده لاگ سرویس: journalctl -u ${SERVICE_NAME} -f"
echo "==================================================================="
