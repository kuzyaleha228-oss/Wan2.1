#!/usr/bin/env bash
# =============================================================================
# «КАПИБАРА-ШАУРМИСТ» — Сцена 1 «Открытие»
# Готовый запуск генерации через Wan2.1 (T2V-1.3B) на машине с GPU.
# Требования: GPU с >= 8.2 GB VRAM (RTX 3060/4060 и выше), ~20 GB диска.
# =============================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR"

CKPT_DIR="${CKPT_DIR:-./checkpoints/Wan2.1-T2V-1.3B}"
SAVE_FILE="${SAVE_FILE:-./outputs/scene1_opening.mp4}"
mkdir -p outputs

echo "==> [1/3] Установка зависимостей..."
pip install -U "huggingface_hub[cli]"
pip install -r requirements.txt

if [ ! -d "$CKPT_DIR" ]; then
  echo "==> [2/3] Скачивание весов Wan2.1-T2V-1.3B (~10 GB, один раз)..."
  huggingface-cli download Wan-AI/Wan2.1-T2V-1.3B --local-dir "$CKPT_DIR"
else
  echo "==> [2/3] Веса уже на месте: $CKPT_DIR"
fi

echo "==> [3/3] Генерация сцены 1 (на RTX 4090 ~4 минуты)..."
python generate.py \
  --task t2v-1.3B \
  --size "832*480" \
  --ckpt_dir "$CKPT_DIR" \
  --save_file "$SAVE_FILE" \
  --prompt "A capybara wearing an apron and chef hat ceremonially opens the shutter of a small street food kiosk in Frankfurt, steam pouring out, sign reads CAPY SHAWARMA, morning light, cinematic, absurd comedy, high detail"

echo "==> Готово! Видео сохранено: $SAVE_FILE"
