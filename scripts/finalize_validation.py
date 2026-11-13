"""Consolidate measured final evidence and regenerate the delivery summaries."""
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import statistics
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
JURY = ROOT / "reports/jury"


def read(name):
    return json.loads((JURY / name).read_text(encoding="utf-8"))


def main():
    suites = ET.parse(JURY / "offline-tests.xml").getroot().findall("testsuite")
    tests = sum(int(s.get("tests", 0)) for s in suites)
    assert not any(int(s.get("failures", 0)) or int(s.get("errors", 0)) for s in suites)
    browser = read("browser-final.json")
    docker = read("docker-final.json")
    live = read("http-focus-regraded.json")
    initial = read("http-acceptance.json")
    replacements = read("http-coverage-replacements.json")
    replay = read("adversarial-replay.json")
    assert all(browser.values()) and all(docker["checks"].values())
    source_delta = sorted(name for name, digest in live["source_fingerprints"].items()
                          if docker["source_fingerprints"].get(name) != digest)
    assert set(source_delta) <= {"eval/grader.py"}, "Runtime sources changed after the provider campaign"
    result = {"date_utc": datetime.now(timezone.utc).isoformat(), "contract": "literal_focus_selection_and_full_source_excerpts",
        "python": platform.python_version(), "offline_tests": tests, "browser_checks": len(browser),
        "docker_checks": len(docker["checks"]), "image": docker["image"],
        "docker_summary": "Image reconstruite ; fichiers identiques au dossier ; UID 10001, sources non modifiables, cache accessible, aucun .env embarqué ; contrôles HTTP et documents liés à leur empreinte réussis.",
        "provider_summary": live["summary"], "model": live["model"], "embedding_model": live["embedding_model"],
        "final_raw_scoring_summary": live["original_summary"],
        "differences_between_provider_image_and_final_sources": source_delta,
        "latency_seconds": {"median": statistics.median(r["duration_seconds"] for r in live["results"]),
            "mean": statistics.mean(r["duration_seconds"] for r in live["results"]),
            "maximum": max(r["duration_seconds"] for r in live["results"])},
        "initial_extractive_campaign": initial["summary"], "initial_fixture_errors": ["j_lisinopril", "j_omeprazole"],
        "separate_coverage_replacements": replacements["summary"], "adversarial_replay": replay["summary"],
        "git_repository_present": (ROOT / ".git").exists(), "public_submission_attested": False,
        "limits": ["Finite known acceptance set; no blind external clinical validation", "Exact wording does not establish selection relevance or completeness", "Frozen corpus and partial product registry", "External provider, quotas and latency", "Public repository and external submission not attested"]}
    (JURY / "validation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    passed, total = live["summary"]["passed"], live["summary"]["total"]
    refusals, errors = live["summary"]["abstained"], live["summary"]["http_errors"]
    failures = "\n".join(f"- {r['id']} : {'; '.join(r['score']['failures'])}" for r in live["results"] if not r["score"]["ok"]) or "Aucun échec dans cette série enregistrée."
    (ROOT / "VALIDATION.md").write_text(f"""# Validation du contrat extractif - 13 novembre 2026

La version finale utilise des focus littéraux internes et publie les contextes
sources entiers. La revue porte sur leur pertinence et leur complétude pour la
question. Le texte du modèle, les notes libres et les requêtes de recherche ne
sont pas des faits cliniques publics. Les preuves sont dans `reports/jury/`.

| Contrôle | Résultat mesuré | Preuve |
|---|---|---|
| Suite hors réseau Python {result['python']} | {tests} tests réussis | `reports/jury/offline-tests.xml` |
| Edge sur l'HTML réellement embarqué | {len(browser)} contrôles réussis, génération interceptée | `reports/jury/browser-final.json` |
| Docker et HTTP | {len(docker['checks'])}/{len(docker['checks'])} contrôles réussis ; sources identiques, UID 10001, aucun .env embarqué | `reports/jury/docker-final.json` |
| Critique optimiste injecté | {replay['summary']['protected']}/{replay['summary']['total']} phrases falsifiées non publiées | `reports/jury/adversarial-replay.json` |
| Nouvelle campagne HTTP avec fournisseur réel | {passed}/{total} après correction du barème ; {refusals} refus ; {errors} erreurs HTTP | `reports/jury/http-focus-final.json`, `http-focus-regraded.json` |
| Sources et contextes | 21 fichiers inchangés ; 556 textes d'index inchangés ; 456 contextes vérifiés indépendamment | `reports/jury/context-reassembly-proof.json`, tests |
| Appel réel dans le navigateur | Capture INR, ordinateur et mobile ; distincte des réponses interceptées | `reports/jury/preview-live.json`, `output/preview/` |

Modèle applicatif de cette campagne : `{live['model']}` ; embeddings :
`{live['embedding_model']}`. Les modèles des agents d'audit sont distincts.
L'image, les empreintes, les paramètres, les durées et les réponses sont enregistrés.
Le score brut était {live['original_summary']['passed']}/{total} : le barème ne reconnaissait pas la parenthèse
de `(eGFR) below 30` dans une source pourtant correcte. La correction de cette
notation, testée indépendamment sans retirer de critère, a réévalué les mêmes
réponses sans nouvel appel. Le JSON brut reste immuable et chaque ancien score
est conservé dans le rapport réévalué.
L'image finale a été reconstruite pour embarquer ce barème corrigé. Les empreintes
confirment que code applicatif, corpus et interface sont identiques à la campagne
réelle ; seule `eval/grader.py` diffère. Les contrôles HTTP et la capture réelle
ont été rejoués sur le conteneur final.

## Échecs et historique conservés

{failures}

L'ancienne prose avait une série à 6/7 et des retests séparés. Le jury a montré
qu'un score positif pouvait conserver un contresens comparatif. La première
version extractive a ensuite donné {initial['summary']['passed']}/{initial['summary']['total']} : deux erreurs de
fixture (lisinopril et omeprazole absents) et deux vrais refus sur données présentes
(comparaison et acetaminophen). Les deux médicaments réellement manquants dans
la couverture, amoxicillin et ibuprofen, ont réussi séparément
{replacements['summary']['passed']}/{replacements['summary']['total']}. Ces résultats ne sont ni effacés ni fusionnés avec
la nouvelle campagne. Voir `fixture-correction.md` et `validation-before-jury.md`.

Un diagnostic ultérieur de comparaison a réussi après révision, sans transformer
le refus original en succès. Une vérification hors réseau a démontré que l'ancienne
garde de plusieurs phrases rejetait des extraits pourtant littéraux. Le protocole
interne a donc été aligné : un focus exact de 12 à 1 800 caractères dans un seul
contexte ; le critique examine le contexte entier réellement publié. Une quote
partielle n'autorise jamais à publier un contexte incomplet ou hors sujet.

## Portée des mesures

Les tests hors réseau couvrent contrats, graphe, outils, produits, alias, cache,
contextes, API, concurrence, délais, annulation et injections. Le navigateur teste
les états, liens, focus, limites Unicode, colonnes et erreurs avec des réponses
interceptées. Ce n'est pas un test médical du modèle.

Le replay utilise volontairement un critique défaillant, avec `verdict=entailed`,
IDs réels et citations authentiques. Il établit l'absence des phrases falsifiées
dans ces sorties, pas une fréquence d'attaque réelle ni une garantie universelle.

Le nouveau barème relit les fichiers, recalcule SHA/offsets, contrôle contexte,
identités et texte hors extraits, puis recalcule les nombres. Les quatre questions
publiques ont des critères de couverture figés dans `eval/README.md`. Les autres
scénarios testent surtout sources, structure et statut ; leur complétude exige
aussi une lecture. Un refus attendu est un succès de scénario négatif, pas une
réponse utile à une question positive.

La sélection, la pertinence, les renvois entre rubriques et la complétude restent
faillibles. Le corpus est figé, le registre produit partiel et le jeu connu des
développeurs. Les deux modèles peuvent avoir des erreurs corrélées. Il n'existe
aucune validation clinique ni garantie générale d'absence d'hallucination.

Les anciens 429 embeddings, délais et refus sont conservés. Cette campagne teste
un démarrage avec cache compatible ; elle ne refait pas un calcul complet à froid.
Le scan historique de 54 dépendances sans avis connu n'est pas un nouveau scan
et ne couvre pas le système complet de l'image. La CI distante n'est pas attestée.

## Reproduire les contrôles

Exécuter ces commandes dans une copie isolée du projet. Le replay remplace son
rapport et la capture remplace les aperçus, même avec un autre chemin `--report`.
Conserver les preuves originales avant tout nouvel essai.

```powershell
.venv311/Scripts/python.exe -B -m pytest -p no:cacheprovider
.venv311/Scripts/python.exe -B scripts/adversarial_replay.py
uv tool run --from playwright python scripts/browser_smoke.py --report .cache/browser-retest.json
.venv311/Scripts/python.exe scripts/check_delivery.py --output .cache/docker-retest.json
# Fournisseur réel, accès et quotas nécessaires :
.venv311/Scripts/python.exe scripts/http_acceptance.py --questions eval/questions.yaml eval/scenarios.yaml eval/jury_scenarios.yaml --output .cache/http-retest.json
uv tool run --from playwright python scripts/capture_preview.py --report .cache/preview-retest.json
```

Le script HTTP vérifie les noms de sources attendues avant tout appel facturable.
Les questions et passages partent au fournisseur : ne pas saisir de données de
patients. La démo reste locale ; authentification, TLS, quotas globaux et exploitation
doivent être conçus avant une exposition Internet.

Le dépôt public et la remise externe ne sont pas attestés. Le ZIP et la démo ne
remplacent pas le lien public et le commit demandés par le sujet.
""", encoding="utf-8")
    (ROOT / "LIVRAISON.md").write_text("""# Produit local et remise

Le produit est une démonstration de recherche documentaire agentique, avec
contextes sources littéraux, citations, rapprochement textuel et calcul numérique
conditionnel. La pertinence et la complétude restent faillibles ; aucun conseil
médical ou garantie générale d'absence d'erreur n'est fourni.

1. Ouvrir http://127.0.0.1:8000 et attendre l'état prêt.
2. Demander « Define INR using only the provided local glossary. ».
3. Lire l'extrait, activer son lien puis ouvrir le document complet lié à son SHA.
4. Lire DEMO.md pour une comparaison prudente et la présentation de dix minutes.

La version courante est servie par `pharma-final`, image `pharma-agent:final`,
liée uniquement à localhost. Les autres projets Docker n'ont pas été modifiés.

| Élément | Chemin |
|---|---|
| Archive de sources et preuves | `dist/assignment-pharma-final.zip` |
| Rapport français, architecture et jury | `output/pdf/Rapport_Projet_Pharma.pdf` |
| Guide usager et démonstration | `DEMO.md` |
| Architecture et justification | `ARCHITECTURE.md` |
| Mesures et limites | `VALIDATION.md`, `reports/jury/validation.json` |
| Aperçus réels | `output/preview/desktop.png`, `output/preview/mobile.png` |
| Audit initial, campagnes et relecture | `reports/jury/` |
| Empreintes du paquet | `MANIFEST_SHA256.json` dans l'archive |

L'archive inclut code, 21 documents, tests, verrous, configuration IA, CI,
documentation, rapport et captures. Elle exclut secrets, environnements, caches,
temporaires et énoncé confidentiel. Le générateur vérifie la clé courante et les
empreintes ; cela ne constitue pas un détecteur exhaustif de tout secret.

```powershell
# Dépendances documentaires optionnelles, hors runtime :
uv tool run --from reportlab --with pypdf python scripts/build_report.py
.venv311/Scripts/python.exe scripts/package_delivery.py
```

Les preuves doivent être à jour avant de régénérer le rapport. Les campagnes
initiales et retests restent distincts. Les fichiers du paquet et le corpus sont
contrôlés par empreintes ; toute modification exige une vérification appropriée.

Le dépôt public de remise est
https://github.com/IlyasFardaouix/Pharma-Research-Agent ; voir `docs/PUBLICATION.md`.
Les rapports de validation datés précèdent cette publication et conservent leur
état historique. Une publication Git ne réalise pas l'envoi du lien et du résumé
au contact recrutement ; aucun envoi à un tiers n'a été effectué ici.
""", encoding="utf-8")
    print(json.dumps({"offline_tests": tests, "browser_checks": len(browser), "real_http": live["summary"]}))


if __name__ == "__main__":
    main()
