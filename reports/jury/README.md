# Preuves finales conservées

Ce dossier contient les preuves utiles pour examiner le livrable, sans les
journaux intermédiaires ni les audits successifs. Les fichiers de mesure ne sont
pas réécrits lors du nettoyage du dépôt.

| Fichier | Portée |
|---|---|
| `validation.json` | Synthèse datée des campagnes, paramètres, succès, refus et limites. |
| `offline-tests.xml` | 271 tests hors réseau. |
| `browser-final.json` | 87 contrôles du navigateur avec génération interceptée. |
| `docker-final.json` | 14 contrôles Docker/HTTP et empreintes de l'image enregistrée. |
| `http-focus-final.json` | 15 cas avec fournisseur réel ; résultat brut 14/15. |
| `http-focus-regraded.json` | Mêmes réponses, 15/15 après correction du faux négatif Q4 ; anciens scores conservés. |
| `scoring-correction.md` | Justification précise de cette correction. |
| `adversarial-replay.json` | 14 injections de fausses phrases avec critique optimiste ; contrôle de fidélité textuelle. |
| `focus-relevance-limit.json` | Limite observée : une source exacte peut être sélectionnée hors sujet. |
| `corpus-integrity.json` | Comparaison des 21 documents avec leur état initial. |
| `context-reassembly-proof.json` | 556 fragments et 456 contextes complets contrôlés. |

Les preuves précèdent la publication Git et son nettoyage. Les anciens champs
« dépôt absent » sont des constats historiques. Les empreintes décrivent les
fichiers de la campagne enregistrée ; elles ne sont pas un état en direct du
serveur ou de la branche courante. La CI GitHub contrôle le commit effectivement
poussé. Aucun résultat ne constitue une validation clinique.

Les essais intermédiaires, notamment les refus et erreurs de fixtures, restent
consultables dans
[l'historique antérieur au nettoyage](https://github.com/IlyasFardaouix/Pharma-Research-Agent/tree/5385352214a2dfbf65e5a5da7326482751318e67/reports).
Ils ne sont pas fusionnés avec le résultat final. Les originaux restent aussi
conservés localement hors des fichiers publiés.

Les commandes de reproduction sont dans [VALIDATION.md](../../VALIDATION.md).
Les nouveaux essais écrivent dans `.cache/` par défaut et préservent ces preuves.
