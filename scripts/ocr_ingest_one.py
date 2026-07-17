#!/usr/bin/env python3
"""
OCR + Ingestion pour PDFs scannés CPS.
Convertit en images, OCR avec Tesseract (fra), puis envoie au Worker.
Resumable: sauve l'état après chaque PDF.

Prérequis:
  sudo apt install poppler-utils tesseract-ocr tesseract-ocr-fra
  pip install pytesseract Pillow requests

Usage:
  export WORKER_URL=https://your-worker.workers.dev
  export TESSDATA_PREFIX=/usr/share/tesseract-ocr/4.00/tessdata
  python3 scripts/ocr_ingest_one.py
"""
import json, time, sys, os, subprocess, requests, traceback
from datetime import datetime

os.environ.setdefault('TESSDATA_PREFIX', '/usr/share/tesseract-ocr/4.00/tessdata')

import pytesseract
from PIL import Image

WORKER = os.environ.get("WORKER_URL", "https://revue-presse.jeanneaj.workers.dev")
OCR_LIST = os.environ.get("OCR_LIST", "data/pdfs_to_ocr.json")
STATE_FILE = os.environ.get("OCR_STATE", "data/ocr_ingest_state.json")
LOG_FILE = os.environ.get("OCR_LOG", "data/ocr_ingest_log.txt")
TMP_DIR = os.environ.get("OCR_TMP", "data/ocr_tmp")
MAX_CHARS = int(os.environ.get("MAX_CHARS", "100000"))
MAX_PAGES = int(os.environ.get("MAX_PAGES", "8"))
DPI = int(os.environ.get("OCR_DPI", "150"))

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
    return {"last_index": 0, "ok": 0, "err": 0, "total": 0}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def ocr_pdf(pdf_path, max_pages=MAX_PAGES):
    """Convert PDF to images and OCR. Returns (text, page_count)."""
    info = subprocess.run(['pdfinfo', pdf_path], capture_output=True, text=True, timeout=15)
    pages_total = 1
    for line in info.stdout.split('\n'):
        if line.strip().startswith('Pages:'):
            try:
                pages_total = int(line.split(':')[1].strip())
            except:
                pass

    pages_to_ocr = min(pages_total, max_pages)

    img_dir = pdf_path + '_img'
    os.makedirs(img_dir, exist_ok=True)

    subprocess.run(
        ['pdftoppm', '-png', '-r', str(DPI), '-f', '1', '-l', str(pages_to_ocr),
         pdf_path, f'{img_dir}/page'],
        capture_output=True, timeout=120
    )

    img_files = sorted([f for f in os.listdir(img_dir) if f.endswith('.png')])

    all_text = []
    for img_file in img_files:
        img_path = os.path.join(img_dir, img_file)
        try:
            img = Image.open(img_path)
            text = pytesseract.image_to_string(img, lang='fra_fast')
            all_text.append(text.strip())
        except Exception as e:
            log(f"    OCR err {img_file}: {e}")
        finally:
            if os.path.exists(img_path):
                os.unlink(img_path)

    os.rmdir(img_dir)

    combined = '\n\n'.join(all_text)
    if pages_total > max_pages:
        combined += f'\n\n[... {pages_total - max_pages} pages non OCRisées ...]'

    return combined, pages_total

def main():
    ocr_docs = json.load(open(OCR_LIST))
    total = len(ocr_docs)
    state = load_state()
    i = state["last_index"]

    if i >= total:
        log(f"=== Tous les {total} PDFs ont été traités ===")
        return 0

    doc = ocr_docs[i]
    url = doc['url']
    date = doc['date']
    dtype = doc['type']
    filename = doc['filename']
    title = f"[{date}] {filename}"

    log(f"[{i+1}/{total}] {date} {filename[:50]}")

    # Download
    tmp_pdf = os.path.join(TMP_DIR, f"ocr_{i}.pdf")
    try:
        r = requests.get(url, timeout=120, headers={'User-Agent': 'CPS-Bot/1.0'})
        if r.status_code != 200:
            log(f"  ERR download HTTP {r.status_code}")
            state["err"] += 1
            state["last_index"] = i + 1
            state["total"] += 1
            save_state(state)
            return 1
        if len(r.content) < 5000:
            log(f"  ERR download trop petit: {len(r.content)} bytes")
            state["err"] += 1
            state["last_index"] = i + 1
            state["total"] += 1
            save_state(state)
            return 1
        with open(tmp_pdf, 'wb') as f:
            f.write(r.content)
    except Exception as e:
        log(f"  ERR download: {e}")
        state["err"] += 1
        state["last_index"] = i + 1
        state["total"] += 1
        save_state(state)
        return 1

    # OCR
    try:
        text, page_count = ocr_pdf(tmp_pdf)
        log(f"  OCR: {page_count} pages, {len(text)} chars")
    except Exception as e:
        log(f"  ERR OCR: {e}")
        state["err"] += 1
        state["last_index"] = i + 1
        state["total"] += 1
        save_state(state)
        return 1
    finally:
        if os.path.exists(tmp_pdf):
            os.unlink(tmp_pdf)

    if len(text) < 200:
        log(f"  ERR OCR texte trop court: {len(text)} chars")
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
            log(f"  OK: {chunks} chunks (OCR {page_count}p, claims en BG)")
            state["ok"] += 1
        else:
            log(f"  ERR ingest: {result.get('error', '?')[:80]}")
            state["err"] += 1
    except Exception as e:
        log(f"  ERR worker: {e}")
        state["err"] += 1

    state["last_index"] = i + 1
    state["total"] += 1
    save_state(state)

    log(f"  Progression: {i+1}/{total} (OK:{state['ok']} ERR:{state['err']})")
    return 0

if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        log(f"CRASH: {type(e).__name__}: {e}")
        traceback.print_exc()
        sys.exit(2)