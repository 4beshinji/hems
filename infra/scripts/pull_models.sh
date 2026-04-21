#!/usr/bin/env bash
# Fetch GGUF + mmproj + TEI embedding weights into ./models/ so the
# `llm`, `vlm-light`, `vlm-heavy`, and `embed` services can start.
#
# Source files are large. Downloads are resumable (curl -C -). Existing files
# are skipped. Override any URL via env vars to pin a specific quantization
# (see the DEFAULT_* block below).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
MODELS_DIR="${REPO_ROOT}/models"
EMBED_DIR="${MODELS_DIR}/embed"

mkdir -p "${MODELS_DIR}" "${EMBED_DIR}"

# --- Defaults --------------------------------------------------------------
DEFAULT_LLM_URL="https://huggingface.co/bartowski/Qwen2.5-14B-Instruct-GGUF/resolve/main/Qwen2.5-14B-Instruct-Q4_K_M.gguf"
DEFAULT_LLM_FILE="Qwen2.5-14B-Instruct-Q4_K_M.gguf"

DEFAULT_VLM_LIGHT_MODEL_URL="https://huggingface.co/openbmb/MiniCPM-V-2_6-gguf/resolve/main/ggml-model-Q4_K_M.gguf"
DEFAULT_VLM_LIGHT_MODEL_FILE="MiniCPM-V-2_6-Q4_K_M.gguf"
DEFAULT_VLM_LIGHT_MMPROJ_URL="https://huggingface.co/openbmb/MiniCPM-V-2_6-gguf/resolve/main/mmproj-model-f16.gguf"
DEFAULT_VLM_LIGHT_MMPROJ_FILE="mmproj-MiniCPM-V-2_6-f16.gguf"

DEFAULT_VLM_HEAVY_MODEL_URL="https://huggingface.co/bartowski/Qwen2-VL-7B-Instruct-GGUF/resolve/main/Qwen2-VL-7B-Instruct-Q4_K_M.gguf"
DEFAULT_VLM_HEAVY_MODEL_FILE="Qwen2-VL-7B-Instruct-Q4_K_M.gguf"
DEFAULT_VLM_HEAVY_MMPROJ_URL="https://huggingface.co/bartowski/Qwen2-VL-7B-Instruct-GGUF/resolve/main/mmproj-Qwen2-VL-7B-Instruct-f16.gguf"
DEFAULT_VLM_HEAVY_MMPROJ_FILE="mmproj-Qwen2-VL-7B-f16.gguf"

# --- Overrides -------------------------------------------------------------
LLM_URL="${LLM_URL:-${DEFAULT_LLM_URL}}"
LLM_FILE="${LLM_FILE:-${DEFAULT_LLM_FILE}}"
VLM_LIGHT_MODEL_URL="${VLM_LIGHT_MODEL_URL:-${DEFAULT_VLM_LIGHT_MODEL_URL}}"
VLM_LIGHT_MODEL_FILE="${VLM_LIGHT_MODEL_FILE:-${DEFAULT_VLM_LIGHT_MODEL_FILE}}"
VLM_LIGHT_MMPROJ_URL="${VLM_LIGHT_MMPROJ_URL:-${DEFAULT_VLM_LIGHT_MMPROJ_URL}}"
VLM_LIGHT_MMPROJ_FILE="${VLM_LIGHT_MMPROJ_FILE:-${DEFAULT_VLM_LIGHT_MMPROJ_FILE}}"
VLM_HEAVY_MODEL_URL="${VLM_HEAVY_MODEL_URL:-${DEFAULT_VLM_HEAVY_MODEL_URL}}"
VLM_HEAVY_MODEL_FILE="${VLM_HEAVY_MODEL_FILE:-${DEFAULT_VLM_HEAVY_MODEL_FILE}}"
VLM_HEAVY_MMPROJ_URL="${VLM_HEAVY_MMPROJ_URL:-${DEFAULT_VLM_HEAVY_MMPROJ_URL}}"
VLM_HEAVY_MMPROJ_FILE="${VLM_HEAVY_MMPROJ_FILE:-${DEFAULT_VLM_HEAVY_MMPROJ_FILE}}"

FETCH_LLM="${FETCH_LLM:-1}"
FETCH_VLM_LIGHT="${FETCH_VLM_LIGHT:-1}"
FETCH_VLM_HEAVY="${FETCH_VLM_HEAVY:-0}"

# --- Helpers ---------------------------------------------------------------
fetch() {
    local url="$1"
    local dest="$2"
    if [[ -f "${dest}" ]]; then
        echo "✓ exists: ${dest}"
        return
    fi
    echo "↓ fetching: ${url}"
    echo "       → ${dest}"
    curl -fL --retry 3 --retry-delay 5 -C - -o "${dest}.part" "${url}"
    mv "${dest}.part" "${dest}"
}

echo "Models directory: ${MODELS_DIR}"

if [[ "${FETCH_LLM}" == "1" ]]; then
    fetch "${LLM_URL}" "${MODELS_DIR}/${LLM_FILE}"
else
    echo "- skipping LLM (FETCH_LLM=0)"
fi

if [[ "${FETCH_VLM_LIGHT}" == "1" ]]; then
    fetch "${VLM_LIGHT_MODEL_URL}"  "${MODELS_DIR}/${VLM_LIGHT_MODEL_FILE}"
    fetch "${VLM_LIGHT_MMPROJ_URL}" "${MODELS_DIR}/${VLM_LIGHT_MMPROJ_FILE}"
else
    echo "- skipping VLM light (FETCH_VLM_LIGHT=0)"
fi

if [[ "${FETCH_VLM_HEAVY}" == "1" ]]; then
    fetch "${VLM_HEAVY_MODEL_URL}"  "${MODELS_DIR}/${VLM_HEAVY_MODEL_FILE}"
    fetch "${VLM_HEAVY_MMPROJ_URL}" "${MODELS_DIR}/${VLM_HEAVY_MMPROJ_FILE}"
else
    echo "- skipping VLM heavy (set FETCH_VLM_HEAVY=1 to include)"
fi

echo ""
echo "TEI embedding weights are fetched automatically on first boot into"
echo "  ${EMBED_DIR}"
echo "Override model via EMBEDDING_HF_MODEL (default: nomic-ai/nomic-embed-text-v1.5)."
echo ""
echo "Done. Now run:"
echo "  python infra/scripts/gpu_setup.py"
echo "  cd infra && docker compose -f docker-compose.yml -f docker-compose.gpu.yml --profile llm up -d --build"
