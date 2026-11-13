# Produit local et remise

Le produit est une démonstration de recherche documentaire agentique, avec
contextes sources littéraux, citations, rapprochement textuel et calcul numérique
conditionnel. La pertinence et la complétude restent faillibles ; aucun conseil
médical ou garantie générale d'absence d'erreur n'est fourni.

1. Ouvrir http://127.0.0.1:8000 et attendre l'état prêt.
2. Demander « Define INR using only the provided local glossary. ».
3. Lire l'extrait, activer son lien puis ouvrir le document complet lié à son SHA.
4. Lire DEMO.md pour une comparaison prudente et la présentation de dix minutes.

La version courante est servie par `pharma-final`, image `pharma-agent:final`,
liée uniquement à localhost. Les autres projets Docker n'ont pas été modifiés.

| Élément | Chemin |
|---|---|
| Archive de sources et preuves | `dist/assignment-pharma-final.zip` |
| Rapport français, architecture et jury | `output/pdf/Rapport_Projet_Pharma.pdf` |
| Guide usager et démonstration | `DEMO.md` |
| Architecture et justification | `ARCHITECTURE.md` |
| Mesures et limites | `VALIDATION.md`, `reports/jury/validation.json` |
| Aperçus réels | `output/preview/desktop.png`, `output/preview/mobile.png` |
| Audit initial, campagnes et relecture | `reports/jury/` |
| Empreintes du paquet | `MANIFEST_SHA256.json` dans l'archive |

L'archive inclut code, 21 documents, tests, verrous, configuration IA, CI,
documentation, rapport et captures. Elle exclut secrets, environnements, caches,
temporaires et énoncé confidentiel. Le générateur vérifie la clé courante et les
empreintes ; cela ne constitue pas un détecteur exhaustif de tout secret.

```powershell
# Dépendances documentaires optionnelles, hors runtime :
uv tool run --from reportlab --with pypdf python scripts/build_report.py
.venv311/Scripts/python.exe scripts/package_delivery.py
```

Les preuves doivent être à jour avant de régénérer le rapport. Les campagnes
initiales et retests restent distincts. Les fichiers du paquet et le corpus sont
contrôlés par empreintes ; toute modification exige une vérification appropriée.

Le dépôt public de remise est
https://github.com/IlyasFardaouix/Pharma-Research-Agent ; voir `docs/PUBLICATION.md`.
Les rapports de validation datés précèdent cette publication et conservent leur
état historique. Une publication Git ne réalise pas l'envoi du lien et du résumé
au contact recrutement ; aucun envoi à un tiers n'a été effectué ici.
