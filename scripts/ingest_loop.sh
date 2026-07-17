#!/bin/bash
# Ingestion en boucle des PDFs texte CPS
# Usage: bash scripts/ingest_loop.sh [max_iterations]
# Prérequis: pdftotext, python3, requests

MAX=${1:-500}
for i in $(seq 1 $MAX); do
  result=$(python3 scripts/ingest_one_pdf.py 2>&1)
  echo "$result"
  # Si le script retourne 0 et indique TERMINÉ, on arrête
  if echo "$result" | grep -q "TERMINÉ"; then
    echo "=== Ingestion texte terminée ==="
    break
  fi
  sleep 0.5
done