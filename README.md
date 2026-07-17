# CPS — Mémoire Documentaire Épistémique

Système de mémoire documentaire pour le **Courant Politique Socialiste (CPS)**, basé sur une approche scientifique épistémique.

## Architecture

```
Cloudflare Workers (API + logique)
    ├── D1 (SQLite) — Stockage structuré : documents, chunks, claims, relations
    ├── Vectorize — Indexation sémantique (embeddings)
    └── KV — Cache inter-phases
```

### Pipeline d'ingestion

```
PDF (texte ou scanné)
    │
    ├── [texte] pdftotext → contenu brut
    └── [scanné] pdftoppm → Tesseract OCR (fra)
    │
    ▼
POST /memory/ingest → Worker
    ├── Chunking structurel (sections, ~3000 chars)
    ├── Stockage chunks complets en D1
    ├── Indexation Vectorize (embeddings BGE-small)
    └── Extraction IA des claims (Mistral small, async via waitUntil)
```

### Modèle épistémique

Chaque assertion (claim) extraite possède :

| Champ | Description |
|-------|-------------|
| `claim_type` | fait, analyse, position, engagement, critique, hypothèse, objectif |
| `epistemic_status` | proposed → confirmed / weakened / invalidated / uncertain / superseded / under_review |
| `confidence` | 0.0–1.0 selon le niveau de preuve |
| `stance` | pour, contre, nuance, neutre, critique, ambivalent |
| `temporal_start/end` | Validité temporelle de l'assertion |

### Relations entre claims

- **supports** : confirmation mutuelle
- **contradicts** : opposition factuelle
- **elaborates** : développement / précision
- **qualifies** : nuance
- **supersedes** : remplacement par version plus récente
- **contextualizes** : mise en contexte
- **evolves_from** : évolution progressive

## État de l'ingestion CPS

| Métrique | Valeur |
|----------|--------|
| Documents ingérés | 424 |
| Claims extraits | 7 546 |
| Texte PDF (pdftotext) | 250 OK / 33 erreurs / 163 scannés |
| OCR PDF (Tesseract fra) | 155 OK / 4 erreurs / 9 sautés |
| Période couverte | ~1983–1990 |
| Types de documents | bulletins (378), déclarations (32), éditoriaux (11), interventions (3) |

## API Endpoints

| Méthode | Route | Description |
|---------|-------|-------------|
| `GET` | `/memory/doc-stats` | Statistiques globales |
| `POST` | `/memory/ingest` | Ingérer un document (JSON) |
| `GET` | `/memory/documents` | Lister les documents |
| `GET` | `/memory/documents/:id` | Détail document + claims |
| `POST` | `/memory/documents/:id/reextract` | Ré-extraire les claims |
| `GET` | `/memory/reextract-pending` | Docs nécessitant ré-extraction |
| `GET` | `/memory/search?q=` | Recherche dans les claims |
| `PATCH` | `/memory/claims/:id/status` | Modifier statut épistémique |
| `DELETE` | `/memory/documents/:id` | Supprimer un document |

## Structure du projet

```
revue-presse/
├── src/
│   ├── index.js          # Routeur Cloudflare Worker
│   ├── docmemory.js      # Mémoire documentaire épistémique
│   ├── ai.js             # Providers IA (Mistral)
│   ├── pipeline.js       # Pipeline revue de presse
│   ├── memory.js         # Mémoire éditoriale KV
│   ├── fetcher.js        # Fetch RSS / News APIs
│   ├── extractor.js      # Extraction article HTML
│   ├── filter.js         # Dédup + scoring
│   ├── searcher.js       # Web search
│   ├── sources.js        # Sources RSS
│   ├── email.js          # Envoi email
│   ├── paywall.js        # Gestion paywalls
│   └── news-apis.js      # News APIs
├── scripts/
│   ├── ingest_one_pdf.py       # Ingestion PDF texte (resumable)
│   ├── ocr_ingest_one.py       # Ingestion PDF scanné via OCR (resumable)
│   └── reextract_pending.py    # Ré-extraction claims en erreur
├── schema.sql            # Schéma D1 complet
├── wrangler.toml         # Configuration Cloudflare
├── package.json          # Dépendances
└── setup-infrastructure.sh  # Setup D1 + Vectorize + KV
```

## Setup

```bash
# Prérequis
npm install
npx wrangler login

# Infrastructure Cloudflare
bash setup-infrastructure.sh

# Déploiement
npx wrangler deploy

# Ingestion PDF (texte)
python3 scripts/ingest_one_pdf.py

# Ingestion PDF (OCR, scannés)
python3 scripts/ocr_ingest_one.py

# Ré-extraction des claims en erreur
python3 scripts/reextract_pending.py
```

## Étapes post-ingestion (à faire)

1. **Déployer la version mise à jour** avec les endpoints de ré-extraction
2. **Lancer `reextract_pending.py`** pour traiter les ~20 documents en erreur
3. **Activer la cross-référence** : ingérer quelques documents avec `skip_crossref: false`
4. **Cycle épistémique** : utiliser les endpoints de mise à jour de statut pour confirmer/invalider les claims au fil des lectures