# Faux négatif Q4 du barème, sans nouvelle réponse

La campagne focus brute obtient 14/15. Son unique échec est Q4, qui publie pourtant
le contexte complet §2.3 de metformin avec `(eGFR) below 30 mL/minute/1.73 m 2`,
la source exacte et le calcul conditionnel 25 < 30, avec les deux unités.

Le motif factuel écrit par le jury exigeait `eGFR below` sans parenthèse fermante.
Le jury a confirmé ce défaut de son évaluateur, ajouté un positif réel §2.3 et
gardé tous les contrôles négatifs. Le seuil, les unités, la normalisation, les
qualifications, l'authenticité et la complétude exigées ne changent pas.

`http-focus-final.json` reste immuable. `regrade_http.py` produit un autre fichier,
`http-focus-regraded.json`, qui conserve chaque `original_score`, le résumé brut,
l'empreinte du rapport source et celle du barème corrigé. Aucun appel fournisseur
n'est effectué pour ce recalcul. Le script courant écrit par défaut dans
`.cache/http-focus-regraded.json`, sans remplacer la preuve publiée. Cela n'efface pas les refus des campagnes
antérieures et ne fusionne pas un retest dans une série artificiellement parfaite.
