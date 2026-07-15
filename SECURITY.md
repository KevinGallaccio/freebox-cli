# Politique de sécurité / Security policy

> **English:** report vulnerabilities privately via
> [GitHub private vulnerability reporting](https://github.com/KevinGallaccio/freebox-cli/security/advisories/new)
> — never through a public issue. The latest release is the supported one.

## Signaler une vulnérabilité

**N'ouvrez pas d'issue publique.** Utilisez le
[signalement privé de GitHub](https://github.com/KevinGallaccio/freebox-cli/security/advisories/new)
(onglet *Security* → *Report a vulnerability*). Vous recevrez une réponse
sous quelques jours.

## Périmètre

`freebox-cli` s'exécute entièrement en local : il parle à votre Freebox sur
votre LAN et ne contacte aucun service tiers. Les sujets sensibles :

- **Le jeton d'appairage** (`~/.config/fbx/credentials.json`, mode 0600) —
  il donne un contrôle étendu de la box ; toute fuite (logs, sorties,
  fichiers temporaires) est une vulnérabilité.
- **Le serveur MCP** (`fbx mcp serve`) — il expose la box à un agent ;
  contournement du masquage des secrets (`include_secrets`), annotations
  destructrices manquantes ou échappement défaillant sont dans le périmètre.
- **Les données affichées** — les chaînes venant de la box (noms d'hôtes,
  SSID…) sont considérées non fiables et doivent rester échappées.

## Versions supportées

La dernière version publiée ([releases](https://github.com/KevinGallaccio/freebox-cli/releases)).
