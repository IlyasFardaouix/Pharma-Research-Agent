# Vérification des corrections UX

13 novembre 2026. Modifications de production limitées à `frontend/index.html` et `scripts/browser_smoke.py`, sur demande du parent. Aucun serveur ou conteneur n'a été touché. L'HTML local modifié a été servi uniquement par interception Playwright de la page racine ; toutes les requêtes `/ask` fonctionnelles ont été interceptées. Le seul POST vers l'API réelle est le test de validation d'une question vide (422, avant tout fournisseur).

Commande :

```powershell
uv tool run --from playwright python -B scripts/browser_smoke.py --frontend frontend/index.html --report .cache/jury-ux-fixed-smoke.json
```

**Résultat : 49 contrôles réussis, code de sortie 0.** À rejouer sans `--frontend` après reconstruction/déploiement du Docker final pour prouver que l'HTML réellement livré est le même.

| Constat initial | Correction et vérification |
|---|---|
| UX-01, question/réponse désynchronisées | Question soumise mémorisée et affichée dans le résultat, même si le brouillon change pendant l'appel ; exemples désactivés en attente ; test de modification pendant une réponse différée réussi. |
| UX-02, instructions internes exposées | Warnings remplacés par une notice publique fixe ; notes/flags de critique jamais recopiés ; plan et détails textuels des outils supprimés sur refus, noms d'outils conservés ; chaîne sentinelle interne absente du résultat. |
| UX-03, lien de preuve inopérant | Le lien ouvre le passage exact, déplace le focus et met à jour l'ancre ; assertion sur visibilité réelle du blockquote et focus sur la source. |
| UX-04, longueur inconnue et rejet tardif | Limite locale explicite de 4000 points de code, compteur et erreur accessibles ; texte intégral préservé ; aucun POST pour 4001 caractères ASCII ou Unicode ; 4000 caractères hors BMP sont acceptés. Le maxlength natif UTF-16 est volontairement évité pour ne pas tronquer une réserve médicale dans un collage. |
| UX-05, recherche manuelle de la preuve | Citations littérales par affirmation, sous disclosure ; seules celles présentes dans l'extrait et déclarées pour cette affirmation sont affichées ; une citation inventée dans le fixture n'est pas rendue. |
| UX-06, structure et focus | Main/section, H2 résultat et H3 cohérents, focus du résultat après réponse/erreur et de la source après activation ; région de statut courte. Une vérification manuelle avec lecteur d'écran reste à effectuer. |
| UX-07, attente/erreurs | Temps écoulé et limite visibles, annulation rappelée ; annonce lecteur d'écran au début sans répétition chaque seconde ; titre d'erreur distinct, refus explicite ; cas 422/429/503/504, annulation et transitions démarrage → prêt testés. |
| UX-08, périmètre documentaire | Reste à améliorer : panneau des médicaments/formulations couverts et liens officiels. Aucun nouveau service/API n'a été inventé pour cet audit UX limité. |
| UX-09, confort/contraste | Exemples courts explicites sans troncature, question complète conservée à la sélection ; bordure du champ renforcée ; chips de 40 px minimum ; absence de débordement vérifiée aux cinq largeurs. |

Le résultat refuse aussi d'afficher une réponse déclarée answered dont le statut de revue n'est pas approuvé. Le texte visible rappelle que la revue automatique ne constitue pas une validation clinique. L'interface n'affirme pas une garantie générale de zéro hallucination.

## Contrôles ajoutés ou renforcés

- Les 18 surfaces et scénarios de smoke initiaux restent couverts, avec des fixtures du nouveau contrat strict.
- Source effectivement ouverte et focalisée ; citation exacte affichée ; citation inventée filtrée.
- Défense d'affichage : réponse non approuvée non publiée, notes/flags/brouillons de refus absents, avertissement public et état d'abstention explicites.
- Absence de débordement à 320, 360, 390, 768 et 1440 px ; titres structurés.
- Même page passant de dégradé à démarrage puis prêt.
- Limite locale ASCII/Unicode, conservation du texte, aria-describedby/aria-invalid, aucun POST inutile.
- Raccourci Ctrl+Enter valide, double clic, annulation, focus après réponse et erreurs.
- Requête différée, changement de question pendant l'attente, association à la question d'origine, chips verrouillés puis rétablis.
- Retour sur l'attente et annonces accessibles ; erreurs 422, 429, 503 et 504.
- Contrôles HTTP locaux de santé, validation vide, absence de publication du corpus et traversée vers .env conservés.

Les captures corrigées ont été ouvertes et vérifiées visuellement en thème clair et sombre : `after-mobile-start.png`, `after-mobile-answer.png`, `after-mobile-abstention.png`, `after-desktop-answer.png`, `after-dark-answer.png`. Les preuves initiales ne sont pas écrasées.

Les nouveaux résultats prouvent le comportement de l'interface dans ces scénarios. Ils ne prouvent pas l'implication médicale des paraphrases, la stabilité du fournisseur ou la conformité de toute l'architecture ; ces points relèvent de l'audit technique indépendant.
