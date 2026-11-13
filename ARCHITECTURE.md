# Architecture et traçabilité

Le service recherche des informations dans un corpus local fixe. Le contrat public
`source_excerpts` publie les mots des sources sélectionnées, avec leur contexte
complet et leur provenance. Le modèle conserve la responsabilité de planifier,
choisir les outils et proposer une sélection pour la revue. Le serveur construit
le texte documentaire publié. Cette séparation répond au choix de privilégier les
extraits exacts sans transformer l'application en abstention systématique.

## Parcours d'une requête

```text
POST /ask
  ├─ Plan interne : sous-questions, médicaments et produits demandés
  ├─ Agent : choix libre des quatre outils du corpus
  │    ├─ index : fragments courts pour la similarité NumPy
  │    └─ preuve : réassemblage du corps Markdown complet avant exposition
  ├─ Sélection interne compacte : focus littéral + un ID par contexte
  ├─ Critique : pertinence des contextes et complétude de leur ensemble
  │    └─ révision et nouvelle récupération dans les limites autorisées
  └─ Rendu serveur : contextes sources littéraux ou abstention
       ↓
{status, response_mode, answer, claims, citations, grounding,
 numeric_comparisons, comparison_scope, plan, tool_trace, disclaimer}
```

Le graphe se trouve dans [`app/agent/graph.py`](app/agent/graph.py), les nœuds dans
[`app/agent/nodes.py`](app/agent/nodes.py). Aucun routage par mots clés ne remplace
le choix des outils. La section documentaire est déterministe une fois les
arguments choisis par l'agent ; c'est une propriété de l'outil, pas une décision
codée pour chaque question publique.

## Index et preuves sont deux unités différentes

Les **21 documents fournis et les 556 fragments indexés** restent inchangés.
[`loader.py`](app/rag/loader.py) conserve le texte destiné aux embeddings, les IDs
et les offsets des fragments. Il ajoute les bornes du corps Markdown avant sa
fragmentation : `context_start_offset` et `context_end_offset`. Cette métadonnée
ne modifie pas la séquence des textes indexés ni sa clé de cache.

[`context.py`](app/rag/context.py) réassemble les fragments contigus d'un même
corps, par concaténation exacte de `raw_text`. Il contrôle les bornes, la continuité,
l'empreinte du document, les IDs canoniques et l'identité du médicament, de la
source, du produit et de la rubrique. L'ID de preuve devient
`nom@préfixe_sha256:début-fin` sur le contexte complet. Les offsets comptent les
caractères du fichier décodé en UTF-8, pas les octets ; l'empreinte SHA-256 porte
sur les octets originaux. Unicode et fins de ligne restent inchangés.

La recherche et les sections de [`CorpusIndex`](app/rag/index.py) effectuent ce
réassemblage avant que les IDs et textes soient montrés à l'agent puis au critique.
Un contexte trouvé plusieurs fois ne paraît qu'une fois, avec son meilleur score.
Les outils protègent aussi les façades de corpus et l'inventaire. Les entrées
complètes produites par le glossaire gardent leurs propres bornes et IDs ; elles
ne sont pas élargies à tout le glossaire.

Un fragment manquant, un chevauchement ou une identité incohérente entraîne un
refus explicite de ce lot de preuves. Une unité trop grande n'est pas raccourcie :
la limite par défaut est de 60 000 caractères, en cohérence avec le budget de
preuves. La limite globale de contexte et de revue s'applique également. Un corps
entre deux en-têtes est complet à cette échelle ; il ne comprend pas nécessairement
les réserves situées dans une autre rubrique du document.

Exemple de défaut évité : un fragment d'atorvastatin se terminait par
`pregnancies is 2 `, et le suivant commençait par `to 4% and 15 to 20%`.
La preuve entière conserve désormais cette phrase et le reste du même contexte,
avec un seul ID couvrant le span source complet.

## Sélection, critique et publication

Le protocole conserve la forme JSON `DraftAnswer` pour limiter les changements de
transport. Le sens du champ interne `claims` évolue : chaque entrée sélectionne
**un seul ID** et son `text` est un **focus copié littéralement, de 12 à 1 800
caractères**, dans ce contexte. Au plus 20 sélections sont permises. Ce focus est
un repère compact, pas une assertion médicale à reformuler ni une réponse à lui
seul. Il peut contenir une liste ou plusieurs phrases exactes.

L'ancien brouillon imposait une paraphrase autonome avec une phrase et une
proposition par affirmation. Cette obligation n'était pas nécessaire au rendu
d'extraits entiers : une reformulation défectueuse pouvait faire refuser des
contextes pertinents qui auraient été publiés sans altération. La sélection
littérale évite cette opération intermédiaire ; elle n'assouplit pas les contrôles
sur le produit demandé, la population ou les preuves disponibles.

Le critique reçoit toutes les preuves récupérées ou la requête échoue au budget,
sans troncature silencieuse. Il examine la **pertinence et l'applicabilité du
contexte complet** de chaque sélection, puis la **complétude de l'ensemble des
contextes sélectionnés qui seront publiés**. Il ne juge pas la complétude du focus
seul, ni celle des passages récupérés mais non sélectionnés. Une réserve déjà
présente dans le contexte n'a pas à être répétée dans le focus. Si une autre
rubrique est nécessaire pour une qualification matérielle de la question, le
critique doit demander sa récupération et sa sélection plutôt qu'en inférer le
contenu depuis une référence.

Chaque sélection reçoit un verdict explicite `entailed`, `contradicted` ou
`insufficient` et une preuve littérale du même passage. `entailed` et
`supported=true` signifient ici que la sélection documentaire est justifiée et
pertinente pour sa partie de la question ; ils ne certifient pas une nouvelle
paraphrase clinique. Une approbation exige une sélection complète et sûre, sans
drapeau et avec toutes les sélections étayées.

Une invocation séparée ne constitue pas un arbitre indépendant de vérité : le même
modèle est utilisé par défaut, et ses erreurs peuvent être corrélées. Les contrôles
déterministes de fidélité détectent certaines valeurs, unités, attributions de
médicament ou de produit et certains raccourcis comparatifs. Ils ne forment pas un
moteur général d'implication médicale.

Après validation, [`grounding.py`](app/agent/grounding.py) développe la sélection en
les **contextes sources complets** choisis. Les `claims` publics sont alors des
unités documentaires : pour chacune, un seul ID, une citation et un texte identique
à `citation.excerpt`. Le serveur ajoute les identités et rubriques depuis les
métadonnées, le périmètre de comparaison et l'avertissement non médical. Le mode
est `source_excerpts` et `grounding.scope` vaut `source_provenance`.

Cela garantit la fidélité des mots publiés à leurs sources vérifiables. Cela ne
garantit ni le choix des bons passages, ni leur exhaustivité, ni une décision
clinique correcte. La revue examine les contextes qui seront publiés pour la
question posée ; elle ne certifie pas la vérité clinique de toutes leurs propositions.

Le plan public est un résumé neutre des étapes de recherche, revue et publication.
Les instructions libres du plan interne et les diagnostics cliniques non vérifiés
du critique ne sont pas présentés comme des faits supplémentaires.
La trace publique conserve la séquence réelle des noms d'outils ; requêtes libres,
arguments et résumés partiels restent internes. Les preuves publiées portent les
identités de produits et les rubriques effectivement sélectionnées.

## Comparaisons et nombres

La comparaison concerne le contenu des sections citées. Une différence de liste
ne démontre pas qu'une condition est cliniquement exclusive à un médicament, ni
qu'un médicament serait sûr en l'absence de mention dans l'autre liste. Les extraits
restent consultables séparément, avec leur source et leur périmètre.

[`numeric.py`](app/agent/numeric.py) peut relever une seule entrée eGFR explicite
et un seuil littéral dans les contextes publiés, puis calculer `below`, `equal` ou
`above` avec des nombres décimaux. Il conserve les unités de la question et de la
source, sans les convertir ni supposer une normalisation corporelle identique.
Ainsi, `25 < 30` est une observation arithmétique conditionnelle ; ce n'est pas la
décision qu'un patient est admissible ou contre-indiqué. Une entrée ambiguë ou un
seuil non reconnu ne produit pas de conclusion numérique.

## Choix et raisons

| Choix | Raison | Limite et contrôle |
|---|---|---|
| LangGraph et outils choisis par le modèle | Garder planification, recherche composée et révision visibles | Boucles, durée, appels et contexte bornés par requête. |
| Similarité NumPy sur petits fragments | Recherche en mémoire adaptée au corpus et cache réutilisable | La similarité ne démontre pas la pertinence médicale ; les preuves sont élargies au contexte avant revue. |
| Sections et alias canonicalisés avant les politiques | Une rubrique dosage nommée « administration » doit subir les mêmes contrôles de marque et produit | Source stricte, fallback explicite ; refus des rubriques inconnues et des produits absents ou ambigus. |
| Focus littéral interne et contextes publics entiers | Ne pas exiger une synthèse intermédiaire qui ne sera pas publiée | Le focus doit être exact et chaque contexte applicable ; pertinence et complétude restent faillibles. |
| Révision bornée puis abstention | Ne pas diffuser un brouillon non validé | Faux refus possibles ; les mesurer au lieu de les masquer. |
| Provenance SHA-256 et offsets | Rendre chaque extrait vérifiable dans le fichier original | Cela certifie une version du corpus, pas son actualité ni sa vérité clinique. |
| Plan public neutre | Ne pas laisser une assertion non vérifiée réapparaître dans le volet de processus | Le détail interne de raisonnement n'est pas une preuve médicale. |

## HTTP, interface et documents originaux

[`main.py`](app/main.py) expose `/health`, `/ask`, `/` et
`/sources/{filename}?sha256=...`. Ce dernier renvoie le document original comme
texte, contrôle le nom et le répertoire du corpus, refuse les liens symboliques
et compare l'empreinte demandée aux octets servis. Une modification donne un refus
`409`. Le lien lie le téléchargement à une version de source ; il ne s'agit pas
d'une autorisation d'accès à d'autres fichiers locaux.

Les budgets sont isolés par requête dans [`execution.py`](app/execution.py). La
limite du corps HTTP précède le parsing ; admission concurrente, délai global et
annulation protègent le service. L'interface traite les contenus dynamiques comme
du texte et permet de consulter extraits, documents et détails d'exécution.
`/health` renseigne l'état local de démarrage et de configuration ; les modèles et
embeddings dépendent toujours du fournisseur externe.

## Matrice des exigences du sujet

| Exigence | Réalisation | Preuve à examiner pour la version actuelle |
|---|---|---|
| Python 3.11+, dépendances fixées | `pyproject.toml`, verrous runtime et développement à empreintes | 271 tests réussis sous Python 3.11 ; XML et synthèse sous `reports/jury/`. |
| Planifier les questions composées | Nœud de planification interne et graphe LangGraph | Tests du graphe, scénarios composés et traces des outils ; le plan public est un résumé sûr. |
| Retrieval par similarité en mémoire | Matrice NumPy de vecteurs normalisés, embeddings configurés et cache local | Tests index/cache ; invariance des 556 textes indexés ; réassemblage des contextes avant exposition. |
| Au moins deux outils locaux, choisis par l'agent | Quatre outils : recherche, section, glossaire, inventaire | Registre d'outils et `tool_trace` ; pas d'obligation artificielle de deux appels pour une question simple. |
| Critique du grounding et autocorrection | Revue des contextes sélectionnés avec verdict `entailed`, preuve littérale, couverture de la question et révisions bornées | Cas adversariaux et refus de revue incohérente ; pertinence et complétude toujours faillibles. |
| Réponse citée et avis non médical | Extraits publics exacts, liens vers le document lié à son hash, disclaimer | Contrats API, provenance, navigateur ; aucun verdict ne certifie une sécurité clinique. |
| Corpus fourni conservé | 21 fichiers inchangés, fragments d'indexation inchangés | Comparaison des sources, SHA-256, offsets Unicode/CRLF et textes d'embedding. |
| Docker à la racine, `/health`, `/ask`, frontend | Dockerfile, FastAPI et interface statique | Reconstruction et essais HTTP/navigateur du contrat actuel ; le fournisseur reste externe. |
| Questions publiques et questions cachées | `eval/questions.yaml`, scénarios et évaluateur générique | Provenance générique, contrôles factuels limités, cas aveugles et lecture des réponses sensibles. |
| Configuration IA, dépôt public et présentation de dix minutes | `.claude/CLAUDE.md`, plan initial conservé, dépôt GitHub public et guide `DEMO.md` | Code et configuration publiés ; vérifier la CI du commit remis. L'envoi du lien et du résumé au recrutement reste une action distincte. |

## Validation et statut des preuves

Les résultats consolidés du contrat `source_excerpts` sont disponibles
sous `reports/jury/` : **271 tests**, **87 contrôles navigateur**, **14 contrôles
Docker/HTTP**, et une campagne réelle **15/15 après correction documentée d'un
faux négatif du barème** (score brut 14/15 conservé). [`VALIDATION.md`](VALIDATION.md)
précise les conditions des essais. Les campagnes intermédiaires appartiennent à
l'historique Git ; elles ne sont pas utilisées comme certification du contrat actuel.

Les vérifications génériques recalculent les empreintes des documents et contrôlent
les spans, IDs, liens, textes exacts, statuts et revues. Les quatre questions publiques
ajoutent un barème factuel étroit. Ces deux niveaux doivent être distingués des essais
réels du modèle et de la validation clinique. Les preuves enregistrées sont datées ;
la CI du commit effectivement remis constitue une vérification distincte.
