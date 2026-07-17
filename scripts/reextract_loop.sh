#!/bin/bash
# Ré-extraction en boucle des claims en erreur/chunked
# Usage: bash scripts/reextract_loop.sh [max_iterations]
MAX=${1:-120}
for i in $(seq 1 $MAX); do
  result=$(python3 scripts/reextract_one.py 2>&1)
  echo "$result"
  if echo "$result" | grep -q "Aucun document\|Tous traités\|Tous les documents"; then
    echo "=== Ré-extraction terminée ==="
    break
  fi
  sleep 0.5
done