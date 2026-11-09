#!/usr/bin/env bash
# 阿里云 ECS 首次初始化（一次性，root 运行）。
# 前置: Ubuntu 22.04/24.04；deploy 用户的 SSH 公钥已可登录（见 docs/deployment.md）。
# 行为: 装基础包 → Python 3.12 → 创建 harness/deploy 用户与目录 → 装 MySQL 8 并建库建号 →
#       装 nginx 与 systemd 单元 → deploy 用户免密 sudo 收敛到 systemctl。
# 幂等: 重复执行不破坏已有数据；MySQL 密码只在首次生成并写入 /root/harness-mysql-password.txt。
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "请用 root 运行（sudo -i 后执行）" >&2
  exit 1
fi

echo "[bootstrap] 1/7 基础包"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y ca-certificates curl git rsync nginx mysql-server ufw

echo "[bootstrap] 2/7 Python 3.12"
PY=python3.12
if ! command -v "$PY" > /dev/null; then
  . /etc/os-release
  if [ "${VERSION_ID%%.*}" -ge 24 ]; then
    apt-get install -y python3.12 python3.12-venv python3.12-dev
  else
    # Ubuntu 22.04 走 deadsnakes PPA
    apt-get install -y software-properties-common
    add-apt-repository -y ppa:deadsnakes/ppa
    apt-get update -y
    apt-get install -y python3.12 python3.12-venv python3.12-dev
  fi
fi
"$PY" --version

echo "[bootstrap] 3/7 用户与目录"
id -u harness > /dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin harness
id -u deploy > /dev/null 2>&1 || useradd -m -s /bin/bash deploy
mkdir -p /opt/harness/releases /opt/harness/shared
touch /opt/harness/shared/.env
chmod 600 /opt/harness/shared/.env
chown -R deploy:deploy /opt/harness

echo "[bootstrap] 4/7 共享 Python venv"
if [ ! -x /opt/harness/shared/venv/bin/python ]; then
  "$PY" -m venv /opt/harness/shared/venv
fi
chown -R deploy:deploy /opt/harness/shared/venv

echo "[bootstrap] 5/7 MySQL 8 建库建号"
service mysql start || systemctl start mysql
PWFILE=/root/harness-mysql-password.txt
if [ ! -f "$PWFILE" ]; then
  DB_PW=$(openssl rand -hex 16)
  mysql -e "CREATE DATABASE IF NOT EXISTS harness_evolution CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
  mysql -e "CREATE USER IF NOT EXISTS 'harness'@'127.0.0.1' IDENTIFIED WITH caching_sha2_password BY '${DB_PW}';"
  mysql -e "GRANT ALL PRIVILEGES ON harness_evolution.* TO 'harness'@'127.0.0.1';"
  mysql -e "FLUSH PRIVILEGES;"
  echo "$DB_PW" > "$PWFILE"
  chmod 600 "$PWFILE"
  echo "[bootstrap] MySQL 账号密码已写入 $PWFILE（填入 .env 的 HE_DB_URL）"
else
  echo "[bootstrap] MySQL 账号已存在（见 $PWFILE），跳过"
fi
systemctl enable --now mysql

echo "[bootstrap] 6/7 nginx 与 systemd 单元"
CONF_DIR=/opt/harness/shared/config
mkdir -p "$CONF_DIR"
if [ ! -f /etc/nginx/sites-enabled/harness ]; then
  if [ -f "$CONF_DIR/nginx-harness.conf" ]; then
    cp "$CONF_DIR/nginx-harness.conf" /etc/nginx/sites-available/harness
  else
    echo "[bootstrap] 未找到 $CONF_DIR/nginx-harness.conf（首次发布流水线会带上），先放默认页"
    printf 'server { listen 80 default_server; root /var/www/html; }\n' > /etc/nginx/sites-available/harness
  fi
  ln -sf /etc/nginx/sites-available/harness /etc/nginx/sites-enabled/harness
  rm -f /etc/nginx/sites-enabled/default
fi
if [ ! -f /etc/systemd/system/harness-api.service ] && [ -f "$CONF_DIR/harness-api.service" ]; then
  cp "$CONF_DIR/harness-api.service" /etc/systemd/system/harness-api.service
  systemctl daemon-reload
  systemctl enable harness-api
fi
if [ ! -f /etc/systemd/system/harness-api.service ]; then
  echo "[bootstrap] 警告: $CONF_DIR/harness-api.service 缺失，服务单元未安装（重新执行本脚本可补）" >&2
fi
nginx -t
systemctl reload nginx || systemctl restart nginx

echo "[bootstrap] 7/7 deploy 用户 sudo 收敛"
SUDOERS=/etc/sudoers.d/harness-deploy
cat > "$SUDOERS" <<'EOF'
deploy ALL=(root) NOPASSWD: /usr/bin/systemctl restart harness-api, /usr/bin/systemctl start harness-api
EOF
chmod 440 "$SUDOERS"
visudo -c

echo "[bootstrap] 完成。下一步: 填 /opt/harness/shared/.env（参考 deploy/env.production.example），"
echo "           然后配置 GitHub Secrets 并触发首次发布。"
