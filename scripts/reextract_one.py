#!/usr/bin/env python3
"""
Ré-extraction des claims — un document par exécution, resumable.
Conçu pour être appelé en boucle (comme ingest_one_pdf.py).

Usage:
  export WORKER_URL=https://your-worker.workers.dev
  python3 scripts/reextract_one.py
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
    return {"last_index": 0, "ok": 0, "err": 0, "total": 0, "done": False}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def main():
    state = load_state()
    if state.get("done"):
        log("=== Tous les documents ont été traités ===")
        return 0

    # Fetch pending docs
    resp = requests.get(f"{WORKER}/memory/reextract-pending", timeout=30)
    data = resp.json()
    docs = data.get('documents', [])
    total_pending = data.get('total', 0)

    if not docs or total_pending == 0:
        log("=== Aucun document à ré-extraire ===")
        state["done"] = True
        save_state(state)
        return 0

    i = state["last_index"]
    if i >= len(docs):
        # Ce batch est fini, vérifier s'il en reste
        if total_pending > 0:
            # Reset pour le prochain batch
            state["last_index"] = 0
            save_state(state)
            log(f"Batch épuisé ({len(docs)} traités), {total_pending} restent au total. Relancer.")
            return 1
        state["done"] = True
        save_state(state)
        log("=== Tous traités ===")
        return 0

    doc = docs[i]
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
    log(f"  Progression: OK:{state['ok']} ERR:{state['err']} RESTANT:{total_pending - state['ok']}")
    return 0

if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        log(f"CRASH: {type(e).__name__}: {e}")
        traceback.print_exc()
        sys.exit(2)