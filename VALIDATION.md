# Validation du contrat extractif - 13 novembre 2026

La version finale utilise des focus littéraux internes et publie les contextes
sources entiers. La revue porte sur leur pertinence et leur complétude pour la
question. Le texte du modèle, les notes libres et les requêtes de recherche ne
sont pas des faits cliniques publics. Les preuves sont dans `reports/jury/`.

| Contrôle | Résultat mesuré | Preuve |
|---|---|---|
| Suite hors réseau Python 3.11.15 | 271 tests réussis | `reports/jury/offline-tests.xml` |
| Edge sur l'HTML réellement embarqué | 87 contrôles réussis, génération interceptée | `reports/jury/browser-final.json` |
| Docker et HTTP | 14/14 contrôles réussis ; sources identiques, UID 10001, aucun .env embarqué | `reports/jury/docker-final.json` |
| Critique optimiste injecté | 14/14 phrases falsifiées non publiées | `reports/jury/adversarial-replay.json` |
| Nouvelle campagne HTTP avec fournisseur réel | 15/15 après correction du barème ; 4 refus ; 0 erreurs HTTP | `reports/jury/http-focus-final.json`, `http-focus-regraded.json` |
| Sources et contextes | 21 fichiers inchangés ; 556 textes d'index inchangés ; 456 contextes vérifiés indépendamment | `reports/jury/context-reassembly-proof.json`, tests |
| Appel réel dans le navigateur | Capture INR, ordinateur et mobile ; distincte des réponses interceptées | `reports/jury/preview-live.json`, `output/preview/` |

Modèle applicatif de cette campagne : `gpt-5.6-terra` ; embeddings :
`text-embedding-3-small`. Les modèles des agents d'audit sont distincts.
L'image, les empreintes, les paramètres, les durées et les réponses sont enregistrés.
Le score brut était 14/15 : le barème ne reconnaissait pas la parenthèse
de `(eGFR) below 30` dans une source pourtant correcte. La correction de cette
notation, testée indépendamment sans retirer de critère, a réévalué les mêmes
réponses sans nouvel appel. Le JSON brut reste immuable et chaque ancien score
est conservé dans le rapport réévalué.
L'image finale a été reconstruite pour embarquer ce barème corrigé. Les empreintes
confirment que code applicatif, corpus et interface sont identiques à la campagne
réelle ; seule `eval/grader.py` diffère. Les contrôles HTTP et la capture réelle
ont été rejoués sur le conteneur final.

## Échecs et historique conservés

Aucun échec dans cette série enregistrée.

L'ancienne prose avait une série à 6/7 et des retests séparés. Le jury a montré
qu'un score positif pouvait conserver un contresens comparatif. La première
version extractive a ensuite donné 11/15 : deux erreurs de
fixture (lisinopril et omeprazole absents) et deux vrais refus sur données présentes
(comparaison et acetaminophen). Les deux médicaments réellement manquants dans
la couverture, amoxicillin et ibuprofen, ont réussi séparément
2/2. Ces résultats ne sont ni effacés ni fusionnés avec
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
