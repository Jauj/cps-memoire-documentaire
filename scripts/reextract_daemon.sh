#!/bin/bash
# Boucle de ré-extraction — lancer en arrière-plan avec nohup
# nohup bash scripts/reextract_daemon.sh &
# tail -f data/reextract_log.txt
WORKER="${WORKER_URL:-https://revue-presse.jeanneaj.workers.dev}"
MAX=${1:-200}
for i in $(seq 1 $MAX); do
  RESULT=$(WORKER_URL="$WORKER" python3 scripts/reextract_one.py 2>&1)
  echo "$RESULT"
  if echo "$RESULT" | grep -q "Aucun document\|Tous traités\|Tous les documents"; then
    echo "=== Ré-extraction terminée ==="
    break
  fi
  sleep 0.3
done