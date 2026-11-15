# Forge-my-Project

Outil local qui prepare l'environnement de developpement d'un nouveau projet (AGENTS.md, skills, documentation, hooks, CI, securite, MCP optionnels) a partir d'un questionnaire dans Firefox. Sans IA embarquee, sans code metier, sans creation ni push de depot.

## Demarrage

Python 3.11+ uniquement, sans dependances externes.

```bash
python3 server.py
```

Ouvrir http://127.0.0.1:8765 dans Firefox : formulaire par sections (projet, technologies avec recherche, agents, securite, skills et MCP, verification), suggestion d'architecture modifiable, confirmation explicite des avertissements, explorateur des fichiers generes, edition et validation des contenus, puis telechargement de l'archive ZIP ou ecriture dans un dossier local. Les fichiers modifies sont signales et peuvent etre retablis avant validation ; le contenu edite est controle (secrets, configurations MCP et hooks, skills). L'ecriture locale compare d'abord le dossier choisi (nouveau, identique, conflit avec diff), demande une decision pour chaque conflit (conserver, remplacer, fusionner) et une confirmation, sauvegarde les fichiers remplaces dans `.forge-backup/` et annule tout en cas d'echec : voir docs/LOCAL_WRITE.md (operations et restauration). Les controles en ligne (registres, my-skills) sont des cases a cocher explicites ; les skills externes sont recherches a la demande et copies uniquement apres approbation, au commit et a l'empreinte approuves. L'ancien formulaire reste disponible sur http://127.0.0.1:8765/legacy.

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

Genere un AGENTS.md detaille, des skills, la documentation (architecture, plan, TODO, securite, tests, dependances, ADR, contribution avec la commande de protection de branche), des hooks Git et d'agents et une CI GitHub Actions operationnelle (executee pour les six profils predefinis par la CI de ce depot), selon les technologies, les agents et les options choisis. Les serveurs MCP ne sont configures que sur selection explicite (catalogue verifie, permissions minimales, aucun secret) et ne sont ni installes ni demarres par l'outil. Ne garantit pas qu'un projet genere est exempt de vulnerabilites.

## Plateformes et configuration

- Linux : teste (unitaires, integration, recette Firefox headless, recette finale T18). macOS : non teste ; l'ecriture locale repose sur des API POSIX disponibles (dir_fd, O_NOFOLLOW). Windows : non teste ; l'ecriture locale y est refusee, le ZIP reste disponible.
- `FORGE_WRITE_ROOT` : racine autorisee pour l'ecriture locale (defaut : dossier personnel). `FORGE_PROFILES_FILE` ou `XDG_CONFIG_HOME` : emplacement des profils personnels.
- Exigences, preuves et recette : docs/TRACEABILITY.md et docs/ACCEPTANCE.md.

## Regles

- Une seule PR ouverte pour le developpement dirige par agent.
- Ne jamais inventer de package ou d'API.
- Bloquer l'utilisation de secrets en clair.
- Ne pas fusionner sans tests, verification des dependances et revue de securite.
