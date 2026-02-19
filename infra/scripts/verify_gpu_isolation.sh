#!/usr/bin/env bash
# verify_gpu_isolation.sh — カーネル安定化 + GPU分離の検証スクリプト
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'
PASS=0; FAIL=0; WARN=0

pass() { echo -e "  ${GREEN}[PASS]${NC} $1"; ((PASS++)); }
fail() { echo -e "  ${RED}[FAIL]${NC} $1"; ((FAIL++)); }
warn() { echo -e "  ${YELLOW}[WARN]${NC} $1"; ((WARN++)); }

echo "=== SOMS GPU Isolation Verification ==="
echo ""

# --- 1. カーネルバージョン ---
echo "1. Kernel version"
KVER=$(uname -r)
echo "   Current: $KVER"
if [[ "$KVER" == 6.8.0-41-generic ]]; then
    pass "Stable kernel 6.8.0-41-generic"
elif [[ "$KVER" == 6.17.* ]]; then
    warn "Running dev kernel $KVER (6.8 was target)"
else
    warn "Unexpected kernel $KVER"
fi
echo ""

# --- 2. amdgpu モジュール ---
echo "2. amdgpu module"
if lsmod | grep -q amdgpu; then
    pass "amdgpu module loaded"
else
    fail "amdgpu module NOT loaded"
fi
echo ""

# --- 3. DRI デバイス ---
echo "3. DRI devices"
ls -la /dev/dri/ 2>/dev/null || { fail "/dev/dri not found"; }
echo ""
EXPECTED_DEVS=(card1 card2 renderD128 renderD129)
for dev in "${EXPECTED_DEVS[@]}"; do
    if [[ -e /dev/dri/$dev ]]; then
        pass "/dev/dri/$dev exists"
    else
        fail "/dev/dri/$dev missing"
    fi
done
echo ""

# --- 4. DRI by-path (ノード番号の安定性確認) ---
echo "4. DRI by-path mapping"
if [[ -d /dev/dri/by-path ]]; then
    ls -la /dev/dri/by-path/
    echo ""
    # dGPU = 03:00.0, iGPU = 0e:00.0
    DGPU_CARD=$(readlink -f /dev/dri/by-path/pci-0000:03:00.0-card 2>/dev/null || echo "NONE")
    DGPU_RENDER=$(readlink -f /dev/dri/by-path/pci-0000:03:00.0-render 2>/dev/null || echo "NONE")
    echo "   dGPU (03:00.0) card   -> $DGPU_CARD"
    echo "   dGPU (03:00.0) render -> $DGPU_RENDER"

    if [[ "$DGPU_CARD" == "/dev/dri/card1" && "$DGPU_RENDER" == "/dev/dri/renderD128" ]]; then
        pass "dGPU mapped to card1/renderD128 (matches docker-compose)"
    else
        fail "dGPU NOT on card1/renderD128 — docker-compose.yml needs update!"
        echo -e "   ${RED}Update infra/docker-compose.yml and infra/llm/docker-compose.yml${NC}"
        echo "   Replace card1/renderD128 with the actual dGPU device nodes above"
    fi
else
    warn "/dev/dri/by-path not found — cannot verify node stability"
fi
echo ""

# --- 5. rocm-smi ---
echo "5. ROCm SMI (host)"
if command -v rocm-smi &>/dev/null; then
    rocm-smi --showid --showproductname 2>/dev/null || warn "rocm-smi failed"
    pass "rocm-smi available"
else
    warn "rocm-smi not installed on host (OK if using container only)"
fi
echo ""

# --- 6. Docker GPU isolation test ---
echo "6. Docker container GPU isolation"
if command -v docker &>/dev/null; then
    echo "   Running rocm-smi inside container with card1+renderD128 only..."
    if sudo docker run --rm \
        --device /dev/kfd \
        --device /dev/dri/card1 \
        --device /dev/dri/renderD128 \
        rocm/rocm-terminal rocm-smi 2>/dev/null; then
        pass "Container sees dGPU via isolated devices"
    else
        fail "Container rocm-smi failed"
    fi
else
    warn "docker not found — skipping container test"
fi
echo ""

# --- 7. GRUB 設定確認 ---
echo "7. GRUB configuration"
if [[ -r /etc/default/grub ]]; then
    GRUB_DEFAULT=$(grep '^GRUB_DEFAULT=' /etc/default/grub | cut -d= -f2)
    GRUB_STYLE=$(grep '^GRUB_TIMEOUT_STYLE=' /etc/default/grub | cut -d= -f2)
    GRUB_TIMEOUT=$(grep '^GRUB_TIMEOUT=' /etc/default/grub | cut -d= -f2)
    echo "   GRUB_DEFAULT=$GRUB_DEFAULT"
    echo "   GRUB_TIMEOUT_STYLE=$GRUB_STYLE"
    echo "   GRUB_TIMEOUT=$GRUB_TIMEOUT"

    if [[ "$GRUB_STYLE" == "menu" ]]; then
        pass "GRUB menu visible"
    else
        fail "GRUB_TIMEOUT_STYLE=$GRUB_STYLE (expected: menu)"
    fi

    if [[ "$GRUB_TIMEOUT" -ge 3 ]] 2>/dev/null; then
        pass "GRUB timeout=${GRUB_TIMEOUT}s"
    else
        fail "GRUB_TIMEOUT=$GRUB_TIMEOUT (expected: >=3)"
    fi

    if [[ "$GRUB_DEFAULT" == "saved" ]]; then
        pass "GRUB_DEFAULT=saved (grub-set-default active)"
    else
        warn "GRUB_DEFAULT=$GRUB_DEFAULT (set to 'saved' for grub-set-default)"
    fi
else
    warn "/etc/default/grub not readable"
fi
echo ""

# --- 8. docker-compose デバイス設定確認 ---
echo "8. docker-compose GPU device config"
COMPOSE_FILES=(
    "$(dirname "$0")/../docker-compose.yml"
    "$(dirname "$0")/../llm/docker-compose.yml"
)
for f in "${COMPOSE_FILES[@]}"; do
    if [[ -f "$f" ]]; then
        fname=$(basename "$(dirname "$f")")/$(basename "$f")
        if grep -q '/dev/dri:/dev/dri' "$f"; then
            fail "$fname still has /dev/dri full passthrough!"
        elif grep -q '/dev/dri/card' "$f"; then
            pass "$fname uses isolated GPU devices"
        else
            warn "$fname has no GPU device config"
        fi
    fi
done
echo ""

# --- Summary ---
echo "=== Results ==="
echo -e "  ${GREEN}PASS: $PASS${NC}  ${RED}FAIL: $FAIL${NC}  ${YELLOW}WARN: $WARN${NC}"
if [[ $FAIL -gt 0 ]]; then
    echo -e "  ${RED}Some checks failed — review above output${NC}"
    exit 1
elif [[ $WARN -gt 0 ]]; then
    echo -e "  ${YELLOW}All critical checks passed, warnings present${NC}"
    exit 0
else
    echo -e "  ${GREEN}All checks passed${NC}"
    exit 0
fi
