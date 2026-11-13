# Plan — Agent de recherche pharma (GenAI Bootcamp Assignment)

## Context

Livrable de l'assignment Syntax (deadline **13 nov. 2026, 23:59 Casablanca**) : un **agent de
recherche agentique** en Python qui répond à des questions composées sur un corpus pharma local
(10 médicaments × 2 sources DailyMed/MedlinePlus + GLOSSARY, déjà fournis dans `corpus/`).

Le pipeline imposé : **Plan → Retrieve (similarité in-memory) → Tools (≥2, choisis par l'agent) →
Critic (grounding) → Answer (cité + disclaimer)**. Interface imposée : Docker à la racine,
`GET /health`, `POST /ask`, frontend minimal. LLM via proxy **LiteLLM** OpenAI-compatible (vars
d'env `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_EMBEDDING_MODEL`).

Projet **greenfield** : actuellement seulement `corpus/`, `.env`, `assignment-pharma.pdf`. Rien à
réutiliser → on construit tout. Évaluation : compétence technique, innovation, résolution de problème.

**Angle différenciant** : retrieval **hybride** (sémantique + structuré section-aware exploitant la
numérotation DailyMed), **critic auto-correctif** (peut relancer la recherche), et **trace
transparente** (plan + outils + grounding) renvoyée à l'API et affichée dans l'UI.

## Stack (épinglée dans `pyproject.toml`, Python 3.11)

- `langgraph` + `langchain-core` — machine à états de l'agent
- `langchain-openai` — `ChatOpenAI` (LLM, tool-binding) **et** `OpenAIEmbeddings`, tous deux lisent
  `OPENAI_BASE_URL`/`OPENAI_API_KEY` → compatible proxy LiteLLM sans code spécifique
- `fastapi` + `uvicorn[standard]` — API + service du frontend
- `pydantic` + `pydantic-settings` — schémas I/O + config env
- `numpy` — cosine in-memory (pas de vector DB → conteneur léger et auto-suffisant)
- `python-dotenv` — confort dev local
- `pytest` + `httpx` — tests

## Arborescence à créer

```
app/
  main.py          # FastAPI: lifespan (build index 1x), GET /health, POST /ask, sert frontend
  config.py        # pydantic-settings Settings (lit l'env, défauts raisonnables)
  models.py        # AskRequest, AnswerResponse, Citation, GroundingReport, Passage
  rag/
    loader.py      # parse corpus/*.md -> chunks header-aware + métadonnées
    embeddings.py  # OpenAIEmbeddings + cache disque (.npz, clé = hash(model+corpus))
    index.py       # InMemoryIndex: matrice normalisée, search(query,k,filter) cosine NumPy
  tools/
    search.py      # search_corpus(query,k,drug?)
    sections.py    # get_drug_section(drug, section)  + list_drugs()
    glossary.py    # lookup_glossary(term)
  agent/
    state.py       # AgentState (TypedDict)
    prompts.py     # prompts plan / agent / critic / answer
    nodes.py       # plan_node, agent_node, tools_node, critic_node, finalize_node
    graph.py       # StateGraph assemblé + compile()
frontend/
  index.html       # UI vanilla (question -> POST /ask -> réponse + citations + trace dépliable)
eval/
  questions.yaml   # 4 questions publiques + fichiers sources attendus
tests/
  test_loader.py test_sections.py test_index.py test_api.py
.claude/
  CLAUDE.md        # config IA du repo (policy "push your AI config")
Dockerfile
pyproject.toml
.env.example
README.md
.dockerignore / .gitignore
```

## Design détaillé

### RAG (in-memory, construit au démarrage, caché sur disque)
- **`loader.load_corpus(dir)`** : découpe chaque `.md` sur les en-têtes `##`/`###`. Chaque chunk =
  `{id, text, drug, source, section_title, section_num?}`. `drug`/`source` déduits du nom de fichier
  (`dailymed-warfarin.md` → drug=`warfarin`, source=`dailymed`). GLOSSARY = source `glossary`.
  Gère les deux formats (DailyMed numéroté + MedlinePlus narratif).
- **`embeddings`** : batch sur `OPENAI_EMBEDDING_MODEL`. Cache `.npz` clé = `sha256(model+contenu
  corpus)` → restart quasi instantané, pas de ré-embedding. Pas d'appel réseau au build Docker
  (clé injectée seulement au `run`) → index construit au **startup** du conteneur.
- **`index.InMemoryIndex.search(query, k, filter=None)`** : cosine NumPy sur matrice normalisée,
  filtre métadonnée optionnel (drug/section/source).

### Outils (enregistrés LangChain, **bindés au LLM → choix par l'agent**, ≥2 satisfait avec 4)
| Outil | Signature | Rôle |
|-------|-----------|------|
| `search_corpus` | `(query, k=5, drug=None)` | recherche sémantique top-k (questions ouvertes) |
| `get_drug_section` | `(drug, section)` | **texte exact** d'une section DailyMed (mappe `contraindications/interactions/dosage/warnings/indications/mechanism` → `## N …`) — haute précision pour Q1/Q2/Q3/Q4 |
| `lookup_glossary` | `(term)` | définition depuis GLOSSARY.md (INR, eGFR…) |
| `list_drugs` | `()` | inventaire corpus (cadrage / désambiguïsation) |

### Agent LangGraph (`StateGraph`)
`AgentState` : `question, plan[], messages[], retrieved[], draft_answer, grounding, revision_count,
tool_trace[], final`.

Nœuds et flux :
```
START → plan_node → agent_node ─(tool_calls?)─► tools_node ─► agent_node
                        │ (sinon: draft prêt)
                        ▼
                    critic_node ─(needs_revision & count<MAX)─► agent_node
                        │ (grounded / count==MAX)
                        ▼
                    finalize_node → END
```
- **plan_node** : LLM décompose en sous-questions (1 seule si lookup simple).
- **agent_node** : `ChatOpenAI` avec outils bindés ; boucle ReAct, choisit les outils, puis rédige
  un brouillon quand l'évidence suffit.
- **tools_node** : exécute les tool-calls, accumule `retrieved` + `tool_trace`.
- **critic_node** : vérifie que chaque affirmation du brouillon est **ancrée** dans `retrieved` ;
  renvoie `verdict` + flags (non-supporté / ambigu cliniquement). Peut déclencher une révision
  (bornée `MAX_REVISIONS=2` pour éviter boucle infinie).
- **finalize_node** : réponse **citée** (fichiers sources + sections) + **disclaimer « not medical
  advice »** + attache `plan`/`tool_trace`/`grounding`.

### API (FastAPI)
- `GET /health` → `{"status":"ok"}` 200 (503 tant que l'index n'est pas prêt).
- `POST /ask` `{question}` → `AnswerResponse {answer, citations[], disclaimer, plan, tool_trace,
  grounding}` 200.
- `/` sert `frontend/index.html`. Build/chargement de l'index via **lifespan** (une fois).

### Frontend (`index.html`, vanilla, zéro build)
Textarea question → `fetch POST /ask` → affiche la réponse, les **citations en chips**, et un bloc
**« Agent trace »** dépliable (plan + outils appelés + verdict grounding). CSS propre, lisible.

### Dockerfile
`python:3.11-slim` → install deps → copie `app/ corpus/ frontend/` →
`EXPOSE 8000` → `CMD uvicorn app.main:app --host 0.0.0.0 --port 8000`. Corpus **baked-in** →
conteneur auto-suffisant ; index construit au premier démarrage.

### Eval & tests
- `eval/questions.yaml` : 4 questions publiques + `expected_sources`. `python -m app.eval` imprime
  une scorecard (les bons fichiers sont-ils cités ?). Gated sur présence de clé API.
- Tests **sans LLM** (déterministes, CI-safe) : `test_loader` (métadonnées), `test_sections`
  (`get_drug_section("metformin","contraindications")` contient « eGFR below 30 »), `test_index`
  (cosine, embeddings mockés), `test_api` (/health 200, /ask 200 avec agent mocké).

### `.claude/` (policy « push your AI config »)
`CLAUDE.md` du repo décrivant projet + conventions + config IA utilisée (ce plan).

## Ordre d'implémentation
1. `pyproject.toml`, `config.py`, `models.py`, `.env.example`
2. RAG : `loader` → `embeddings` (+cache) → `index` ; tests loader/index/sections
3. Outils (`search`, `sections`, `glossary`)
4. Agent LangGraph : `state` → `prompts` → `nodes` → `graph`
5. API `main.py` + `frontend/index.html`
6. `Dockerfile`, `.dockerignore`, `eval/`, `README.md`, `.claude/CLAUDE.md`
7. `git init` (dépôt pas encore initialisé) — **push GitLab laissé à l'utilisateur** (pas de commit sans accord)

## Vérification (bout-en-bout)
- **Unit** : `pytest` → vert (sans clé API).
- **Local** : `uvicorn app.main:app` → `curl /health` = 200 ; `POST /ask` sur les **4 questions** →
  vérifier que les citations incluent les fichiers attendus (warfarin ; warfarin+apixaban ;
  warfarin+sertraline + monitoring INR ; metformin eGFR<30) et que le disclaimer est présent.
- **Docker** : `docker build -t agent . && docker run -p 8000:8000 --env-file .env agent` → mêmes
  checks ; conteneur démarre seul.
- **UI** : ouvrir `http://localhost:8000` → poser une question → réponse + citations + trace.
- **Eval** : `python -m app.eval` → scorecard citations OK sur les 4 questions.

## Hors-scope de ce plan (à proposer après)
Présentation 10 min (slides/walkthrough) et push GitLab final.
