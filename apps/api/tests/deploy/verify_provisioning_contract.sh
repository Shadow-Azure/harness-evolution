#!/usr/bin/env bash
# 部署 provisioning 契约（干净 Ubuntu 主机，root 运行）。
#
# 目的：把“部署运行时前置”变成 PR 必过检查，而不是等合并后的 Deploy 才发现主机缺包。
# 顺序：
#   1. 移除（若有）预装 bwrap，确保负例走真实缺包路径；
#   2. 负例：provision --check 必须退出 10 并输出 ATTRIBUTION_BWRAP_MISSING；
#   3. 正例：真实 provision 脚本安装，bwrap --version 与 harness 命名空间探针通过；
#   4. 真实 preflight：以 harness 身份运行候选代码的 attribution.preflight，必须 ready=True。
#
# 用法: sudo bash apps/api/tests/deploy/verify_provisioning_contract.sh
# 前置: 已安装 apps/api/.venv（CI job 负责），主机为 Ubuntu 22.04/24.04。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
PROVISION="$ROOT/deploy/provision-bubblewrap.sh"
PREFLIGHT_DIR="$ROOT/apps/api"
PYTHON="$PREFLIGHT_DIR/.venv/bin/python"
SERVICE_USER="harness"
PROBE_PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

log() { printf '[deploy-contract] %s\n' "$*"; }
fail() {
  printf '[deploy-contract] FAIL: %s\n' "$*" >&2
  exit 1
}

[ "$(id -u)" -eq 0 ] || fail "必须以 root 运行"
[ -x "$PROVISION" ] || fail "缺少可执行脚本: $PROVISION"
[ -x "$PYTHON" ] || fail "缺少 API venv: $PYTHON（先安装 apps/api 依赖）"

log "1/4 确认主机没有 bwrap"
if command -v bwrap >/dev/null 2>&1; then
  log "镜像预装了 bwrap，先移除，确保负例验证的是真实缺包路径"
  DEBIAN_FRONTEND=noninteractive apt-get remove -y bubblewrap >/dev/null
  hash -r
fi
if command -v bwrap >/dev/null 2>&1; then
  fail "无法移除预装 bwrap，负例不可信"
fi

log "2/4 负例：--check 必须识别缺包"
set +e
negative_output="$("$PROVISION" --check 2>&1)"
negative_status=$?
set -e
printf '%s\n' "$negative_output"
[ "$negative_status" -eq 10 ] || fail "--check 期望退出 10，实际 $negative_status"
grep -q 'state=missing' <<<"$negative_output" || fail "--check 未输出 state=missing"
grep -q 'error_code=ATTRIBUTION_BWRAP_MISSING' <<<"$negative_output" ||
  fail "--check 未输出 ATTRIBUTION_BWRAP_MISSING"

log "3/4 正例：真实 provision 脚本安装并验证"
if ! id -u "$SERVICE_USER" >/dev/null 2>&1; then
  useradd --system --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
fi
set +e
provision_output="$("$PROVISION" --install 2>&1)"
provision_status=$?
set -e
printf '%s\n' "$provision_output"
[ "$provision_status" -eq 0 ] || fail "--install 期望退出 0，实际 $provision_status"
grep -q 'state=ready' <<<"$provision_output" || fail "--install 未到达 state=ready"
hash -r
command -v bwrap >/dev/null 2>&1 || fail "安装后 PATH 中没有 bwrap"
bwrap --version || fail "bwrap --version 失败"
runuser -u "$SERVICE_USER" -- env -i "PATH=$PROBE_PATH" \
  bwrap --unshare-all --share-net --die-with-parent --ro-bind / / -- /bin/true ||
  fail "服务账号 $SERVICE_USER 的命名空间探针失败"

log "4/4 真实 preflight（服务账号 $SERVICE_USER）"
set +e
preflight_output="$(cd "$PREFLIGHT_DIR" && runuser -u "$SERVICE_USER" -- env -i \
  "PATH=$PREFLIGHT_DIR/.venv/bin:$PROBE_PATH" \
  HOME=/tmp \
  HE_JWT_SECRET=deploy-contract-only \
  HE_AI_AGENT_PROVIDER=claude-code \
  "$PYTHON" -m app.third_party_api.ai_agent.preflight 2>&1)"
preflight_status=$?
set -e
printf '%s\n' "$preflight_output"
[ "$preflight_status" -eq 0 ] || fail "attribution.preflight 期望退出 0，实际 $preflight_status"
grep -q 'attribution.preflight provider=.* ready=True' <<<"$preflight_output" ||
  fail "preflight 未输出 ready=True"

log "PASS：缺包负例、provision 正例与真实 preflight 全部通过"
