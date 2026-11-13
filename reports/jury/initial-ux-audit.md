# Audit indépendant de l'interface – constat initial

13 novembre 2026. Audit en lecture seule du code de production et de l'application actuellement servie sur `http://127.0.0.1:8000`. Les seuls fichiers créés sont des scripts, captures et reçus dans `.cache/jury-ux-*`. Aucun appel payant : les requêtes `/ask` ont toutes été interceptées. Les réponses affichées viennent de `reports/acceptance-final.json` ; les erreurs sont simulées. Chromium/Edge en mode headless, tailles de fenêtre 320, 360, 390, 768 et 1440 px, thèmes clair et sombre, navigation clavier.

## Avis du jury UX

L'interface est simple, visuellement cohérente, rapide à comprendre et lisible sur mobile. Elle permet de vérifier les passages d'origine et conserve un avertissement médical visible. Elle est exploitable pour une démonstration encadrée. Elle n'est pas encore entièrement aboutie pour un utilisateur autonome : association question/réponse, affichage des preuves, messages d'abstention et retour sur les états méritent des corrections. Aucun test limité ne peut établir l'absence générale d'hallucinations.

## Défauts reproduits et améliorations

### UX-01 – P2 : réponse détachée de la question effectivement envoyée

**Code :** `frontend/index.html:126`, `frontend/index.html:129`, `frontend/index.html:184`, `frontend/index.html:289`.

**Reproduction :** envoyer la question warfarin, puis cliquer l'exemple metformin pendant l'attente. Le champ affiche maintenant la question metformin et le résultat final parle de warfarin. Aucun rappel de la question soumise n'accompagne le résultat. Le champ et les exemples restent modifiables pendant l'appel.

**Preuves :** `inflight.json`, `mobile-question-mismatch.png`. L'API simulée a reçu warfarin, le champ visible affiche metformin et la première affirmation affichée concerne warfarin.

**Conséquence :** risque de mal attribuer une réponse, surtout lorsque deux questions sont proches. **Correction :** mémoriser et afficher la question soumise dans le résultat ; rendre explicite toute nouvelle saisie et désactiver les exemples pendant l'appel si nécessaire. Tester un changement de question avant la réponse.

### UX-02 – P2 : des instructions internes apparaissent dans les avertissements utilisateur

**Code :** `frontend/index.html:191`.

**Reproduction :** afficher l'abstention de la comparaison dans `reports/acceptance-final.json`. La zone principale Warnings affiche notamment « Each warfarin pregnancy claim must include, within that SAME claim … Combine incomplete pregnancy and exception claims into one qualified claim … ». C'est une instruction de révision destinée au générateur, incompréhensible comme aide utilisateur.

**Preuves :** `results.json` → `abstention`, `mobile-abstention.png`.

**Conséquence :** l'utilisateur ne sait pas s'il doit réécrire lui-même une affirmation médicale ou si l'application est en panne. Les avertissements étant du texte libre, leur affichage peut aussi exposer des explications médicales non vérifiées ; cette possibilité n'est pas une hallucination clinique démontrée par cet essai.

**Correction :** séparer les codes/explications techniques des messages utilisateur ; présenter un texte stable expliquant l'abstention et la prochaine action possible. Ne pas exposer directement les instructions internes ou les brouillons refusés.

### UX-03 – P2 : « Read source » ne montre pas directement l'extrait

**Code :** `frontend/index.html:211`, `frontend/index.html:246`.

**Reproduction :** cliquer le lien sous une affirmation. L'URL devient `#source-1`, mais le `<details>` reste fermé et le `<blockquote>` demeure invisible. Une seconde action sur « Read source excerpt » est nécessaire.

**Preuves :** `results.json` → `source_link` : `detailsOpen:[false]`, `quoteVisible:false` ; `mobile-source-click.png`.

**Correction :** ouvrir le détail ciblé, le mettre en évidence et y déplacer le focus lors de l'activation du lien. Conserver une action claire pour replier ensuite le passage. Le test actuel ne vérifie que le `href`, pas le résultat du clic.

### UX-04 – P2 : longueur maximale connue seulement après l'envoi

**Code :** `frontend/index.html:89`, `frontend/index.html:289` ; règle serveur `app/models.py:26`.

**Reproduction :** saisir 5000 caractères. `textarea.maxLength` vaut -1 et le champ conserve les 5000 caractères. Le serveur rejette seulement après envoi avec « String should have at most 4000 characters ».

**Preuves :** `results.json` → `starting`, `long_question`.

**Correction :** annoncer 4000 caractères et afficher un compteur/une erreur associée au champ avant l'envoi ; éviter toute troncature silencieuse. Garder la validation serveur.

### UX-05 – P3 : les preuves précises du contrôle ne sont pas affichées

**Code :** `frontend/index.html:194`, `frontend/index.html:276`.

Le rendu montre les passages complets et les IDs d'affirmations associés, mais ne lit jamais `grounding.claim_checks[].evidence`. Pour la première réponse, cinq affirmations renvoient au même passage de 1828 caractères. Le lecteur doit retrouver lui-même la phrase précise qui soutient chaque affirmation.

**Correction :** présenter les citations littérales exactes du contrôle par affirmation et permettre d'ouvrir leur contexte complet. Expliquer simplement qu'une citation authentique prouve la provenance mais n'est pas à elle seule une garantie d'interprétation médicale correcte. Ne pas afficher un label qui promet une vérification clinique.

### UX-06 – P3 : repérage du résultat et structure pour les technologies d'assistance

**Code :** `frontend/index.html:99`, `frontend/index.html:101`, `frontend/index.html:129`, `frontend/index.html:260`, `frontend/index.html:309`.

Un seul titre H1 existe initialement ; Answer, Warnings et Sources sont des `<strong>`, et les titres de trace sont des H4. Après le clic Ask puis sa désactivation, le focus observé est BODY. Le résultat dispose bien d'une région `aria-live="polite"`, mais n'a pas de titre de résultat focalisable. Sur mobile 390 px, son début est à environ 734 px du haut, après le long groupe d'exemples.

**Preuves :** `results.json` → `starting`, `answered`, `keyboard_q_tab`.

**Correction :** ajouter des H2/H3 cohérents, annoncer brièvement la fin ou l'échec de la recherche, proposer un lien « Aller à la réponse », et gérer le focus lorsque l'utilisateur a demandé une réponse. Une vérification avec un vrai lecteur d'écran reste nécessaire : cet audit ne certifie pas sa restitution.

### UX-07 – P3 : retour d'attente et erreurs peu guidants

**Code :** `frontend/index.html:132`, `frontend/index.html:152`, `frontend/index.html:161`, `frontend/index.html:295`.

Pendant une requête pouvant durer 180 secondes, seul « Thinking... » est affiché. Pas de temps écoulé ni de rappel du délai maximal. Le texte d'erreur est simplement rendu dans la même zone que la réponse et le bouton Ask est de nouveau actif immédiatement. Les motifs de quota, occupation du service et indisponibilité ont peu de contexte ou d'aide à la reprise.

**Preuves :** `results.json` → `error_429` ; le cas 429 ici est simulé. Le runtime réel utilise également des 503 pour service occupé ou quota fournisseur.

**Correction :** expliquer que la recherche peut prendre du temps, conserver le bouton Annuler, afficher un état d'erreur distinct et une action de réessai adaptée au message serveur. Le chronomètre doit mesurer le temps écoulé sans inventer un pourcentage d'avancement.

### UX-08 – P3 : périmètre documentaire difficile à découvrir

**Code :** `frontend/index.html:78`, `frontend/index.html:112`, `frontend/index.html:142`.

Le lecteur voit seulement que 21 fichiers sont indexés. Il ne voit ni les médicaments/formulations disponibles, ni les limites par produit, ni la date du corpus depuis l'interface. Les quatre exemples ne l'aident pas à découvrir le glossaire ou les autres médicaments. Les fichiers de source sont nommés mais n'offrent pas de lien vers leur provenance officielle.

**Correction :** proposer un panneau compact « Documents couverts » avec médicaments, produits/formulations, date de collecte et lien officiel quand disponible. Rester fidèle aux métadonnées locales : ne pas inventer de date de mise à jour ou de produit.

### UX-09 – P3 : détails de confort et contraste des contrôles

**Code :** `frontend/index.html:29`, `frontend/index.html:38`, `frontend/index.html:124`.

Les exemples longs sont tronqués en plein milieu et le `title` natif n'est pas une aide fiable sur écran tactile ; un clic remplit correctement la question entière. À 390 px, les exemples consomment environ 210 px de hauteur. Les ratios calculés des bordures du champ par rapport au panneau/fond sont faibles : environ 1,22–1,41 selon le thème. Le texte principal et le texte secondaire sont en revanche lisibles : le texte secondaire sur la surface des chips mesure 5,38 en thème clair et 5,89 en thème sombre. Une des chips mesure 32 px de haut : marge d'amélioration tactile, sans en déduire à elle seule un échec d'accessibilité.

**Correction :** utiliser des libellés courts explicites puis montrer la question entière à la sélection ; rendre le contour du champ plus identifiable et prévoir des cibles tactiles confortables. La page ne présente aucun débordement horizontal dans les cinq largeurs essayées.

## Couverture du script de smoke existant

`scripts/browser_smoke.py` est utile pour l'échappement XSS, les contrôles de base, les sources distinctes, la double soumission, l'annulation, le délai fourni par le serveur et quelques endpoints HTTP. Ses 18 contrôles n'équivalent pas à un audit ergonomique ni à une validation clinique. Il ne vérifie pas : association question/réponse après édition pendant une requête ; vraies abstentions et messages internes ; clic ouvrant effectivement la preuve ; limite de saisie ; erreurs 422/429/503/504 dans l'interface ; transition d'un état dégradé vers prêt dans la même page ; placement du focus et titres ; restitution lecteur d'écran ; vérification de chaque citation littérale affichée ; moteur navigateur autre qu'Edge.

Ajouter des assertions ciblées sur les corrections ci-dessus apporte plus de valeur que multiplier des contrôles qui ne font que reproduire la structure du code.

## Points positifs constatés

- Toutes les chaînes testées sont insérées par `textContent`/nœuds DOM ; le smoke existant vérifie plusieurs surfaces XSS.
- Avertissement médical permanent, y compris en mode dégradé.
- Saisie conservée en cas d'erreur, annulation disponible et double soumission protégée.
- Pas de débordement horizontal de 320 à 1440 px avec les longs résultats réels utilisés.
- Extraits repliables, vrais liens internes entre affirmation et source, produits affichés quand fournis.
- Navigation du champ à Ask par Tab et ouverture des détails par Enter fonctionnent.
- Couleurs de texte lisibles dans les deux thèmes ; aucune bibliothèque frontend externe chargée.
- Statuts d'initialisation/dégradation déjà distingués et contrôlés périodiquement.

## Inventaire des preuves

- `results.json` : états, saisie longue, clavier, dimensions et styles calculés.
- `inflight.json` : association question envoyée / question affichée / réponse.
- `html-identity.json` : comparaison de l'HTML servi avec le fichier local au moment du contrôle.
- `mobile-answered.png`, `mobile-source-click.png`, `mobile-abstention.png`, `mobile-question-mismatch.png`, `desktop-answered.png`.
- Scripts reproductibles : `.cache/jury-ux-audit.py`, `.cache/jury-ux-inflight.py`.

Note d'exécution : le premier script a enregistré tous ses résultats puis sa dernière impression console a rencontré l'encodage Windows cp1252 à cause de l'emoji du H1. Le JSON UTF-8 et toutes les captures avaient déjà été écrits ; cela n'indique pas un échec de l'application. Le second script s'est terminé avec le code 0.
