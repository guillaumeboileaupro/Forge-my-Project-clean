# Attribution Git - regle obligatoire

Ce depot appartient a son proprietaire. Codex, Claude Code et les autres assistants sont des outils, pas des contributeurs a crediter dans Git ou GitHub.

- Auteur et committer des commits : uniquement l'identite Git choisie par le proprietaire.
- Interdit dans les messages de commit, descriptions de PR et squash merges : `Co-Authored-By` attribuant une contribution a Claude, Anthropic, Codex ou a un autre agent; mentions automatiques `Generated with Claude Code` ou equivalentes.
- Les noms d'agents restent autorises dans la documentation technique lorsqu'ils decrivent la configuration, les hooks ou les agents compatibles. Cette politique concerne l'attribution des contributions, pas la documentation.
- La configuration `.claude/settings.json` desactive l'attribution automatique. Verifier le message final avant chaque commit et chaque PR.

## Historique a reparer

Deux commits de main portent actuellement le trailer `Co-Authored-By: Claude <noreply@anthropic.com>` :

- `11d0f4ca058da0f5f54fcd636c1e746c6a7280e5` (T10)
- `e71a9507fe2ecddf85c0608cae00b5df0332665f` (T15)

Leur auteur et leur committer Git sont deja le proprietaire. Nettoyer le texte de leurs messages implique de reecrire ces commits et tous leurs descendants, ce qui change les SHA. Cela ne peut pas etre fait par une PR classique. Cette operation requiert une sauvegarde de toutes les refs, l'inventaire des tags et branches, la coordination de tous les clones et worktrees, une reecriture controlee puis un push force explicite. Ne pas tenter cette operation automatiquement pendant une PR courante.

Commande d'audit : `git log --all -i --format='%H %an <%ae> %cn <%ce>%n%B' | grep -i -E 'co-authored-by|noreply@anthropic.com'`.
