# Avis indépendant sur le choix « extraits exacts en priorité »

Le choix explicite de l'utilisateur est compatible avec le sujet, à condition de conserver une réponse composée utile. Le sujet n'impose pas une prose clinique libre. L'agent peut planifier, choisir ses outils, rechercher, sélectionner et rapprocher des preuves, puis faire revoir cette sélection avant qu'un serveur rende les extraits et les seules relations vérifiables. L'autonomie agentique porte sur la recherche et l'organisation, pas sur un droit à publier une paraphrase.

Cette architecture réduit fortement le risque d'inventer une phrase dans la réponse. Elle ne supprime pas les erreurs de sélection, de produit, de contexte, de pertinence, de complétude ni de rapprochement entre extraits. Un extrait authentique peut être trompeur s'il est coupé avant sa réserve ou placé sous un titre faux.

## Conditions du contrat de publication

1. Le contenu clinique public doit provenir du corpus, non du texte du brouillon ni d'une quote abrégée choisie par le reviewer. Les métadonnées doivent être issues du chargeur ou d'un registre vérifié. Une sortie clinique libre ne doit pas réapparaître dans `claims`, `grounding.notes`, `flags`, les intitulés ou une autre propriété JSON publique.
2. Les extraits doivent constituer une unité de contexte complète : phrase/paragraphes complets, liste avec son introduction, tableau avec ses entêtes et les lignes « Clinical Impact / Intervention » liées. Un chunk complet n'est pas une unité sémantique complète. Dans le corpus réel, `dailymed-atorvastatin@6ea369098461:25611-27535` finit par « ... is 2 » et le suivant commence « to 4% and 15 to 20%, respectively ». D'autres chunks séparent impact et intervention. Cette situation exige un ajout de contexte, pas un simple badge « extrait exact ».
3. Les voisins ajoutés doivent être fournis au reviewer et avoir leurs propres offsets/empreintes ou un span fusionné exact et vérifiable. Ne pas inventer un collage sans provenance; ne pas attribuer un span fusionné à l'ancien ID d'un fragment. Garder les métadonnées de section et le lien au document complet.
4. Dédupliquer les mêmes spans pour la lecture, mais conserver leurs associations aux différentes parties de la question. Un extrait qui répond à deux sous-questions ne doit pas perdre sa seconde association. L'absence d'un médicament/produit ou d'une composante demandée doit empêcher le statut « réponse complète ».
5. La revue doit vérifier pertinence, bonne identité de produit/voie/population, complétude de chaque sous-question et absence de contexte contradictoire omis. Elle ne doit pas seulement confirmer que les extraits existent. Un mauvais reviewer peut encore sélectionner une preuve hors sujet : ce risque doit rester mesuré.
6. Les en-têtes serveur doivent être neutres. Pour une comparaison, « Libellés rapprochés » avec les deux extraits est plus précis que « identiques cliniquement »; « Autres libellés de cette section » n'affirme pas qu'une condition n'existe pas ailleurs ou ne relève pas d'une catégorie plus large. Une réponse ne doit jamais inférer la permission de prendre un médicament depuis une absence de mention.
7. Éviter un dump de tous les passages récupérés. Publier seulement les unités nécessaires aux parties de la question, avec accès au contexte. Une réponse de plusieurs dizaines de milliers de caractères techniquement exacte peut échouer à l'exigence d'utilité.
8. Le plan doit être présenté comme plan de recherche provisoire, pas comme résultat clinique. Les notes libres de revue peuvent rester internes. Les erreurs publiques et motifs d'abstention doivent être des messages serveur maîtrisés.

## Tests d'acceptation à figer avant le nouveau retest

Les invariants suivants sont communs : égalité exacte des extraits avec les spans de fichiers originaux; médicament/produit/source corrects; toutes les parties de la question couvertes; aucun texte du draft injecté; disclaimers; citations associées; absence de contradictions introduites par les titres. Un test négatif doit supprimer ou remplacer une preuve tout en gardant un JSON et des citations valides. La sortie doit alors échouer à la complétude/pertinence, et non passer parce qu'elle est extractive.

### Q1 : contre-indications principales de warfarin

Exiger les catégories de la section de contre-indications, y compris grossesse **avec l'exception complète**, tendances hémorragiques/dyscrasies, chirurgie/procédures, situations obstétricales, non-observance sans supervision, hypersensibilité et hypertension maligne. Le choix le plus simple est l'extrait complet de cette courte section avec son titre. Une réponse ne contenant que la grossesse ne doit pas passer « complète ».

Négatifs : couper juste avant l'exception; ne prendre que la première puce Pregnancy; remplacer par une section de mécanisme; masquer des catégories; conserver un draft affirmant l'inverse. Le dernier cas ne doit faire apparaître sa paraphrase dans aucun champ clinique public, même si le reviewer l'approuve.

### Q2 : comparaison warfarin/apixaban

Exiger les deux sections de contre-indications et une organisation permettant d'identifier (a) les libellés relatifs au saignement dans chacune, (b) l'hypersensibilité avec la sévérité et la portée propres à chacune, (c) les autres libellés énumérés chez warfarin, dont la réserve de grossesse. Les relations affichées sont des rapprochements textuels limités aux documents, pas une équivalence clinique universelle ni un catalogue d'autorisations.

Négatifs : une seule notice; sections inversées sous les mauvais médicaments; hémorragie du SNC classée comme preuve qu'apixaban est permis; hypersensibilité « severe » supprimée; titre libre « pregnancy safe with apixaban »; tous les passages présents mais aucun rapprochement utile. Ce dernier résultat peut satisfaire provenance/rappel mais doit être noté insuffisant pour la comparaison.

### Q3 : association warfarin/sertraline, risque et surveillance

Exiger des preuves pour **les deux dimensions** : augmentation/addition du risque de saignement et surveillance INR, avec les conditions temporelles disponibles (début/arrêt/changement de traitement). Les deux médicaments doivent être identifiables dans les preuves ou leur contexte documentaire. Conserver les modalisations, par exemple « may », si elles figurent dans la notice. La seule mention du mot INR n'est pas une réponse à « quelle surveillance ».

Négatifs : seulement risque; seulement surveillance; définition du glossaire à la place de la recommandation; preuve sur une autre association; récupération du texte antérieur à une phrase qui qualifie le risque; transformation d'une surveillance en dose personnalisée. Les deux sources demandées par le jeu public doivent être consultables, sans forcer que chaque phrase porte les deux citations si une seule la supporte.

### Q4 : eGFR 25 et seuil de metformin

Exiger le passage définissant la contre-indication en dessous de 30 avec l'unité et la normalisation complètes. **Afficher seulement ce passage ne répond pas entièrement à l'application au nombre 25.** Deux options honnêtes : ajouter une inférence numérique déterministe, bornée et conditionnelle; ou afficher explicitement que la conclusion appliquée à la donnée du patient n'est pas fournie et noter cette réponse partielle, sans la compter comme plein succès du sujet.

Une synthèse limitée vérifiable peut afficher « 25 < 30 » et préciser que la comparaison suppose les mêmes unités et la même normalisation que le libellé. Le sujet donne mL/min, la notice mL/min/1,73 m² : ne pas transformer silencieusement l'une en l'autre. La relation au seuil doit être calculée à partir des valeurs/relations réellement extraites et des données explicites de la question, non à partir d'une réponse LLM tenue pour vraie. Aucune prescription personnalisée n'est requise.

Négatifs : < remplacé par >; 30 remplacé par 45; initiation non recommandée confondue avec contre-indication; unité L/min substituée à mL/min; autre médicament; eGFR 35 ou exactement 30 pour tester la frontière; unité non comparable; calcul « 25 > 30 » proposé par le draft; valeur 25 absente de la question mais inventée par le modèle. Le renderer ne doit pas copier ce calcul faux.

## Requalification des anciennes attaques

Les probes initiaux qui injectent une paraphrase fausse doivent être rejoués contre le nouveau contrat. Le résultat attendu est soit une abstention justifiée, soit une réponse composée d'extraits corrects et de relations serveur vérifiées; **jamais la phrase fausse**, même dans les détails ou le JSON. Il faut en parallèle tester que des preuves authentiques mais hors sujet ne deviennent pas une réponse complète.

Les anciens scores de prose et les nouveaux scores extractifs mesurent des produits différents. Conserver les anciens résultats; annoncer le changement de contrat, publier les critères de la nouvelle campagne et rapporter séparément fidélité textuelle, contexte, pertinence, complétude, synthèse vérifiée, refus et latence. Ne pas supprimer un test de sens au seul motif que le rendu a changé.

Verdict architectural : favorable sous ces conditions. Plan→outils autonomes→sélection/revue→publication extractive vérifiable répond à l'intention technique du sujet. Un simple affichage de chunks, sans contexte complet ni traitement explicite des comparaisons et du seuil chiffré, reste une conformité partielle à l'assistant de recherche composé.
