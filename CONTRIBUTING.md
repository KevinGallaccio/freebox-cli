# Contribuer à freebox-cli

> **English speakers:** the project is French-first (the Freebox only exists
> in France), but contributions in English are perfectly welcome — open your
> issues and PRs in the language you're comfortable with. The rules below
> are summarized at the [bottom of this file](#english-summary).

Merci de votre intérêt ! Ce dépôt est prêt à recevoir des contributions :
tout se teste **hors ligne** (la box est mockée), la CI est rapide, et les
règles tiennent en une page.

## Démarrer

Il faut [`uv`](https://astral.sh/uv) — et c'est tout. **Pas besoin de
Freebox** : la suite de tests mocke entièrement la box.

```sh
git clone https://github.com/KevinGallaccio/freebox-cli
cd freebox-cli
./fbx --version         # le shim amorce uv et lance la CLI depuis les sources

uv sync                 # dépendances + outils de dev
uv run pytest           # ~370 tests, entièrement hors ligne
uv run ruff check src tests scripts
```

## L'architecture en trois phrases

- **Toute la logique vit dans `src/fbx/core/`** — une fonction par endpoint,
  qui prend un `FbxClient` et rend le `result` déballé. C'est la seule
  couche qui parle à la box.
- **La CLI (`cli/`), le serveur MCP (`mcp/`) et l'application (`tui/`) sont
  trois adaptateurs minces** au-dessus du même cœur. Une fonctionnalité se
  code dans `core/`, puis s'expose dans les adaptateurs concernés.
- **stdout = données, stderr = interface.** Cette règle est structurante :
  messages, spinners, invites et erreurs vont sur stderr ; `--json` doit
  rester pipable partout.

## Les règles qui comptent

1. **Tests hors ligne uniquement** (respx). Pour une **écriture**, testez le
   **corps de la requête envoyée** (`sent_json`/`sent_form` dans
   `tests/helpers.py`) — c'est le contrat, pas seulement la réponse.
2. **Données fictives uniquement** dans les tests et la doc : IP en
   `192.0.2.x` (TEST-NET), MAC localement administrées (`02:…`), jamais de
   vrais SSID/MAC/IP/numéros. Le dépôt est public.
3. **Ne lancez jamais `fbx auth login` depuis du code de test** hors des
   fixtures pytest — l'isolation (`conftest.py`) protège le vrai jeton
   d'appairage de la machine.
4. **Les gardes anti-dérive doivent rester vertes** : chaque fonction
   publique de `core.api` doit être exposée (ou explicitement exclue) côté
   MCP ; la version est vérifiée dans **trois fichiers** (`pyproject.toml`,
   `src/fbx/__init__.py`, `.claude-plugin/plugin.json`).
5. **ruff propre** (ligne à 100 colonnes) ; commits de style conventionnel
   (`feat:`, `fix:`, `docs:`…).
6. Les actions destructrices (reboot, suppression, Wi-Fi off…) passent par
   une **confirmation** (CLI : `ui.confirm` + `--yes` ; app :
   `ConfirmModal` ; MCP : annotation `destructiveHint`).

## Proposer un changement

1. Ouvrez une issue (modèles fournis) pour discuter si le changement est
   substantiel.
2. Branche → commits → PR vers `main`. **`main` est protégée** : tout passe
   par une PR avec la CI verte, mainteneur compris.
3. Une fonctionnalité = core + adaptateur(s) + tests + doc si visible.

## Publier une version (mainteneur)

Bump de version dans les trois fichiers, puis :

```sh
git tag vX.Y.Z && git push origin vX.Y.Z
```

Le workflow fait le reste : tests → build → PyPI (Trusted Publishing) →
release GitHub → mise à jour de la formule Homebrew.

## Sécurité

Une faille ? **Pas d'issue publique** — voir [SECURITY.md](SECURITY.md).

---

## English summary

Everything runs offline (`uv sync && uv run pytest` — the box is mocked, no
Freebox needed). All logic lives in `src/fbx/core/`; the CLI, MCP server,
and terminal app are thin adapters over it. stdout is data, stderr is UI.
Write-operation tests must assert the **request body** (`sent_json` in
`tests/helpers.py`). Test data must be fictional (TEST-NET IPs,
locally-administered MACs) — the repo is public. `main` is protected:
branch → PR → green CI, maintainer included. Security issues go through
private reporting, never public issues.
