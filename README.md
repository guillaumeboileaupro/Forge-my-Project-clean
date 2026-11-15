# Forge-my-Project

Generateur interactif de projets GitHub - version initiale.

## Demarrage

Python 3.11+ uniquement, sans dependances externes.

```bash
python3 server.py
```

Ouvrir http://127.0.0.1:8765 dans Firefox : formulaire par sections (projet, technologies, agents, securite, skills externes, verification), apercu des fichiers generes puis telechargement de l'archive ZIP. Les controles en ligne (registres, my-skills) sont des cases a cocher explicites ; les skills externes sont recherches a la demande et copies uniquement apres approbation, au commit et a l'empreinte approuves. L'ancien formulaire reste disponible sur http://127.0.0.1:8765/legacy.

Les reponses sont sauvegardees automatiquement dans le navigateur et restaurees a la reouverture. Des profils predefinis (Python API/CLI/bibliotheque/Django, TypeScript React/Express) et des profils personnels (stockes dans `~/.config/forge-my-project/profiles.json`) se chargent dans le questionnaire; les reponses s'exportent et s'importent en JSON valide par le serveur.

## Tests

```bash
python3 -m unittest discover -s tests -v
FORGE_E2E=1 python3 -m unittest tests.test_e2e_firefox -v   # recette Firefox headless (geckodriver requis)
```

## Architecture

`generator.py` reste la facade compatible. La validation et la generation historiques sont isolees sous `forge/`, le formulaire sous `ui/` et ses textes generes sous `templates/legacy/`. Les interfaces stables et les zones reservees au developpement parallele sont documentees dans `docs/CONTRACTS.md`.

## Moteur technique (apercu, sans ecriture)

```bash
python3 -m forge plan spec.json             # diagnostics et fichiers prevus
python3 -m forge plan spec.json --verify    # + verification registres/OSV (reseau)
python3 -m forge show spec.json AGENTS.md   # contenu d'un document rendu
```

Voir docs/ENGINE.md.

## Portee de cette version

Genere un AGENTS.md, des skills, de la documentation d'architecture, des regles de securite et un squelette de CI en fonction du langage, de l'agent et du deploiement. Les packages et integrations MCP sont des recommandations a valider et ne sont pas installes automatiquement. Ne garantit pas qu'un projet genere est exempt de vulnerabilites.

## Regles

- Une seule PR ouverte pour le developpement dirige par agent.
- Ne jamais inventer de package ou d'API.
- Bloquer l'utilisation de secrets en clair.
- Ne pas fusionner sans tests, verification des dependances et revue de securite.
