# Utiliser et montrer Pharma Research Agent

L'application consulte les documents fournis et affiche leurs **extraits exacts**.
Elle ne donne pas de conseil médical. Les sources sont fixes et ne sont pas
actualisées automatiquement.

## Parcours simple

1. Ouvrir **http://localhost:8000** lorsque le service est démarré.
2. Attendre l'indication que le corpus est prêt.
3. Saisir une question documentaire, puis lancer la recherche. La recherche et la
   revue peuvent prendre du temps ; l'interface permet d'annuler.
4. Lire les extraits avec le nom du médicament ou du produit, la rubrique et la
   source. Ouvrir le document source pour vérifier le contexte.
5. Consulter les détails d'exécution si nécessaire : résumé du processus et outils
   appelés. Le plan affiché est un résumé neutre, pas une conclusion médicale.

Une abstention invite à préciser la demande, le produit ou la source. Un extrait
exact peut rester incomplet ou mal choisi pour la question ; le statut de revue
ne certifie pas une interprétation clinique.

Commencer par cette question courte :

```text
Define INR using only the provided local glossary.
```

L'objectif est de retrouver une entrée du glossaire, son extrait et sa citation.
Un terme absent ne doit pas recevoir une définition inventée de mémoire.

## Une comparaison prudente

```text
Compare the wording of the supplied contraindication sections for warfarin and apixaban. Show each source's section and preserve all exceptions. Limit conclusions to those documents.
```

La démonstration attendue est documentaire : consulter séparément les passages
des deux médicaments et leur rubrique, puis ouvrir les fichiers sources. Une
condition absente d'une liste sélectionnée n'est pas déclarée cliniquement unique
à l'autre médicament. Le service rappelle ce périmètre de comparaison. Si les
preuves ne suffisent pas, présenter l'abstention comme telle.

Deux questions complémentaires :

```text
A patient with an eGFR of 25 mL/min is being considered for metformin. What threshold is stated in the supplied label? Preserve the source units and qualifications.
```

L'extrait garde les termes de la notice. Une éventuelle observation `25 < 30`
compare seulement les nombres et affiche les unités de la question et de la
source. Elle ne suppose ni unités équivalentes ni normalisation corporelle
identique, et ne décide pas de l'admissibilité d'un patient.

```text
What is the dose of a single-ingredient Ventolin inhaler according to this corpus?
```

Le corpus documente notamment une association nébulisée et des formulations orales
d'albuterol. Leurs doses ne doivent pas remplacer celles d'un inhalateur demandé
absent du corpus. Vérifier le produit exact ou constater l'abstention.

## Démarrage local si nécessaire

Avec Docker Desktop ouvert, depuis le dossier du projet dans PowerShell :

```powershell
# Seulement si .env n'existe pas encore :
if (-not (Test-Path -LiteralPath .env)) { Copy-Item -LiteralPath .env.example -Destination .env }
# Compléter .env localement avec les paramètres du fournisseur autorisé.

docker build -t agent .
docker run --name pharma-demo --rm -p 127.0.0.1:8000:8000 --env-file .env agent
```

Ouvrir **http://localhost:8000**. Le premier démarrage construit les embeddings
avec le fournisseur configuré. Un cache peut être conservé en ajoutant
`-v pharma-cache:/app/.cache` à `docker run` ; un cache chaud peut encore nécessiter
une courte vérification des dimensions auprès du fournisseur.

Si un serveur utilise déjà le port 8000, employer cette instance ou choisir un
port distinct, par exemple `127.0.0.1:8002:8000`, puis ouvrir
**http://localhost:8002**. Une clé présente ne garantit pas que le fournisseur soit
joignable. Le code, le corpus et l'interface sont locaux ; les appels modèle et
embeddings restent externes.

## Présentation facultative en dix minutes

Préparer le service et vérifier une question courte avant la présentation. Garder
la clé et `.env` hors du partage d'écran. Prévoir un ou deux appels en direct : la
latence du fournisseur peut dépasser le temps disponible pour quatre questions.

| Temps | Montrer | Message à faire passer |
|---|---|---|
| 0:00–1:00 | L'interface et le corpus fixe | Une recherche de documents avec preuves consultables. |
| 1:00–2:00 | Le schéma d'architecture | Plan interne, outils choisis par l'agent, revue et publication d'extraits. |
| 2:00–3:00 | INR | Une entrée exacte du glossaire et sa citation. |
| 3:00–6:00 | La comparaison prudente | Deux notices, leurs réserves et le périmètre documentaire. |
| 6:00–7:00 | Un document source ouvert | Empreinte, rubrique et texte original ; le lien refuse une version dont le hash a changé. |
| 7:00–8:00 | eGFR ou produit absent, selon le temps | Arithmétique conditionnelle ou produit exact ; aucune prescription personnalisée. |
| 8:00–9:00 | Les preuves de validation disponibles | Distinguer tests hors réseau, navigateur intercepté et appels réels du modèle. |
| 9:00–10:00 | Les limites | Fidélité des mots, sélection faillible, corpus limité et dépendance fournisseur. |

Les preuves consolidées de cette révision sont enregistrées dans
`reports/jury/`. Les anciens chiffres de **144 tests**, **18 contrôles navigateur**
et **6/7 dans une série modèle complète** sont historiques et concernent le contrat
précédent. Ne pas les annoncer comme validation de la révision `source_excerpts`.
Les anciennes captures ou réponses peuvent illustrer un essai daté, en l'identifiant
explicitement ; elles ne remplacent pas un appel réel ou une validation actuelle.

## Montrer l'API, si utile

Dans un second terminal PowerShell :

```powershell
Invoke-RestMethod http://localhost:8000/health
$body = @{ question = 'Define INR using only the provided local glossary.' } | ConvertTo-Json
Invoke-RestMethod http://localhost:8000/ask -Method Post -ContentType application/json -Body $body -TimeoutSec 200 | ConvertTo-Json -Depth 12
```

Repérer `response_mode: source_excerpts`, les liens entre `claims` et `citations`,
les offsets et SHA-256. `grounding.scope: source_provenance` décrit la provenance
littérale publiée. Le critique utilise un verdict explicite `entailed` sur le
brouillon interne ; ce jugement reste faillible.

## Réponses courtes au jury

- **Pourquoi LangGraph ?** Pour des transitions et une boucle de révision explicites,
  bornées et testables.
- **Pourquoi NumPy ?** Les 556 fragments tiennent dans une matrice en mémoire ; une
  base vectorielle externe n'est pas nécessaire à cette échelle.
- **Pourquoi réassembler les fragments ?** Une coupure pour l'embedding peut couper
  une phrase ou une réserve. L'agent et le critique reçoivent le corps documentaire
  complet, avec un ID couvrant son span exact.
- **Pourquoi publier les extraits ?** Le serveur copie les mots de la source au lieu
  de diffuser la paraphrase du modèle. La sélection et l'exhaustivité restent à
  examiner.
- **Que prouve le hash ?** L'identité de la version du fichier servi. Il ne prouve
  pas l'actualité ou la vérité clinique de son contenu.
- **Le critique est-il indépendant ?** Son invocation est séparée ; il utilise par
  défaut le même modèle configuré, dont les erreurs peuvent être corrélées.

## En cas d'incident

- `starting` : attendre l'initialisation et consulter les journaux.
- `degraded` : vérifier configuration, accès au fournisseur et modèle autorisé.
- `503` : service occupé, non prêt ou fournisseur limité ; attendre avant de retenter.
- `504` : délai dépassé ; essayer une question courte après vérification du service.
- Réseau indisponible : montrer les résultats enregistrés en les identifiant comme
  tels, avec leur version et leur date. Ne pas présenter une simulation comme un
  appel réel.

La démonstration est validée dans le périmètre documenté et reste locale. Ce guide n'effectue aucune
publication de service, de dépôt Git ou de résultats.
