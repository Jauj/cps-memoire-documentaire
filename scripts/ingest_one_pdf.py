#!/usr/bin/env python3
"""
Ingestion PDF texte CPS — un PDF par exécution, resumable.
Usage:
  export WORKER_URL=https://your-worker.workers.dev
  export CF_ACCOUNT_ID=your_account_id
  export CF_API_TOKEN=your_api_token
  export CF_DATABASE_ID=your_database_id
  python3 scripts/ingest_one_pdf.py
"""
import json, time, sys, os, subprocess, requests, traceback
from datetime import datetime

WORKER = os.environ.get("WORKER_URL", "https://revue-presse.jeanneaj.workers.dev")
PDF_FILE = os.environ.get("PDF_LIST", "data/pdfs_to_ingest.json")
STATE_FILE = os.environ.get("INGEST_STATE", "data/ingest_state.json")
LOG_FILE = os.environ.get("INGEST_LOG", "data/ingest_log.txt")
TMP_DIR = os.environ.get("INGEST_TMP", "data/pdf_tmp")
MAX_CHARS = int(os.environ.get("MAX_CHARS", "100000"))
CF_ACCOUNT = os.environ.get("CF_ACCOUNT_ID", "")
CF_DB = os.environ.get("CF_DATABASE_ID", "")
CF_TOKEN = os.environ.get("CF_API_TOKEN", "")

os.makedirs(os.path.dirname(STATE_FILE) or "data", exist_ok=True)
os.makedirs(TMP_DIR, exist_ok=True)

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
    return {"last_index": 0, "ok": 0, "err": 0, "total": 0, "skipped": 0}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def get_ingested_urls():
    """Get URLs already in D1 via Cloudflare API."""
    if not CF_TOKEN or not CF_ACCOUNT or not CF_DB:
        return set()
    try:
        r = requests.post(
            f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT}/d1/database/{CF_DB}/query",
            headers={"Authorization": f"Bearer {CF_TOKEN}", "Content-Type": "application/json"},
            json={"sql": "SELECT source_url FROM documents WHERE source_url IS NOT NULL GROUP BY source_url"},
            timeout=15
        )
        data = r.json()
        if data.get('success'):
            return set(row['source_url'] for row in data['result'][0]['results'])
    except:
        pass
    return set()

def main():
    pdfs = json.load(open(PDF_FILE))
    total = len(pdfs)
    state = load_state()
    i = state["last_index"]

    # Skip already ingested
    ingested = get_ingested_urls()
    while i < total and pdfs[i]['url'] in ingested:
        state["skipped"] = state.get("skipped", 0) + 1
        i += 1

    if i >= total:
        log(f"=== TERMINÉ: {state.get('skipped',0)} skip + {state['ok']} OK + {state['err']} ERR = {total} ===")
        return 0

    doc = pdfs[i]
    url, date, dtype, filename = doc['url'], doc['date'], doc['type'], doc['filename']
    title = f"[{date}] {filename}"

    log(f"[{i+1}/{total}] {date} {filename[:45]}")

    # Download
    tmp_path = os.path.join(TMP_DIR, f"doc_{i}.pdf")
    try:
        r = requests.get(url, timeout=30, headers={'User-Agent': 'Mozilla/5.0 (compatible; CPS-Bot/1.0)'})
        if r.status_code != 200:
            log(f"  ERR download HTTP {r.status_code}")
            state["err"] += 1
            state["last_index"] = i + 1
            state["total"] += 1
            save_state(state)
            return 1
        with open(tmp_path, 'wb') as f:
            f.write(r.content)
    except Exception as e:
        log(f"  ERR download: {e}")
        state["err"] += 1
        state["last_index"] = i + 1
        state["total"] += 1
        save_state(state)
        return 1

    # Extract text
    try:
        result = subprocess.run(['pdftotext', '-layout', tmp_path, '-'],
                                capture_output=True, text=True, timeout=30)
        text = result.stdout.strip()
    except:
        text = ""
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    if len(text) < 100:
        log(f"  ERR extraction: {len(text)} chars (probablement scanné → utiliser ocr_ingest_one.py)")
        state["err"] += 1
        state["last_index"] = i + 1
        state["total"] += 1
        save_state(state)
        return 1

    content = text

    # Ingest (mode asynchrone)
    try:
        r = requests.post(f"{WORKER}/memory/ingest", json={
            "title": title, "content": content, "doc_type": dtype,
            "date": date, "url": url, "org_name": "CPS",
            "skip_crossref": True, "async_claims": True
        }, timeout=30)
        result = r.json()
        if result.get('success'):
            chunks = result.get('chunk_count', 0)
            words = result.get('word_count', 0)
            log(f"  OK: {words} mots, {chunks} chunks (claims en BG)")
            state["ok"] += 1
        else:
            log(f"  ERR: {result.get('error', '?')[:80]}")
            state["err"] += 1
    except Exception as e:
        log(f"  ERR worker: {e}")
        state["err"] += 1

    state["last_index"] = i + 1
    state["total"] += 1
    save_state(state)

    log(f"  Progression: {state['last_index']+state.get('skipped',0)}/{total} (OK:{state['ok']} ERR:{state['err']} Skip:{state.get('skipped',0)})")
    return 0

if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        log(f"CRASH: {type(e).__name__}: {e}")
        traceback.print_exc()
        sys.exit(2)