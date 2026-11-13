# Validation du livrable

Les preuves conservées ont été enregistrées le 13 novembre 2026, avant la
publication et le nettoyage du dépôt. Elles décrivent la version et les fichiers
mesurés à cette date. La CI du commit remis est un contrôle distinct :
https://github.com/IlyasFardaouix/Pharma-Research-Agent/actions

| Contrôle | Résultat enregistré | Preuve dans `reports/jury/` |
|---|---|---|
| Python 3.11.15, hors réseau | 271 tests réussis | `offline-tests.xml` |
| Edge, réponses de génération interceptées | 87 contrôles réussis | `browser-final.json` |
| Conteneur Docker et HTTP | 14/14 contrôles réussis | `docker-final.json` |
| Critique volontairement défaillant | 14/14 phrases falsifiées non publiées | `adversarial-replay.json` |
| Fournisseur réel, 15 scénarios | 14/15 brut ; 15/15 après correction documentée du barème ; 11 réponses et 4 refus attendus | `http-focus-final.json`, `http-focus-regraded.json` |
| Documents et contextes | 21 sources inchangées ; 556 fragments ; 456 contextes vérifiés | `corpus-integrity.json`, `context-reassembly-proof.json` |

## Score brut et correction conservés

L'unique échec de la dernière campagne brute était un faux négatif Q4 : le barème
ne reconnaissait pas la parenthèse de `(eGFR) below 30` dans la source exacte.
Les mêmes réponses ont été réévaluées sans nouvel appel au modèle. Le rapport brut
reste inchangé ; le second conserve chaque ancien score et les empreintes du
rapport source et du barème. Seule `eval/grader.py` différait entre l'image de cette
campagne et l'image finale enregistrée. Voir `reports/jury/scoring-correction.md`.

Le modèle applicatif de cette campagne était `gpt-5.6-terra`, avec embeddings
`text-embedding-3-small`. Ces noms ne désignent pas les agents d'aide au développement.
La latence médiane était de 9,016 s, le maximum de 28,547 s. Ce sont des mesures,
pas des délais garantis. Le démarrage utilisait un cache compatible : un calcul
complet d'embeddings à froid n'a pas été refait dans cette campagne.

Les essais antérieurs comprenaient des échecs réels et deux erreurs de fixtures.
Ils ne sont ni fusionnés avec la campagne finale ni présentés comme des succès.
Les rapports intermédiaires et audits détaillés ont été retirés du contenu courant
pour alléger le livrable ; ils restent consultables dans
[l'historique de développement](https://github.com/IlyasFardaouix/Pharma-Research-Agent/tree/5385352214a2dfbf65e5a5da7326482751318e67/reports).

## Reproduire les contrôles

Depuis le projet, avec les dépendances de développement installées :

```powershell
python -B -m pytest -p no:cacheprovider
python -B scripts/adversarial_replay.py
python -B scripts/regrade_http.py
```

Les deux scripts écrivent leurs nouveaux résultats dans `.cache/`, afin de ne pas
remplacer les preuves publiées. Avec le service et le navigateur Edge disponibles :

```powershell
uv tool run --from playwright python -B scripts/browser_smoke.py
python -B scripts/check_delivery.py --container pharma-demo
```

`--container` doit désigner le conteneur réellement lancé. La vérification Docker
compare ses fichiers avec le dossier courant ; une ancienne image doit être
reconstruite avant ce contrôle.

Pour une nouvelle campagne avec le fournisseur réel, clé et quotas requis :

```powershell
python scripts/http_acceptance.py --questions eval/questions.yaml eval/scenarios.yaml eval/jury_scenarios.yaml --output .cache/http-retest.json
```

Ce script vérifie les sources attendues avant les appels facturables. Les questions
et passages nécessaires sont transmis au fournisseur ; ne pas utiliser de données
de patients. L'évaluateur intégré est aussi disponible via `python -m app.eval`.

## Ce que ces tests ne garantissent pas

La fidélité littérale n'établit pas la pertinence, l'exhaustivité ni la vérité
clinique d'un extrait. `focus-relevance-limit.json` conserve un contre-exemple :
un critique trop optimiste peut approuver un contexte exact mais hors sujet.
Le critique utilise normalement le même modèle que l'agent ; leurs erreurs peuvent
être corrélées. Le corpus est figé, le registre produit partiel et les scénarios
connus des développeurs. Il n'existe aucune validation clinique ni garantie
générale d'absence d'hallucination.

Les contrôles navigateur utilisent des réponses interceptées. Les injections
hors réseau démontrent une protection dans les cas construits, pas une fréquence
d'attaque réelle. Un refus attendu valide un scénario négatif, pas une réponse
utile à une question positive. Les quatre questions publiques ont un barème de
couverture limité, expliqué dans `eval/README.md` ; les autres scénarios vérifient
surtout provenance, structure et statut.

Le dépôt est public. Les champs historiques `git_repository_present: false` et
`public_submission_attested: false` dans les anciennes preuves restent datés et
ne décrivent pas l'état actuel de GitHub. L'envoi du lien et du résumé au contact
recrutement reste distinct de la publication du code.
