#!/usr/bin/env bash
set -euo pipefail

INPUT_DIR="${1:-testImg}"
OUTPUT_DIR="${2:-testImg/testImgOutput}"
URL="${3:-http://127.0.0.1:8000/convert}"

mkdir -p "${OUTPUT_DIR}"

shopt -s nullglob
FILES=("${INPUT_DIR}"/*.HEIC "${INPUT_DIR}"/*.heic)
shopt -u nullglob

if [ "${#FILES[@]}" -eq 0 ]; then
  echo "no HEIC files found in: ${INPUT_DIR}"
  exit 1
fi

for INPUT in "${FILES[@]}"; do
  BASENAME="$(basename "${INPUT}")"
  STEM="${BASENAME%.*}"
  OUTPUT="${OUTPUT_DIR}/${STEM}.jpg"

  curl -X POST \
    -F "file=@${INPUT};type=image/heic" \
    "${URL}" \
    --output "${OUTPUT}"

  echo "converted: ${INPUT} -> ${OUTPUT}"
done
