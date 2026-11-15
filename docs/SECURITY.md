# Modele de securite du generateur

## Risques
- Entree non fiable dans le nom du projet, contenu JSON et descriptions.
- ZIP Slip / sortie d'archive hors racine; verifier chaque chemin genere.
- Injection de commandes lors de hooks et de templates.
- Supply chain: typosquatting, imports inexistants, malwares de packages, versions vulnerables.
- MCP: fuite de secrets, capacites excessives, outils non approuves.
- GitHub Actions: scripts non eprouves, permissions excessives et actions non epinglees.

## Regles bloquantes
- Aucune execution arbitraire depuis les valeurs du formulaire.
- Pas de reseau ou installation de packages sans accord et verification.
- Pas de token ou secret en dur ni de journalisation de secrets.
- Minima de permissions GitHub Actions, revue des actions epinglees aux SHA.
- Verifications CI: tests, syntaxe, analyse des secrets, SAST et SCA lorsque la stack ajoute des dependances.
- CI non executee ou audit impossible => etat NON VERIFIE, jamais PASS.

## Vulnerabilites
Bloquer severites critiques/hautes quand des outils d'audit fiables sont configures. Les outils ne garantissent jamais zero vulnerabilite. Suivre les exceptions motivees et datees; ne pas masquer les alertes.

## Donnees locales du questionnaire (T05)
- Brouillon: `localStorage` du navigateur (cle `forge-my-project.draft.v1`), revalide par le serveur avant restauration; un brouillon incompatible est supprime, jamais applique.
- Profils personnels: `$FORGE_PROFILES_FILE`, sinon `$XDG_CONFIG_HOME/forge-my-project/profiles.json`, sinon `~/.config/forge-my-project/profiles.json`; dossier 0700, fichier 0600, ecriture atomique, liens symboliques et fichiers illisibles refuses sans ecrasement. Aucun nom ni description de projet n'y est stocke.
- Import JSON: 64 Kio maximum, `JSON.parse` uniquement, validation serveur integrale avant application; affichage par `textContent`.
- Ne pas stocker de secret dans les reponses: elles sont enregistrees en clair.

## Skills externes (T10)
- Aucun skill externe n'est copie sans approbation explicite dans l'interface (confirmation supplementaire pour une source non reconnue).
- L'approbation epingle depot, commit et empreinte SHA-256 de l'arborescence du skill ; tout changement depuis l'approbation est une erreur bloquante, et chaque fichier telecharge est compare au SHA de son blob Git.
- Seuls des fichiers texte (.md, .yaml, .yml, .json, .txt) sont copies ; scripts, binaires, liens et executables sont ignores, jamais telecharges ni executes.
- Les approbations importees (JSON, profil, brouillon) sont revalidees par le serveur et peuvent etre controlees en ligne avant generation.

## Serveurs MCP des projets generes (T15)
- Aucun serveur sans selection explicite ; uniquement des serveurs du catalogue verifie et pertinents pour la configuration.
- Aucun secret genere : references a des variables d'environnement uniquement ; lecture seule et ensembles d'outils limites pour GitHub ; version epinglee et profil isole pour Playwright.
- Provenance controlee dans le registre MCP officiel (actif, depot, transport) lors de la verification en ligne ; un ecart bloque la generation.

## Controles de ce depot (T13)
- Job CI `security`: Gitleaks sur tout l'historique et Bandit (severite >= medium) sur forge/, server.py et generator.py, avec les memes versions epinglees que les projets generes (alignement verifie par tests/test_repo_ci.py).
- Job CI `generated-projects`: CI generee des profils predefinis executee, puis preuve de detection des controles de securite (tests/smoke_security.py).


## Ecriture locale (T17)
- Destination limitee aux sous-dossiers de `FORGE_WRITE_ROOT` (sinon le dossier personnel), hors dossier de Forge-my-Project; chemins absolus normalises uniquement; chaque composant ouvert par descripteur avec O_NOFOLLOW (liens symboliques refuses, y compris s'ils apparaissent apres la verification).
- Aucune ecriture sans comparaison, decision explicite pour chaque conflit et confirmation; jeton HMAC (cle propre au processus) liant destination, contenus et etat des cibles : toute validation perimee est refusee.
- Sauvegarde des fichiers remplaces avant modification (`.forge-backup/`, 0600), ecriture atomique, reverification de chaque cible, rollback automatique sur echec.
- Contenu edite ou fusionne : motifs de secrets bloquants, configurations MCP et hooks d'agents figees (mise en forme seule), scripts de hooks non modifiables, nom de skill conserve, chemins sensibles interdits. Aucun fichier ecrit n'est execute.
