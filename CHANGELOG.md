# Changelog

Les notes de version complètes sont sur la page
[Releases](https://github.com/KevinGallaccio/freebox-cli/releases) ; ce fichier
résume ce qui change pour l'utilisateur.

## 0.8.1

**Correctif : le serveur MCP plantait au démarrage avec mcp 2.x.**

Depuis début août, `uvx --from freebox-cli[mcp] fbx mcp serve` (ce que lance
Claude Desktop) récupérait le SDK `mcp` 2.x, qui a supprimé les décorateurs
`@server.list_tools()` / `@server.call_tool()` du serveur bas niveau. Le
serveur échouait avec `'Server' object has no attribute 'list_tools'` avant
même de lister un outil.

- `fbx mcp serve` fonctionne maintenant avec mcp 1.x **et** 2.x : même
  construction des outils, même dispatch, seule l'inscription des handlers
  change selon le SDK installé.
- Avec mcp 2.x, une erreur d'outil (« outil inconnu », « pas appairé ») reste
  un résultat `isError` lisible par le modèle au lieu de devenir une erreur de
  protocole JSON-RPC.
- L'extra est borné : `freebox-cli[mcp]` demande `mcp>=1.2,<3`.
- Test de régression : le serveur est lancé en sous-processus et on lui parle
  en stdio (initialize → tools/list → tools/call). La CI tourne désormais
  contre mcp `<2` et `>=2,<3`.
