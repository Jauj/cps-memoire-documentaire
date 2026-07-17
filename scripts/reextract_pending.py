#!/usr/bin/env python3
"""
Ré-extraction des claims pour les documents en erreur/chunked.
Interroge /memory/reextract-pending, puis POST /memory/documents/:id/reextract.
Resumable : sauve l'état après chaque document.

Usage:
  export WORKER_URL=https://your-worker.workers.dev
  python3 scripts/reextract_pending.py
"""
import json, time, sys, os, requests, traceback
from datetime import datetime

WORKER = os.environ.get("WORKER_URL", "https://revue-presse.jeanneaj.workers.dev")
STATE_FILE = os.environ.get("REEXTRACT_STATE", "data/reextract_state.json")
LOG_FILE = os.environ.get("REEXTRACT_LOG", "data/reextract_log.txt")

os.makedirs(os.path.dirname(STATE_FILE) or "data", exist_ok=True)

def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    line = f"{ts} {msg}"
    print(line, flush=True)
    with open(LOG_FILE, 'a') as f:
        f.write(line + "\n")

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"last_index": 0, "ok": 0, "err": 0, "total": 0}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def main():
    log("=== Récupération des documents à ré-extraire ===")
    resp = requests.get(f"{WORKER}/memory/reextract-pending", timeout=30)
    data = resp.json()
    docs = data.get('documents', [])
    total_pending = data.get('total', len(docs))

    if not docs:
        log(f"Aucun document à ré-extraire. Total en attente: {total_pending}")
        return 0

    log(f"{total_pending} documents à ré-extraire (premier batch: {len(docs)})")

    state = load_state()
    start_idx = 0
    for i, doc in enumerate(docs):
        if i < state.get("last_index", 0):
            continue
        doc_id = doc['id']
        title = doc.get('title', '?')[:60]
        log(f"[{i+1}/{len(docs)}] {doc_id} — {title}")

        try:
            r = requests.post(
                f"{WORKER}/memory/documents/{doc_id}/reextract",
                timeout=60
            )
            result = r.json()
            if result.get('success'):
                claims = result.get('claims_extracted', 0)
                log(f"  OK: {claims} claims extraits")
                state['ok'] += 1
            else:
                log(f"  ERR: {result.get('error', '?')[:100]}")
                state['err'] += 1
        except Exception as e:
            log(f"  ERR réseau: {e}")
            state['err'] += 1

        state['last_index'] = i + 1
        state['total'] += 1
        save_state(state)
        time.sleep(1)

    log(f"=== Terminé. OK: {state['ok']} ERR: {state['err']} ===")
    return 0

if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        log(f"CRASH: {type(e).__name__}: {e}")
        traceback.print_exc()
        sys.exit(2)