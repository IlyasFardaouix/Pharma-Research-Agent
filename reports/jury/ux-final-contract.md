# Interface finale du mode extraits exacts

13 novembre 2026. Le choix utilisateur priorise les extraits exacts et limite les observations ajoutées aux données vérifiables. Les changements de cette phase restent limités à `frontend/index.html` et `scripts/browser_smoke.py`.

Le mode `response_mode=source_excerpts` s'affiche sous **Evidence from the documents**, avec la question soumise, une notice sur la sélection automatique et chaque passage complet rendu comme citation brute. Le médicament, produit et titre de section viennent de sa Citation associée, sans attribution devinée depuis le texte du modèle. Les espaces et retours à la ligne du passage sont préservés. L'interface explique qu'un passage peut ne couvrir qu'une partie de la section source.

Avant affichage, le client exige un statut approuvé de provenance, un seul passage par extrait, des passages non dupliqués, une Citation non ambiguë, un lien vers l'ID d'affirmation et l'égalité exacte `claim.text === citation.excerpt`. Cette garde établit la cohérence du payload ; la preuve contre le fichier réel, les empreintes et les offsets relève du serveur et de ses tests, pas de cette comparaison côté navigateur.

Les liens **Read full document** utilisent uniquement une route locale `/sources/{filename}?sha256=...`, avec nom simple `.md` et empreinte SHA256 complète. Les valeurs sont encodées et les nouveaux onglets protégés par `noopener noreferrer`. Aucun lien fourni librement par un modèle n'est suivi.

Si `comparison_scope` correspond au message public fixe du serveur, les extraits sont groupés par médicament/produit, sur deux colonnes à partir de 960 px et empilés sur mobile. Tous les passages restent visibles. Les termes de `common_terms` sont présentés comme chevauchement littéral, avec la réserve **Word overlap does not establish clinical equivalence**. Le client n'affiche que des mots réellement présents dans les textes sélectionnés de chacun des ingrédients ; aucune catégorie clinique partagée ou exclusive n'est inférée.

Les `numeric_comparisons` sont dans un panneau séparé **Conditional numerical observation**. Une table conserve la valeur et l'unité de la question d'un côté, celles du seuil source de l'autre. Le calcul affiche la relation numérique du serveur, sans conversion ou équivalence d'unités supposée. La condition publique fixe sur les unités, la normalisation corporelle et le contexte accompagne chaque observation. Aucun avis d'éligibilité clinique n'est généré. Un lien ouvre le passage contenant le seuil. Les observations sans source publiée, au format numérique invalide, avec condition inconnue ou relation inconnue ne sont pas affichées.

Les réponses historiques sans `response_mode` conservent leur rendu antérieur. Les refus ne montrent aucune instruction interne, note clinique de critique ou brouillon rejeté. Le champ `plan_kind=workflow_summary` est affiché sous **Workflow summary** : les étapes fixes ne sont pas présentées comme le plan de recherche privé du modèle. Les historiques `research_plan` gardent le titre **Plan**.

## Vérification

Commande sans appel fournisseur, HTML local intercepté et serveur laissé intact :

```powershell
uv tool run --from playwright python -B scripts/browser_smoke.py --frontend frontend/index.html --report .cache/jury-ux-excerpts-smoke.json
```

**87 contrôles réussis, code de sortie 0.** Les cas du mode antérieur restent couverts. Les nouveaux cas vérifient la conservation des espaces/CRLF, l'identité de chaque citation, la non-publication d'une synthèse cachée, le rejet des attributions incohérentes ou ambiguës, le SHA du lien local, les liens hostiles, les colonnes et regroupements, les mots réellement communs, les unités distinctes et relations below/equal/above, la virgule décimale, l'absence d'observation non attribuable et le libellé honnête du résumé de fonctionnement.

Ces contrôles ne sont pas une nouvelle campagne clinique ni un appel réel au fournisseur. Ils doivent être rejoués sans `--frontend` après reconstruction du conteneur pour contrôler la version réellement servie. Les captures finales seront produites par le parent sur ce déploiement avec une vraie réponse, séparément des fixtures de l'audit.

Les limites initiales de découverte du corpus et de vérification humaine au lecteur d'écran restent documentées dans `RAPPORT_UX.md` et `CORRECTIONS_UX.md`. La nouvelle présentation réduit la génération de prose clinique, mais elle ne prétend pas que le choix des passages, leur pertinence ou leur complétude sont infaillibles.
