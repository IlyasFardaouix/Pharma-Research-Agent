# Audit technique indépendant — état initial du 13 novembre 2026

## Périmètre, méthode et portée des preuves

Lecture du sujet confidentiel local, des sources applicatives, du frontend, des outils, du corpus, des tests, du Dockerfile, des verrous et des documents de livraison. Le sujet n'est pas joint ni reproduit ici. Les preuves propres à cette revue sont la suite locale de **144 tests réussis en 92,86 s**, l'état HTTP réel du conteneur `pharma-final` et les reproductions hors réseau `.cache/jury-semantic-probe.py` / `.cache/jury-semantic-results.json`. Aucun appel de génération/embeddings payant n'a été effectué par ce jury. Les anciennes réponses réelles conservées dans `reports/` ont été examinées comme des observations historiques, pas comme une nouvelle campagne.

Le parent et d'autres relecteurs corrigent le projet en parallèle. Les références ci-dessous concernent les sources lues au début de cette revue; l'instantané `.cache/jury-baseline-manifest.json` détenu par le parent permet de les rattacher. Les correctifs ultérieurs doivent être réévalués séparément. Aucun fichier de production n'a été modifié par ce jury.

Verdict : l'architecture et les contrôles de provenance sont solides pour un exercice de cette taille, mais le système ne démontre pas l'absence d'hallucination. Une réponse réelle a confondu différence d'énumération et différence clinique. Des fautes sémantiques injectées passent la publication et, pour trois d'entre elles, le barème public avec des citations authentiques. La remise externe n'est pas achevée : le dossier n'est pas un dépôt Git et aucune publication publique n'est attestée.

## Constats priorisés

### J1 — Élevé : une vraie comparaison publiée dépasse ce que les sources établissent

Preuve : `reports/comparison-retest.json`, réponse q2, troisième affirmation, qualifie de contre-indications « unique to warfarin » une liste comprenant « central nervous system hemorrhage ». La même réponse indique qu'apixaban est contre-indiqué pour « active pathological bleeding ». La première catégorie peut être une instance de la seconde : l'absence d'une énumération spécifique ne démontre pas une différence clinique. Le texte `reports/comparison-http-final.json`, claims c4/c5, conserve « Warfarin-only contraindications » avant de préciser que les termes ne figurent pas parmi les deux conditions énumérées pour apixaban. Cette précision réduit l'ambiguïté sans rendre l'étiquette clinique générale fondée.

Il s'agit d'un défaut observé dans une réponse issue du modèle réel et acceptée par le critique, pas d'une preuve injectée. La contre-indication explicite de chaque notice peut être citée; l'inférence d'exclusivité clinique ne peut pas être tirée de l'absence des mêmes mots. Références : `app/agent/prompts.py:49`, `app/agent/nodes.py:143`, `app/eval.py:179`, `eval/questions.yaml` q2. Les tests de comparaison vérifient des mots et des sources, pas la relation d'inclusion entre catégories.

Correction prioritaire : distinguer les conditions communes et les différences **de libellé dans les sections consultées**. Exiger des preuves des deux côtés pour les relations comparatives; rejeter les phrases inférant « non contre-indiqué » ou « exclusivement pour ce médicament » depuis une simple absence de mention. Préserver la distinction entre sévérité/spécificité d'une catégorie et absence clinique.

### J2 — Élevé : provenance authentique et revue positive ne suffisent pas à bloquer une proposition fausse

Références : `app/agent/grounding.py:40`, `:55`, `:74`, `:79`, `:93`; `app/answer.py:17`, `:62`, `:69`; `app/agent/graph.py:76`. Le serveur contrôle l'existence d'un ID récupéré, la couverture des IDs et la présence littérale d'une quote. Il ne contrôle pas le rapport sémantique entre cette quote et la proposition. Le critic est un appel séparé au même modèle par défaut, donc ses erreurs peuvent être corrélées avec celles du générateur. Le rendu revalide ces mêmes invariants de provenance.

Reproduction entièrement hors réseau : `.venv311/Scripts/python.exe .cache/jury-semantic-probe.py`. Chaque cas utilise le vrai chargeur et les vrais fichiers du corpus; les citations ont les vrais IDs, offsets, SHA-256 et extraits. Un critic volontairement défaillant est simulé avec `supported=true`, `complete=true`, `safe=true` et une citation littérale.

| Mutation | Résultat de publication | Barème public |
|---|---|---|
| Exception grossesse de warfarin inversée : contre-indiqué « including pregnant women with mechanical heart valves at high risk of thromboembolism » | answered / grounded, aucun flag | PASS q1 |
| Unité metformin changée de mL/min à L/min en conservant 25 et 30 | answered / grounded, aucun flag | PASS q4 |
| Affirmation correcte du seuil suivie d'une prétendue guérison permanente de tous les cancers | answered / grounded, aucun flag | PASS q4 |
| Sujet remplacé par apixaban avec le passage de metformin | answered / grounded, aucun flag | FAIL q4, mais seulement parce qu'un motif attendu manque |

Interprétation rigoureuse : ceci prouve que la barrière de publication et l'évaluateur ne résistent pas à ces erreurs du reviewer. Cela **ne mesure pas** la probabilité que le modèle réel produise/approuve ces erreurs et ne prouve pas qu'un simple utilisateur peut déclencher chaque cas à volonté. Le défaut devient matériel dès qu'une revue se trompe, ce que J1 montre déjà sur une relation comparative.

Correction : proposer des propositions suffisamment atomiques, une décision `entailed / contradicted / insufficient` pour chacune, et une couverture explicite de chaque clause. Les preuves doivent supporter sujet, relation, produit, voie, population, quantité/unité et qualifications, plutôt qu'être simplement présentes dans le bon document. Garder la revue séparée, mais ne pas confondre ajout d'un appel identique et indépendance démontrée. Une autre configuration de reviewer peut réduire certaines erreurs corrélées sans fournir une garantie universelle.

### J3 — Élevé : garde de grossesse contournable par inversion de l'exception

Référence : `app/agent/policies.py:14-18`. Le contrôle cherche grossesse, valves mécaniques, risque élevé et thromboembolisme. Il n'exige pas que ces éléments forment une **exception** à la contre-indication. Le premier cas de J2 contient tous les mots mais inverse exactement le sens du passage. `draft_issues` renvoie une liste vide.

La garde est explicitement documentée comme une règle de régression limitée; elle ne doit pas être généralisée en moteur clinique. Corriger l'inversion ciblée et tester les formulations positive, négative, « including », « except », exception séparée, portée de la population et paraphrases. Une règle qui rejette toute reformulation peut augmenter fortement les abstentions : il faut mesurer cette contrepartie.

### J4 — Élevé pour le bilan de qualité : l'évaluation peut certifier un faux positif matériel

Références : `app/eval.py:63`, `:179`, `:196-218`, `eval/questions.yaml`, `eval/scenarios.yaml`, `tests/test_eval.py`. Les validations de provenance sont utiles et recalculent réellement les empreintes et offsets lorsqu'un corpus est fourni. En revanche, les motifs factuels sont une liste positive étroite, assortie de quelques négations. Une proposition supplémentaire non étayée, une unité fausse ou une inversion d'exception peut passer, comme le montre J2.

La complétude est peu mesurée : q1 peut réussir avec uniquement la grossesse et son exception, sans les autres catégories principales de contre-indications; q2 ne vérifie pas le sens de « unique ». Les trois scénarios généraux ajoutent une définition et deux abstentions : ils élargissent peu la diversité des réponses positives. Les tests hors réseau valident majoritairement des contrats et des doubles du modèle; ils ne mesurent pas sa compréhension. Les régressions sont écrites à partir des erreurs des questions publiques : c'est utile en ingénierie, mais ne constitue pas un ensemble aveugle.

Le bilan existant a un mérite important : `VALIDATION.md` conserve le 6/7 de la série complète et ne le remplace pas par un 7/7 obtenu en mélangeant des retests. Préserver cette honnêteté. Toutefois les termes « réponse vérifiée » doivent indiquer **par quel contrôle**, car PASS n'est pas une validation clinique ni une validation de chaque proposition.

Correction : figer un jeu distinct avant la retouche des prompts; inclure chaque médicament, plusieurs formulations, questions françaises/anglaises, comparaisons, négations, exceptions, unités, questions incomplètes et refus injustifiés. Ajouter des mutations de réponses correctes (changement de médicament, voie, nombre, comparateur, unité, population, suppression de clause et ajout d'une clause non prouvée). Mesurer séparément fidélité sémantique, complétude, exactitude des citations, taux de réponse et faux refus. Une revue humaine indépendante doit annoter l'implication claim→preuves; le même LLM ne doit pas être l'unique oracle de succès.

### J5 — Moyen : l'outil d'inventaire accumule des preuves qu'il ne montre pas au générateur

Référence initiale : `app/tools/sections.py`, `run_list` (environ lignes 120-140). L'outil stocke un passage par document dans `ToolResult.passages`, mais le texte remis au modèle contient seulement noms, fichiers et quelques identités de produit. Il n'expose aucun ID de passage ni extrait, alors que `AGENT_SYSTEM` exige des IDs exacts issus des outils. Pour une question d'inventaire, les passages sont présents chez le critique mais invisibles à l'étape qui doit les citer. Le modèle doit multiplier les appels, deviner des IDs (rejetés) ou s'abstenir.

Correction : exposer dans ce résultat les IDs et une courte preuve littérale d'identité par source; conserver des limites de contexte. L'autre agent de revue travaille sur ce correctif; non encore requalifié dans cet audit initial.

### J6 — Bloquant pour la remise externe : aucun dépôt Git/public attesté

Preuve propre : `git status --short`, `git log -1` et `git ls-files` renvoient « not a git repository ». `LIVRAISON.md` et `README.md` reconnaissent explicitement l'absence de publication. Un ZIP propre et un rapport ne satisfont pas l'exigence de lien public et de commit poussé avant l'échéance. La présentation peut être un walkthrough : `DEMO.md` prépare bien ce format.

Correction : préparer l'historique et un dépôt public autorisé sans secrets ni sujet confidentiel, vérifier la reproductibilité depuis un clone, puis réaliser la remise conformément aux instructions du candidat. La présence de règles `.gitignore` ne prouve pas qu'un futur commit est propre : contrôler les fichiers suivis avant publication. Aucun envoi ou push n'a été fait par ce jury.

## Architecture, corpus, exploitation et sécurité

Points solides : modules à responsabilités relativement claires; graphe explicite avec planification, choix d'outils, revue et révision bornée; contrat typé strict contre les clés supplémentaires et booléens coercitifs; provenance exacte avec empreintes et offsets; aucune publication brute d'un brouillon non approuvé; citations rendues par le serveur; validation du corps avant parsing; admission bornée par sémaphore; budget par requête via ContextVar; conservation de la capacité tant qu'un worker annulé tourne; erreurs fournisseur expurgées; utilisateur Docker non root; dépendances fixées et hash-locked; interface sans injection HTML de contenu modèle.

Le corpus contient 21 fichiers, 10 médicaments avec deux sources et un glossaire, et produit 556 passages. Les noms de fichiers ne décrivent pas toujours précisément le produit : le label albuterol correspond à une association nébulisée, la monographie albuterol à des formes orales, le fichier aspirin à un produit effervescent. Le registre explicite de certaines identités est donc justifié. Il reste partiel et ne constitue pas un catalogue exhaustif de formulations. Les sources originales comportent leurs liens, mais les réponses n'exposent généralement que le fichier/section/extrait. Pour un exercice sur corpus figé c'est conforme; cela ne prouve pas l'actualité clinique.

Le découpage par titres et offsets préserve le texte, mais `_raw_spans` peut couper une phrase longue entre deux chunks sans chevauchement. Une restriction peut alors être dans le chunk suivant; top-k ne garantit pas de le récupérer. L'outil de section complète compense lorsque le modèle le choisit. C'est un risque de rappel et de qualification, pas une erreur démontrée sur toutes les questions. Mesurer avec des passages où la réserve traverse une frontière; envisager le rattachement aux phrases/paragraphes voisins sans modifier les extraits sources.

La recherche emploie une vraie similarité cosinus mémoire et un seuil configurable; elle n'est pas routée par une liste de réponses prédéfinies. Aucune étude de rappel ni calibration du seuil 0,18 sur un jeu indépendant n'est fournie. Les questions publiques favorisent les sections structurées connues; tester aussi les formulations qui exigent réellement la recherche sémantique.

Le conteneur observé est sain, lié à `127.0.0.1:8000`; `/health` retourne HTTP 200, `status=ok`, 21 fichiers, 556 chunks, configuration modèle présente. Cela prouve l'initialisation de l'index, pas la disponibilité continue du fournisseur ni la qualité future des réponses. La construction initiale dépend du réseau, de la clé et du quota embeddings; des 429 sont historiquement documentés. Trois essais bornent les reprises, mais peuvent répéter des lots déjà payés si l'échec arrive tard. Un processus/thread annulé ne peut pas interrompre rétroactivement un appel réseau déjà en cours : limite correctement documentée.

L'image contient code/corpus/UI et requiert normalement un service LLM externe : « autonome » au sens du packaging du sujet ne signifie pas « génération hors ligne ». Le tag `python:3.11-slim` n'est pas fixé par digest; la résolution du système de base peut évoluer malgré les paquets Python verrouillés. Le fichier CI GitHub existe, mais n'a pas été exécuté à distance et ne serait pas exécuté automatiquement par GitLab sans configuration adaptée. Le scan Python historique annonce 54 dépendances sans vulnérabilité connue lors de cet essai; ce jury ne l'a pas réinterrogé et il ne couvre pas l'ensemble du système de l'image. Aucun défaut de dépendance connu n'est affirmé sans preuve.

Pas d'authentification ni de quota utilisateur : acceptable pour cette démonstration locale explicitement bornée, insuffisant pour une ouverture Internet payante. Aucun besoin d'ajouter un système d'authentification pour satisfaire le sujet local. Les fichiers de packaging utilisent une sélection explicite et vérifient l'occurrence de la clé courante; ce contrôle n'est pas un détecteur exhaustif de tout secret éventuel. Les rapports historiques livrés doivent rester identifiés comme tels et les nouveaux résultats rattachés à un hash de sources, modèle, paramètres, date et jeu de questions.

## Jugement UX

La base est lisible, légère, sans dépendances frontend, avec états de disponibilité, exemples, annulation, extraits ouvrables, trace inspectable et disclaimer permanent. L'affichage utilise `textContent` et les liens locaux évitent de transformer un texte modèle en HTML actif. Les rapports de navigateur historiques contiennent 18 contrôles; ils interceptent les appels de génération et ne doivent pas être confondus avec 18 validations du modèle réel.

Réserves de l'état lu : le verdict vert `grounded` (`frontend/index.html:281`) peut être compris comme une certification, alors qu'il n'est qu'un jugement automatique; les preuves exactes du critic (`claim_checks`) ne sont pas affichées, seulement les passages entiers. Un clic « Read source » atteint la source mais n'ouvre pas nécessairement l'extrait. La question reste modifiable pendant l'attente et la réponse n'est pas ancrée visuellement à un rappel de la question soumise. La zone de saisie n'a pas de compteur/maxlength correspondant à la limite API; le feedback peut arriver tard. `Thinking...` est le seul état pendant des comparaisons observées à 69–97 secondes; l'utilisateur ne voit pas s'il s'agit de recherche ou de révision. Une animation ne remplace pas un état fidèle; ne pas simuler de progression inexistante. L'agent UX traite plusieurs de ces points en parallèle, à vérifier ensuite.

L'accès aux sources compte plus qu'un embellissement graphique : associer les affirmations aux preuves lisibles, rappeler la portée de la validation, rendre les erreurs et l'annulation prévisibles, préserver le focus et l'accessibilité clavier. La terminologie technique c1/grounded peut être conservée dans la trace, mais la réponse principale doit être lisible sans connaissance du protocole interne.

## Matrice de conformité au sujet

| Exigence reformulée | État initial | Preuve / réserve |
|---|---|---|
| Python 3.11+ et versions de dépendances fixées | Conforme | pyproject, verrous hashes, suite exécutée sous .venv311 |
| Planification de questions composées | Implémentée | planner + plan dans traces; pas de mesure indépendante de complétude du plan |
| Récupération par similarité mémoire | Conforme architecturalement | NumPy cosine, embeddings, search_corpus; rappel non mesuré |
| Au moins deux outils locaux, sélection agentique | Conforme | quatre outils bindés, sélection par tool calls; pas besoin de forcer deux outils pour chaque lookup simple |
| Revue avant publication des faits | Implémentée mais insuffisance sémantique démontrée | critic structuré, révisions, J1–J4 |
| Citations de fichiers et disclaimer | Conforme pour le flux normal | rendu serveur, API et UI; citations authentiques ≠ implication |
| Docker racine, code/corpus embarqués, env injecté | Conforme par inspection et conteneur observé | aucun rebuild de zéro exécuté par ce jury; preuves historiques disponibles |
| GET /health HTTP 200 | Reproduit | conteneur actuel sain |
| POST /ask JSON et frontend minimal | Implémenté/testé hors réseau et historiquement réel | pas de nouvelle question facturable dans cette revue |
| Jeu public et questions cachées | Public intégré, généralisation non établie | quatre questions détaillées + trois scénarios locaux; ne pas inventer une cinquième question publique |
| Qualité du code et expérience | Bonne base, améliorations nécessaires | tests, limites runtime, points UX et sémantiques ci-dessus |
| Configuration d'assistance IA partagée | Présente localement | .claude/CLAUDE.md, plan, outils décrits; pas encore poussée |
| Dépôt public et remise avant échéance | Non attesté, dossier non Git | J6 |
| Présentation d'environ dix minutes | Préparée | DEMO.md; performance réelle dépend du fournisseur |

## Rendre l'exigence « pas d'hallucination » opérationnelle

Ne pas remplacer tout le projet par des extraits sans synthèse ni par une abstention systématique : cela contournerait le cœur des questions composées. Le contrat opérationnel doit plutôt être : aucune proposition factuelle n'est publiée sans preuves identifiées, revue sémantique explicite de toutes ses clauses, contrôles déterministes applicables et absence de contradiction détectée; tout échec entraîne révision puis abstention. Ce contrat est vérifiable, contrairement à une garantie universelle de vérité.

Les contrôles déterministes doivent rester contextuels : comparer relation numérique, unité et population, pas uniquement la présence de nombres. Le « 25 » de la question eGFR n'a pas besoin d'être écrit dans le document si l'inférence arithmétique est justifiée; en revanche l'unité et la comparaison au seuil doivent être explicites. Les comparaisons exigent les deux notices et une portée textuelle claire. Une quote exacte peut étayer une clause et pas les autres : la revue doit pouvoir rejeter une réponse partiellement étayée.

Avant la remise : (1) corriger les contresens comparatifs observés et les contournements de règles; (2) introduire les mutations adversariales comme cas de rejet et les réponses fidèles comme cas positifs; (3) vérifier le contrat complet sur des appels bornés du modèle réellement déployé; (4) contrôler les faux refus; (5) refaire Docker/UI/packaging sur les mêmes sources; (6) documenter les cas résiduels et finaliser le dépôt public. Fixer les critères d'acceptation avant les retests empêche de transformer chaque échec en nouveau barème favorable.

Une campagne finie peut rapporter « zéro affirmation non étayée observée parmi N affirmations, selon cette procédure de revue », jamais « zéro hallucination garanti ». Le bilan doit compter les abstentions et réponses incomplètes au lieu de les masquer. L'audit lui-même ne prétend ni à l'exhaustivité ni à une validation clinique.
