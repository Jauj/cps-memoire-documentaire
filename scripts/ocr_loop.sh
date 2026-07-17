#!/bin/bash
# Ingestion en boucle des PDFs scannés CPS (OCR)
# Usage: bash scripts/ocr_loop.sh [max_iterations]
# Prérequis: poppler-utils, tesseract-ocr-fra, python3, pytesseract, Pillow

MAX=${1:-200}
for i in $(seq 1 $MAX); do
  result=$(python3 scripts/ocr_ingest_one.py 2>&1)
  echo "$result"
  if echo "$result" | grep -q "tous les.*traités"; then
    echo "=== OCR terminé ==="
    break
  fi
  sleep 0.5
done