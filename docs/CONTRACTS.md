# Contrats techniques

Statut: contrats de transition etablis par T02. Ils preservent le prototype T01 et permettent aux composants T06-T11 d'evoluer independamment.

## Principes
- Les donnees traversant une frontiere sont revalidees par le composant receveur.
- La generation pure ne fait ni ecriture disque, ni reseau, ni execution de commande.
- Les chemins de templates et de sortie sont relatifs, sans composant `..` ni chemin absolu.
- Un changement incompatible exige un ADR, des tests de migration et une mise a jour de ce document.

## Interface utilisateur -> serveur
- `GET /` retourne le formulaire hybride `ui/index.html` (moteur `forge/`); `GET /legacy` retourne le formulaire historique `ui/legacy.html`. Seuls les assets connus sont servis: `/css/app.css`, `/js/app.js`, `/js/legacy.js`.
- `GET /api/catalog` retourne categories, technologies, agents, types de projet, niveaux de securite, options et serveurs MCP proposes (`mcp_servers` : besoin, pertinence, provenance, licence, execution, variable du jeton, permissions) (lecture seule).
- `POST /api/plan` accepte `{"config": <schema moteur v1>, "verify": bool, "skills": bool}` (1 a 65 536 octets, `Host` et `Origin` loopback) et retourne diagnostics, rapports et contenu des fichiers.
- `POST /api/files/validate` accepte en plus `"files": {<chemin>: <texte>}` (2 500 000 octets de requete maximum). Le serveur regenere le plan et exige exactement les memes chemins, des textes UTF-8 sans NUL, 256 Kio maximum par fichier et 2 Mio au total. Il retourne la liste des chemins modifies; aucune ecriture n'a lieu.
- `POST /api/archive` accepte le meme champ `files` optionnel et repete generation, controles et validation des editions avant de retourner le ZIP. Diagnostic bloquant: 422; edition ou schema invalide: 400; erreur imprevue: 500 sans detail. Voir docs/ENGINE.md.
- `POST /api/answers/validate` accepte `{"document": <export JSON ou reponses>}` et retourne les reponses normalisees ou 400 avec un message lisible. Reponses partielles admises (brouillon), mais tout champ inconnu, type invalide, technologie hors catalogue, prerequis manquant, conflit ou version non supportee est refuse.
- `GET /api/profiles` (profils predefinis + personnels, `Host` loopback), `POST /api/profiles`, `PUT /api/profiles/<id>`, `DELETE /api/profiles/<id>` : corps `{"label", "description", "answers"}`; 404 si absent, 400 si invalide ou predefini.
- `POST /api/skills/search` accepte `{"config": <schema moteur v1>}` et retourne `{"ok", "candidates", "notes"}` ; chaque candidat porte nom, description, provenance, commit, empreinte, fichiers copies/ignores, notes et la valeur `approval` a ajouter a `external_skills`. Acces reseau GitHub explicite ; rien n'est copie ni execute. Configuration invalide : 400/422.
- `POST /api/skills/verify` accepte `{"approvals": [...]}` et retourne `{"ok", "checks"}` avec un statut PASS / FAIL / NON VERIFIE par approbation (empreinte recalculee au commit approuve). Approbation mal formee : 400.
- Format d'export: `{"format": "forge-my-project/answers", "schema_version": 1, "answers": {...}}`. Les valeurs sont des donnees, jamais executees.
- `POST /generate` (historique) accepte `Content-Type: application/json`, 1 a 16 384 octets, depuis un `Host` (et un `Origin` s'il est present) loopback autorise.
- Corps historique: objet avec `name`, `description`, `language`, `agent`, `deployment`, `security` et `one_pr`. Aucun champ inconnu n'est accepte.
- Succes: HTTP 200, `application/zip`, nom de fichier derive du nom valide. Erreur client: HTTP 400, 403, 404 ou 415 avec un texte sans secret.
- Le navigateur n'est jamais une source de confiance; ses contraintes HTML ne remplacent pas la validation Python.

## Serveur -> validation
- Point stable: `generator.validate(data) -> dict`.
- Implementation T02: `forge.config.legacy.validate` reexportee par la facade.
- Le dictionnaire retourne contient tous les champs historiques, des valeurs appartenant aux ensembles `OPTIONS`, une description normalisee et un booleen `one_pr` reel.
- Une entree invalide leve `ValueError`; le serveur la transforme en HTTP 400 sans corriger silencieusement la configuration.
- Le schema moderne de Claude peut etre plus riche, mais un adaptateur explicite est requis avant de remplacer ce contrat.

## Validation -> generation
- Point stable: `generator.build(config) -> dict[str, str]`.
- `build` revalide toujours `config`; un appel direct ne contourne donc pas la frontiere de confiance.
- Les cles sont des chemins POSIX relatifs au futur dossier projet. Les valeurs sont des textes UTF-8 termines par un saut de ligne.
- La fonction est deterministe et sans effet de bord.

## Generation -> templates externes
- Bibliotheque de compatibilite: `templates/legacy/`, lecture seule pendant un rendu.
- Moteur minimal: marqueurs `{{ nom }}` simples, liste de valeurs fournie par le code, variable absente bloquante.
- Le remplacement est effectue en un passage: un marqueur fourni par l'utilisateur reste une donnee et n'est jamais reevalue.
- `forge.generator.legacy.render_template` refuse les chemins absolus et la traversee `..`.
- Les futurs templates de Claude restent separes de `templates/legacy/` jusqu'a ce qu'une comparaison de sorties et une migration de facade soient validees.

## Generation -> archive
- Point stable: `generator.generate(config) -> bytes`.
- Le ZIP est construit en memoire. Chaque entree est prefixee par le nom de projet valide et issue de `build`.
- Aucun fichier local n'est ecrit et aucun script genere n'est execute par l'application.
- L'ordre des entrees est stable (`sorted`) pour faciliter les tests et les comparaisons.

## Ecriture de fichiers
- T16 implemente uniquement la preparation en memoire: arbre, edition, indication des changements, restauration du contenu genere et validation par `forge.filesystem.preview.validate_preview`.
- Interactions T10/T15/T16: les fichiers des skills approuves et des serveurs MCP selectionnes sont editables comme les autres, mais ne peuvent etre ni ajoutes ni retires depuis l'editeur; un skill modifie depuis son approbation bloque l'archive (422) meme avec des editions; toute modification de la configuration ou des approbations desactive le telechargement jusqu'a une nouvelle verification.
- Le telechargement ZIP reste la seule sortie. L'ensemble des chemins doit etre strictement identique au rendu regenere cote serveur; un ajout, une suppression ou un chemin non sur est refuse.
- T17 ajoutera comparaison avec une destination, diff, fusion, confirmation, sauvegarde et rollback. Cette ecriture devra rester independante du transport HTTP et du moteur de templates.

## Points d'entree compatibles
- `python3 server.py` et `http://127.0.0.1:8765`.
- Imports historiques: `from generator import OPTIONS, validate, build, generate, skill`.
- Commandes de test generees: unittest pour Python et `npm test` pour JavaScript.
- Contrat ZIP et contenu des 64 configurations historiques inchanges apres T02.

## Coordination Claude Code
- Claude possede T06-T11: catalogues, compatibilites, rules/planner, generation moderne, skills et verification des dependances.
- Codex n'edite pas ces composants dans T02. Les modules `legacy` et `templates/legacy` sont une couche de compatibilite, pas une seconde implementation du moteur cible.
- Integration attendue: conserver la facade; adapter l'entree historique vers le schema moderne; comparer les fichiers produits; basculer seulement apres tests verts.
