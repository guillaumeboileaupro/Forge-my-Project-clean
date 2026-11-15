# Ecriture dans un dossier local (T17)

L'archive ZIP reste disponible. L'ecriture locale est une alternative optionnelle, dans un dossier choisi, apres comparaison et confirmation.

## Parcours
1. Section « Verification et apercu » : verifier la configuration, relire ou editer les fichiers, puis « Valider les modifications ». La partie « Ecrire dans un dossier local » ne s'active qu'ensuite.
2. Choisir le dossier : saisir un chemin absolu, ou « Parcourir ce dossier » puis cliquer les sous-dossiers ; « Dossier parent » remonte. Le dossier peut etre nouveau (il sera cree) ou existant.
3. « Comparer avec la destination » : rien n'est ecrit. Chaque fichier prepare est classe :
   - nouveau : absent de la destination, sera cree ;
   - identique : contenu deja present, laisse tel quel ;
   - conflit : un fichier different existe ; le diff (existant -> prepare) s'affiche en cliquant le fichier ;
   - bloque : lien symbolique, fichier special ou chemin non sur ; l'ecriture est refusee tant que l'entree n'est pas corrigee a la main.
4. Pour chaque conflit, choisir : « Conserver l'existant », « Remplacer » ou « Fusionner manuellement » (zone d'edition pre-remplie avec le fichier existant ; reprendre les ajouts voulus depuis le diff). Aucun fichier n'est jamais ecrase sans decision explicite.
5. Cocher la confirmation, puis « Ecrire les fichiers » et confirmer la boite de dialogue.
6. Le rapport final liste chaque fichier (cree, remplace, fusionne, conserve, identique), l'emplacement de la sauvegarde et les avertissements non bloquants.

Les fichiers du dossier qui ne font pas partie de la generation ne sont jamais lus en dehors des chemins prepares, ni modifies, ni supprimes.

## Racine autorisee
Seuls les sous-dossiers de la racine autorisee sont acceptes : le dossier personnel par defaut, ou la valeur de `FORGE_WRITE_ROOT` au lancement (`FORGE_WRITE_ROOT=/chemin python3 server.py`). La racine elle-meme, le dossier de Forge-my-Project, les chemins relatifs, `.` et `..`, et tout lien symbolique sur le chemin (destination ou fichier cible) sont refuses.

## Garanties
- Controles repetes juste avant l'ecriture : regeneration du plan (avec les verifications en ligne demandees), diagnostics bloquants, ensemble exact des fichiers, contenu edite et fusionne.
- Contenu edite ou fusionne refuse s'il contient un secret reconnaissable (jetons GitHub, AWS, Slack, Google, Stripe, npm, cles privees, cles d'API `sk-`, affectation litterale d'un mot de passe ou d'une cle), s'il change la semantique de `.mcp.json`, `.codex/config.toml` ou des hooks d'agents (seule la mise en forme peut changer), s'il modifie un script de hook ou renomme un skill. Les chemins sensibles (`.env`, `.git/`, cles, `.npmrc`...) sont interdits.
- Validation perimee bloquee : la comparaison delivre un jeton lie au dossier, aux contenus prepares et a l'etat de chaque fichier cible. Si la configuration, une edition, la destination ou un fichier cible change ensuite, l'ecriture est refusee (« Validation perimee ») et il faut comparer a nouveau. Le jeton est propre au serveur en cours : apres un redemarrage, comparer a nouveau.
- Chaque cible est reverifiee juste avant son remplacement ; un fichier modifie pendant l'ecriture annule l'operation.
- Ecriture atomique de chaque fichier : fichier temporaire dans le meme dossier, `fsync`, puis renommage. Droits 0644, 0755 pour `.githooks/` et `scripts/hooks/`.
- Aucun fichier ecrit ou importe n'est execute par Forge-my-Project.

## Sauvegarde et restauration
Avant toute modification, chaque fichier remplace ou fusionne est copie dans `.forge-backup/<horodatage>/` a la racine de la destination, avec `MANIFEST.json` (`replaced`, `created`). Ajouter `.forge-backup/` au `.gitignore` du projet si ce dossier ne doit pas etre versionne ; le supprimer apres verification.

- Echec pendant l'ecriture (disque plein, droits, modification concurrente) : Forge-my-Project restaure automatiquement les fichiers remplaces, supprime les fichiers et dossiers qu'il venait de creer, puis affiche « Ecriture interrompue : modifications annulees ». La sauvegarde est conservee. Si la restauration echoue, le rapport liste les fichiers concernes.
- Annulation manuelle d'une ecriture reussie : depuis la destination,
  ```bash
  B=.forge-backup/<horodatage>
  python3 -c 'import json,sys; print("\n".join(json.load(open(sys.argv[1]))["created"]))' "$B/MANIFEST.json"  # fichiers crees, a supprimer apres relecture
  cp -a "$B/." .  && rm "./MANIFEST.json"                                                              # restaure les fichiers remplaces
  ```
  Relire la liste `created` avant de supprimer ces fichiers.

## Limites
- Linux (teste) et macOS (non teste, memes API POSIX dir_fd et `O_NOFOLLOW`) ; ailleurs, dont Windows, l'ecriture est refusee et le ZIP reste disponible.
- La fusion est manuelle (pas de fusion a trois voies automatique). Un fichier existant binaire ou de plus de 256 Kio ne peut qu'etre conserve ou remplace.
- Les configurations MCP et hooks d'agents existantes ne peuvent pas etre fusionnees avec les fichiers generes : conserver l'existant ou remplacer.
- La detection de secrets repose sur des motifs connus ; elle ne remplace pas Gitleaks, execute par la CI et le hook pre-commit generes.
- Les droits sont verifies avant l'ecriture ; un changement de droits pendant l'ecriture est traite comme un echec avec restauration.
