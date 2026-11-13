# Bilan de la version livrée - 13 novembre 2026

## Résultats

| Contrôle | Résultat observé | Preuve |
|---|---|---|
| Suite hors réseau sous Python 3.11.15 | **144 tests réussis** | `tests/`, `reports/validation.json` |
| Copie propre de l'archive extraite | **144 tests réussis**, sans `.env`, en 25,37 s | `reports/package-smoke.json` |
| Navigateur Edge sur l'image Docker structurée | **18 contrôles réussis** ; appels IA interceptés dans ce script | `scripts/browser_smoke.py`, `reports/browser-final.json` |
| Appel réel par l'interface | HTTP 200, une affirmation et un passage exact pour INR ; captures ordinateur/mobile sans débordement | `reports/preview-live.json`, `output/preview/` |
| Dernière série complète sur le modèle configuré | **6/7 réussis**, sans erreur agent ; 3 abstentions dont 2 attendues | `reports/acceptance-final.json` |
| Retest ciblé de la comparaison | **1/1 réussi**, en 22,875 s ; index préalablement calculé, génération et critique réels | `reports/comparison-retest.json` |
| Comparaison par l'API Docker | HTTP 200 en **96,641 s**, réponse citée ; contrôle réussi après correction d'un faux négatif du barème, score initial conservé | `reports/comparison-http-final.json` |
| Corpus d'origine | **21 fichiers inchangés** par comparaison binaire avec la référence ; **556 passages** | `reports/validation.json`, tests de provenance |
| Dépendances Python runtime | **54 paquets examinés, aucune vulnérabilité connue signalée** par pip-audit à cet essai | `reports/dependency-audit.json` |
| Docker | UID 10001, code/corpus identiques aux sources, sources non modifiables par cet utilisateur, aucun `.env` embarqué ; état sain et cache portable vérifié | `Dockerfile`, `reports/docker-final.json`, `reports/validation.json` |

La série complète et le retest sont deux essais distincts. **Le résultat de la série complète reste 6/7, pas 7/7.** Les sept scénarios ont chacun réussi dans les essais enregistrés, mais la comparaison a aussi donné des abstentions. Le livrable conserve cette réserve de stabilité.

La série complète enregistrée utilise `gpt-5.6-terra` et `text-embedding-3-small`. Les agents d'assistance au développement et le modèle de l'application sont des éléments distincts. Un autre environnement peut injecter d'autres modèles via `.env` et doit être retesté.

## Scénarios réellement exécutés

| Scénario | Dernière série complète | Retest séparé |
|---|---|---|
| Contre-indications de warfarin | Réponse vérifiée par le barème ciblé | — |
| Comparaison warfarin/apixaban | Abstention, alors qu'une réponse était attendue | Réponse et contrôles réussis |
| Risque documentaire warfarin/sertraline et surveillance | Réponse vérifiée | — |
| Question metformin et eGFR chiffré | Réponse vérifiée | — |
| Définition INR depuis le glossaire | Réponse vérifiée | Appel réel HTTP/navigateur également réussi |
| Semaglutide absent du corpus | Abstention attendue | — |
| Inhalateur Ventolin absent des formulations fournies | Abstention attendue | — |

Les vérifications génériques contrôlent les statuts, les IDs, les associations affirmation-passage, les extraits, les citations littérales, les offsets Unicode et les empreintes des fichiers. Les quatre questions publiques ajoutent des motifs factuels limités. **Ces contrôles ne certifient pas l'implication médicale de toute paraphrase ni sa sécurité clinique.**

## Incidents conservés dans le bilan

- Première série structurée : 5/7, avec un timeout fournisseur et un identifiant du glossaire non canonique. L'identifiant a été corrigé et couvert par un test.
- L'évaluation séparait une affirmation en plusieurs phrases et perdait sa citation finale : correction de la segmentation, avec maintien des tests de négation et de mauvaises sources.
- Une garde ne reconnaissait pas « high thromboembolic risk » : formulation reconnue et retour de révision clarifié. Des abstentions conservatrices restent possibles.
- L'initialisation a rencontré des **429 fournisseur sur les embeddings**, en CLI et dans le premier démarrage Docker. Le service est passé en mode dégradé après trois essais bornés. Après redémarrage, le calcul de l'index complet a réussi. Les erreurs CLI de démarrage sont maintenant masquées et enregistrées sans traceback fournisseur.
- La comparaison ciblée a réussi avec un index existant après les abstentions de la série. Ce succès n'efface pas les faux refus observés.
- L'ordre des fichiers variait entre `WindowsPath` et `PosixPath`. Le tri explicite par nom rend désormais l'ordre des passages et le cache portables ; un test couvre cette régression.
- Le dernier appel HTTP a révélé un faux négatif du barème sur « no contraindication unique ». La négation des conditions partagées et l'absence de condition unique sont maintenant distinguées, avec un test qui rejette toujours une négation réelle. La même réponse HTTP a été réévaluée sans nouvel appel modèle ; son ancien score reste enregistré.

Les anciens essais sont conservés sous `reports/initial-structured-eval.json`, `reports/acceptance-before-caveat-fix.json` et `reports/early-retest.json`. `AUDIT_FINAL.md` est un document **historique**, avec les chiffres de l'ancienne architecture.

## Reproduire les contrôles

```powershell
.venv311/Scripts/python.exe -B -m pytest -p no:cacheprovider
# Serveur déjà démarré, Edge installé :
uv tool run --from playwright python -B scripts/browser_smoke.py --report reports/browser-final.json
# Appels réels facturables par le fournisseur, configuration requise :
.venv311/Scripts/python.exe -B -m app.eval --output .cache/public-eval.json
.venv311/Scripts/python.exe -B -m app.eval --questions eval/scenarios.yaml --output .cache/scenario-eval.json
uv tool run --from playwright python scripts/capture_preview.py
# Scan d'avis de sécurité Python, nécessite le réseau :
uv tool run --from pip-audit pip-audit -r requirements.txt --disable-pip --no-deps --format json
```

Pour réunir les deux fichiers de scénarios avant un seul appel à l'évaluateur, concaténer leurs listes `questions` dans un YAML temporaire. Les résultats fournis ont été obtenus avec cette liste combinée de sept questions. Le retest ciblé a réutilisé la même matrice normalisée déjà construite, puis exécuté le même agent et le même évaluateur sur la comparaison.

## Limites du bilan

Cette vérification couvre le dossier, les contrats, les cas adversariaux codés, l'intégration Docker, le navigateur et des appels réels bornés. Elle ne prétend pas explorer toutes les failles possibles. Il reste notamment : erreurs corrélées du générateur et du critique, couverture limitée du jeu d'essais, corpus figé, quota et latence fournisseur, annulation coopérative d'un thread, absence d'authentification et de quota par utilisateur pour une exposition publique. Le scan Python ne couvre pas toute l'image système ni les vulnérabilités inconnues.

La CI est fournie mais aucune exécution distante ni publication de dépôt n'a été déclenchée ici. Le projet est préparé pour une démonstration locale ; une utilisation clinique ou une exposition publique demande une validation et une exploitation supplémentaires.
