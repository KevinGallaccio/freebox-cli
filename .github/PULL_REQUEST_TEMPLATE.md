<!-- English is fine too — use the language you prefer. -->

## Quoi et pourquoi

<!-- Ce que change cette PR, et le problème qu'elle règle. Liez l'issue le cas échéant. -->

## Liste de contrôle

- [ ] `uv run pytest` passe (hors ligne — la box est mockée)
- [ ] `uv run ruff check src tests scripts` est propre
- [ ] Les **écritures** testent le **corps de la requête** (`sent_json`/`sent_form`)
- [ ] Les fixtures n'utilisent que des **données fictives** (IP `192.0.2.x`, MAC `02:…`)
- [ ] La logique vit dans `core/` ; les adaptateurs (CLI/MCP/app) restent minces
- [ ] Action destructrice → confirmation (`ui.confirm` / `ConfirmModal` / `destructiveHint`)
- [ ] README/doc à jour si le comportement visible change
- [ ] Pas de bump de version (les mainteneurs le font au moment de la release)
