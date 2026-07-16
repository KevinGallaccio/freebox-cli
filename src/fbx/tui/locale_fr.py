"""The French catalog: every user-visible app string, keyed by its English.

Terminology follows Freebox OS 4.12's own French — pulled verbatim from the
box's `resources/lang/fra.json` where a term exists (« Gestion des ports »,
« Baux statiques », « Journal d'appels », « Allumé »/« Éteint » for VMs,
« Allumée depuis » for uptime, « Version du micrologiciel »…). Typography
follows it too: real apostrophes (’), « guillemets », and a
NON-BREAKING space (U+00A0 — invisible here, deliberate) before ?, !, :, ;
and % and inside « ». Keep them when editing: the drift-guard tests check
the catalog against the source, and a punctuation test checks the spaces.

Keys that map to themselves are reviewed-and-identical, not omissions — the
suite enforces that every wrapped string has an entry, so the catalog reads
as the complete inventory. Keys of the form "context|value" translate raw
box statuses (`i18n._p`); unknown wire values fall through untranslated.
"""

CATALOG: dict[str, str] = {
    # ---------- generic verbs & modal chrome --------------------------------
    "Quit": "Quitter",
    "Back": "Retour",
    "Refresh": "Actualiser",
    "Language": "Langue",
    "Yes": "Oui",
    "No": "Non",
    "Confirm": "Valider",
    "Save": "Sauvegarder",
    "Apply": "Appliquer",
    "Add": "Ajouter",
    "Delete": "Supprimer",
    "Edit": "Modifier",
    "Create": "Créer",
    "Rename": "Renommer",
    "Remove": "Retirer",
    "Run": "Exécuter",
    "Start": "Démarrer",
    "Close": "Fermer",
    "Cancel": "Annuler",
    "Cancel (n)": "Annuler (n)",
    "Cancel (esc)": "Annuler (esc)",
    "esc to close": "esc pour fermer",
    "Complete": "Compléter",
    "History": "Historique",
    "Box error": "Erreur Freebox",
    # ---------- domain registry (dashboard menu) ----------------------------
    "Top": "Top",
    "live throughput and sensors": "débits et capteurs en direct",
    "Connection": "Connexion",
    "WAN, fiber, IPv6, logs": "WAN, fibre, IPv6, journaux",
    "Wi-Fi": "Wi-Fi",
    "radios, networks, clients": "radios, réseaux, clients",
    "Devices": "Périphériques réseau",
    "who's on the network": "qui est sur le réseau",
    "DHCP": "DHCP",
    "leases and reservations": "baux actifs et baux statiques",
    "Port forwarding": "Gestion des ports",
    "rules, DMZ, UPnP": "redirections, DMZ, UPnP",
    "Downloads": "Téléchargements",
    "the download manager": "le gestionnaire de téléchargements",
    "Files": "Explorateur de fichiers",
    "browse the box's disks": "parcourir les disques de la Freebox",
    "Storage": "Disques",
    "disks and partitions": "disques et partitions",
    "Virtual machines": "VMs",
    "lifecycle, console, exec": "cycle de vie, console, exécution",
    "Phone": "Téléphonie",
    "call log": "journal d’appels",
    "Contacts": "Contacts",
    "address book": "carnet d’adresses",
    "System": "Système",
    "firmware, sensors, reboot": "micrologiciel, capteurs, redémarrage",
    # ---------- splash & dashboard ------------------------------------------
    "press any key": "appuyez sur une touche",
    "Go to": "Navigation",
    "Suggestions": "Suggestions",
    "{name} ch {channel} · {state}": "{name} canal {channel} · {state}",
    "no radios": "aucune radio",
    "{n} active on the LAN": "{n} actifs sur le réseau",
    "none defined": "aucune VM",
    "{label} {pct}% of {total}": "{label} {pct} % de {total}",
    "no disks": "aucun disque",
    "{n} task(s), {active} active": "{n} tâche(s), {active} active(s)",
    "{n} new missed call(s)": "{n} appel(s) manqué(s) non lu(s)",
    "no new calls": "aucun nouvel appel",
    "firmware {version}": "micrologiciel {version}",
    "up {uptime}": "allumée depuis {uptime}",
    "Nothing pressing — the box looks tidy.": "Rien d’urgent — la Freebox se porte bien.",
    "The {key} screen lands later in Phase 6.": (
        "L’écran {key} arrivera dans une phase ultérieure."
    ),
    # ---------- suggestions --------------------------------------------------
    "WAN is not up — inspect the connection logs": (
        "La connexion Internet est coupée — consultez les journaux de connexion"
    ),
    "Wi-Fi WPS is enabled — a known attack surface; consider disabling it": (
        "Le WPS Wi-Fi est activé — une surface d’attaque connue ; pensez à le désactiver"
    ),
    "{n} finished download(s) — clean up the list": (
        "{n} téléchargement(s) terminé(s) — faites le ménage dans la liste"
    ),
    "{n} download(s) in error — inspect them": (
        "{n} téléchargement(s) en erreur — examinez-les"
    ),
    "VM '{name}' is stopped — start it?": (
        "La VM « {name} » est éteinte — la démarrer ?"
    ),
    "Partition '{label}' is {pct}% full — free up space": (
        "La partition « {label} » est pleine à {pct} % — libérez de l’espace"
    ),
    "{n} new missed call(s) — review the log": (
        "{n} appel(s) manqué(s) non lu(s) — consultez le journal"
    ),
    "{n} active device(s) without a name — label them": (
        "{n} périphérique(s) actif(s) sans nom — nommez-les"
    ),
    # ---------- box errors (support.human_error) -----------------------------
    "Not paired with the box — quit and run `fbx auth login` in a terminal.": (
        "Non associé à la Freebox — quittez puis lancez `fbx auth login` "
        "dans un terminal."
    ),
    "Missing the '{scope}' permission — grant it in Freebox OS → "
    "Gestion des accès → Applications → fbx.": (
        "Permission « {scope} » manquante — accordez-la dans Freebox OS → "
        "Gestion des accès → Applications → fbx."
    ),
    "The box refused: {code}: {msg}": "La Freebox a refusé : {code} : {msg}",
    "API error": "erreur API",
    "Can't reach the box: {error}": "Freebox injoignable : {error}",
    # ---------- shared table headers -----------------------------------------
    "Name": "Nom",
    "Band": "Bande",
    "Signal": "Signal",
    "Rate ↓/↑": "Débit ↓/↑",
    "Type": "Type",
    "State": "État",
    "Status": "Statut",
    "Comment": "Commentaire",
    "Description": "Description",
    "Source": "Source",
    "Duration": "Durée",
    # ---------- top -----------------------------------------------------------
    "↓ down": "↓ descendant",
    "↑ up": "↑ montant",
    "(peak {rate})": "(max {rate})",
    "Wi-Fi clients": "Clients Wi-Fi",
    # ---------- connection ----------------------------------------------------
    "Fiber": "Fibre",
    "Logs": "Journaux",
    "When": "Date",
    "Link": "Lien",
    "rate     ↓ {down}   ↑ {up}": "débit    ↓ {down}   ↑ {up}",
    "link     ↓ {down}   ↑ {up}": "lien     ↓ {down}   ↑ {up}",
    "total    ↓ {down}   ↑ {up}": "total    ↓ {down}   ↑ {up}",
    "WAN ping": "ping WAN",
    "remote access": "accès à distance",
    "WOL proxy": "proxy Wake on LAN",
    "API domain": "domaine API",
    "link": "lien",
    "power   rx {rx}   tx {tx}": "optique  rx {rx}   tx {tx}",
    "signal  {signal}": "signal   {signal}",
    "prefix {prefix} → next hop {next_hop}": "préfixe {prefix} → next hop {next_hop}",
    "Toggle WAN ping": "Basculer le ping WAN",
    "WAN ping responses enabled.": "Réponses au ping WAN activées.",
    "WAN ping responses disabled.": "Réponses au ping WAN désactivées.",
    # ---------- wifi ----------------------------------------------------------
    "Radios": "Radios",
    "Networks": "Réseaux",
    "Clients": "Clients",
    "MAC filter": "Filtrage MAC",
    "Radio": "Radio",
    "Channel": "Canal",
    "Width": "Largeur",
    "Enabled": "Activé",
    "Security": "Sécurité",
    "AP": "Radio",
    "Connected": "Durée",
    "Show key": "Afficher la clé",
    "Neighbor survey": "Scan des voisins",
    "Temp-disable…": "Coupure temporaire…",
    "Wi-Fi on/off": "Wi-Fi marche/arrêt",
    "WPS on/off": "WPS marche/arrêt",
    "Add MAC filter": "Ajouter un filtre MAC",
    "Delete filter": "Supprimer le filtre",
    "Wi-Fi passphrase": "Clé Wi-Fi",
    "No Wi-Fi key to show.": "Aucune clé Wi-Fi à afficher.",
    "Scanning neighbors from AP {ap}…": "Scan des réseaux voisins depuis la radio {ap}…",
    "What AP {ap} hears — {n} network(s)": (
        "Ce que la radio {ap} entend — {n} réseau(x)"
    ),
    "(hidden)": "(masqué)",
    "Temporarily disable Wi-Fi": "Couper temporairement le Wi-Fi",
    "Minutes": "Minutes",
    "Band to keep up (optional)": "Bande à garder active (facultatif)",
    "Disable": "Couper",
    "Minutes must be a number.": "Les minutes doivent être un nombre.",
    " (keeping {band})": " (en gardant {band})",
    "Disable Wi-Fi for {minutes} min{kept}? If this machine is on Wi-Fi "
    "you WILL lose it until the timer ends.": (
        "Couper le Wi-Fi pendant {minutes} min{kept} ? Si cette machine est en "
        "Wi-Fi, vous la perdrez jusqu’à la fin du délai."
    ),
    "Disable Wi-Fi": "Couper le Wi-Fi",
    "Wi-Fi disabled for {minutes} min{kept}.": "Wi-Fi coupé pendant {minutes} min{kept}.",
    "Turn Wi-Fi OFF globally? If this machine is on Wi-Fi you will lose it.": (
        "Couper le Wi-Fi entièrement ? Si cette machine est en Wi-Fi, "
        "vous perdrez la connexion."
    ),
    "Turn off": "Couper",
    "Wi-Fi enabled.": "Wi-Fi activé.",
    "Wi-Fi disabled.": "Wi-Fi désactivé.",
    "WPS enabled.": "WPS activé.",
    "WPS disabled.": "WPS désactivé.",
    "New MAC filter entry": "Nouvelle règle de filtrage MAC",
    "MAC address": "Adresse MAC",
    "Comment (optional)": "Commentaire (facultatif)",
    "Delete the {type} entry for {mac}?": (
        "Supprimer la règle « {type} » pour {mac} ?"
    ),
    # ---------- lan -----------------------------------------------------------
    "All/active": "Tous/actifs",
    "Wake (WoL)": "Réveil réseau",
    "Last seen": "Dernière activité",
    "{n} host(s) — {scope}": "{n} périphérique(s) — {scope}",
    "all known": "tous les connus",
    "active": "actifs",
    "Rename device": "Renommer le périphérique",
    "No MAC for this host.": "Pas d’adresse MAC pour ce périphérique.",
    "Wake-on-LAN sent to {mac}.": "Demande de réveil envoyée à {mac}.",
    # ---------- dhcp ----------------------------------------------------------
    "Reserve IP": "Réserver une IP",
    "Static reservations": "Baux statiques",
    "Active leases": "Baux actifs",
    "Hostname": "Nom d’hôte",
    "Assigned": "Attribué",
    "Remaining": "Restant",
    "Static": "Statique",
    "range": "plage",
    "yes": "oui",
    "no": "non",
    "Reserve an IP": "Réserver une IP",
    "IPv4 address": "Adresse IPv4",
    "Reserve": "Réserver",
    "Reserved {ip} for {mac}.": "{ip} réservée pour {mac}.",
    "Edit reservation": "Modifier le bail",
    "Delete the reservation of {ip} for {mac}?": (
        "Retirer le bail statique de {ip} pour {mac} ?"
    ),
    # ---------- port forwarding -----------------------------------------------
    "Add rule": "Ajouter une redirection",
    "Enable/disable": "Activer/désactiver",
    "DMZ…": "DMZ…",
    "Port forwards": "Redirections",
    "Incoming services": "Services entrants",
    "On": "Actif",
    "Proto": "Proto",
    "WAN port": "Port WAN",
    "Service": "Service",
    "Port(s)": "Port(s)",
    "New port forward": "Nouvelle redirection de port",
    "LAN IP": "IP LAN",
    "LAN port": "Port LAN",
    "WAN port (this box allows 16384-32767)": (
        "Port WAN (cette box autorise 16384-32767)"
    ),
    "Protocol": "Protocole",
    "Forward": "Rediriger",
    "Ports must be numbers.": "Les ports doivent être des nombres.",
    "Forwarded WAN {wan} → {ip}:{port}.": "Redirection WAN {wan} → {ip}:{port} créée.",
    "Delete the forward WAN {wan} → {ip}:{port}?": (
        "Supprimer la redirection WAN {wan} → {ip}:{port} ?"
    ),
    "DMZ host (leave empty to disable)": "Hôte DMZ (laisser vide pour désactiver)",
    "Expose {ip} to the whole internet as the DMZ host?": (
        "Exposer {ip} à tout Internet comme hôte DMZ ?"
    ),
    "Expose": "Exposer",
    "DMZ updated.": "DMZ mise à jour.",
    # ---------- downloads -----------------------------------------------------
    "Add URL/magnet": "Ajouter URL/magnet",
    "Pause/resume": "Pause/reprise",
    "Remove task": "Retirer la tâche",
    "Erase + files": "Effacer + fichiers",
    "Size": "Taille",
    "Rate": "Vitesse",
    "Queue a download": "Ajouter un téléchargement",
    "URL or magnet link": "URL ou lien magnet",
    "Download directory (optional)": "Répertoire de téléchargement (facultatif)",
    "Download": "Télécharger",
    "Download queued.": "Téléchargement ajouté.",
    "this task": "cette tâche",
    "Remove {name!r} from the list? Downloaded files are kept.": (
        "Retirer « {name} » de la liste ? "
        "Les fichiers téléchargés sont conservés."
    ),
    "Erase {name!r} AND delete its downloaded files? This cannot be undone.": (
        "Effacer « {name} » ET supprimer ses fichiers téléchargés ? "
        "Action irréversible."
    ),
    "Erase files": "Effacer les fichiers",
    "Task and files erased.": "Tâche et fichiers effacés.",
    # ---------- storage --------------------------------------------------------
    "Disks": "Disques",
    "Partitions": "Partitions",
    "Model": "Modèle",
    "Temp": "Temp.",
    "Label": "Libellé",
    "Used": "Utilisé",
    "Total": "Total",
    "Use%": "% util.",
    "Free": "Libre",
    # ---------- system ---------------------------------------------------------
    "Reboot": "Redémarrer",
    "Power off": "Éteindre",
    "Reboot the Freebox?\n\nThe whole network (including this app's "
    "connection) drops for a couple of minutes.": (
        "Redémarrer la Freebox ?\n\nTout le réseau (y compris la connexion "
        "de cette appli) sera coupé pendant quelques minutes."
    ),
    "Reboot requested — the box is going down.": (
        "Redémarrage demandé — la Freebox s’arrête."
    ),
    "Power off the Freebox?\n\nIt stays down until someone presses the "
    "physical button — this app cannot turn it back on.": (
        "Éteindre la Freebox ?\n\nElle restera éteinte jusqu’à un appui sur le "
        "bouton physique — cette appli ne peut pas la rallumer."
    ),
    "Shutdown requested.": "Extinction demandée.",
    "temp   {sensors}": "temp.   {sensors}",
    "fans   {fans}": "ventil. {fans}",
    # ---------- calls -----------------------------------------------------------
    "Mark read": "Marquer lu",
    "Mark all read": "Tout marquer comme lu",
    "Clear log": "Vider l’historique",
    "Number": "Numéro",
    "New": "Nouveau",
    "All calls marked read.": "Tous les appels sont marqués comme lus.",
    "Delete this call log entry?": "Supprimer cette entrée du journal d’appels ?",
    "Clear the WHOLE call log? This cannot be undone.": (
        "Vider TOUT le journal d’appels ? Action irréversible."
    ),
    "Call log cleared.": "Journal d’appels vidé.",
    # ---------- contacts ---------------------------------------------------------
    "First": "Prénom",
    "Last": "Nom de famille",
    "Company": "Société",
    "Display name": "Nom affiché",
    "First name": "Prénom",
    "Last name": "Nom de famille",
    "New contact": "Nouveau contact",
    "Edit contact": "Modifier le contact",
    "Created contact {name!r}.": "Contact « {name} » créé.",
    "Delete contact {name!r}?": "Supprimer le contact « {name} » ?",
    "this contact": "ce contact",
    # ---------- files shell ------------------------------------------------------
    "type `help` for commands": "tapez `help` pour voir les commandes",
    "The Freebox filesystem. `help` lists commands; Tab completes.": (
        "Le système de fichiers de la Freebox. `help` liste les commandes ; "
        "Tab complète."
    ),
    """\
ls [PATH]          list a directory
cd [PATH]          change directory (`cd` → /, `cd -` → back, .. goes up)
pwd                print the current directory
tree [PATH]        directory tree, a few levels deep
mkdir NAME         create a directory here
mv SRC DST         move (box-side task)
cp SRC DST         copy (box-side task)
rm PATH            delete (box-side task, asks first)
share PATH [DAYS]  publish a download link (default: never expires)
tasks              show the box's file tasks
clear              wipe the scrollback
help               this text""": """\
ls [CHEMIN]           liste un répertoire
cd [CHEMIN]           change de répertoire (`cd` → /, `cd -` → retour, .. remonte)
pwd                   affiche le répertoire courant
tree [CHEMIN]         arborescence, sur quelques niveaux
mkdir NOM             crée un répertoire ici
mv SRC DST            déplace (tâche côté box)
cp SRC DST            copie (tâche côté box)
rm CHEMIN             supprime (tâche côté box, confirmation demandée)
share CHEMIN [JOURS]  publie un lien de téléchargement (par défaut : sans expiration)
tasks                 affiche les tâches de fichiers de la box
clear                 efface l’écran
help                  ce texte""",
    "parse error: {error}": "erreur de syntaxe : {error}",
    "error: {error}": "erreur : {error}",
    "{n} items": "{n} éléments",
    "{n} entry in {path}": "{n} élément dans {path}",
    "{n} entries in {path}": "{n} éléments dans {path}",
    "… (truncated)": "… (tronqué)",
    "cd: no previous directory": "cd : pas de répertoire précédent",
    "mkdir: which name?": "mkdir : quel nom ?",
    "created {path}": "{path} créé",
    "{cmd}: needs SRC and DST": "{cmd} : il faut SRC et DST",
    "{cmd} started (task {task}) — `tasks` shows progress": (
        "{cmd} lancé (tâche {task}) — `tasks` affiche la progression"
    ),
    "rm: which path?": "rm : quel chemin ?",
    "Delete {path} from the box? This cannot be undone.": (
        "Supprimer {path} de la Freebox ? Action irréversible."
    ),
    "rm: cancelled": "rm : annulé",
    "rm started (task {task})": "rm lancé (tâche {task})",
    "share: which path?": "share : quel chemin ?",
    "share: DAYS must be a number": "share : JOURS doit être un nombre",
    "no file tasks": "aucune tâche de fichiers",
    "unknown command {cmd!r} — try `help`": (
        "commande inconnue « {cmd} » — essayez `help`"
    ),
    # ---------- VMs ------------------------------------------------------------
    "Shutdown": "Éteindre",
    "Hard stop": "Arrêt forcé",
    "Console": "Console",
    "VNC screen": "Écran (VNC)",
    "Exec…": "Exécuter…",
    "cloud-init": "cloud-init",
    "Memory": "Mémoire",
    "Disk": "Disque",
    "Hypervisor: {used}/{total} vCPUs · {used_mem} / {total_mem} memory in use": (
        "Hyperviseur : {used}/{total} vCPU · "
        "{used_mem} / {total_mem} de mémoire utilisée"
    ),
    "screen (VNC)": "écran (VNC)",
    "yes — v opens Freebox OS": "oui — v ouvre Freebox OS",
    "on box": "sur la box",
    "virtual": "virtuel",
    "virtual size unavailable while running": (
        "taille virtuelle indisponible tant que la VM est allumée"
    ),
    "host": "hôte",
    "(u shows userdata)": "(u affiche le user-data)",
    "Starting {name}…": "Démarrage de {name}…",
    "ACPI shutdown sent to {name}.": "Extinction ACPI envoyée à {name}.",
    "Hard-stop VM {name!r}? Like pulling the power cord — the guest "
    "gets no chance to sync its disks.": (
        "Arrêt forcé de la VM « {name} » ? Comme débrancher la prise — "
        "le système invité n’aura aucune chance de synchroniser ses disques."
    ),
    "{name} powered off.": "{name} éteinte.",
    "Delete the VM definition {name!r}? Its disk file is kept on the "
    "box, but the VM itself is gone.": (
        "Supprimer la définition de la VM « {name} » ? Son fichier "
        "disque reste sur la box, mais la VM disparaît."
    ),
    "Delete VM": "Supprimer la VM",
    "VM {name} deleted (disk kept).": "VM {name} supprimée (disque conservé).",
    "{name} has no screen: enable_screen is off in its config, so "
    "the box runs it headless (serial console only).": (
        "{name} n’a pas d’écran : l’écran virtuel est désactivé dans sa "
        "configuration, la box l’exécute sans affichage (console série uniquement)."
    ),
    "Freebox OS opens in the browser — VMs → {name} → écran.": (
        "Freebox OS s’ouvre dans le navigateur — VMs → {name} → Écran."
    ),
    "The VM must be running to attach its console.": (
        "La VM doit être allumée pour attacher sa console."
    ),
    "This attaches your terminal to the VM's serial port (its tty) — not a "
    "fresh shell. You may land on a guest login prompt, or on whatever the "
    "console last printed; a sleeping getty may need an Enter to wake up."
    "\n\nTo come back to fbx, press {detach}": (
        "Ceci attache votre terminal au port série de la VM (son tty) — pas à un "
        "nouveau shell. Vous pouvez tomber sur une invite de connexion du système "
        "invité, ou sur le dernier affichage de la console ; un getty endormi "
        "peut demander un appui sur Entrée pour se réveiller."
        "\n\nPour revenir à fbx, appuyez sur {detach}"
    ),
    "Serial console — {name}": "Console série — {name}",
    "Attach here (a)": "Attacher ici (a)",
    "New terminal window (t)": "Nouvelle fenêtre de terminal (t)",
    "Attach here": "Attacher ici",
    "New terminal": "Nouveau terminal",
    "Reveal credentials": "Afficher les identifiants",
    "Copy password": "Copier le mot de passe",
    "Copy login": "Copier l’identifiant",
    "Guest credentials (cloud-init): ": "Identifiants de l’invité (cloud-init) : ",
    "  —  r reveals · p copies the password · u the login": (
        "  —  r affiche · p copie le mot de passe · u l’identifiant"
    ),
    "Password copied to the clipboard.": "Mot de passe copié dans le presse-papiers.",
    "cloud-init names no login for this one.": (
        "cloud-init n’indique aucun identifiant ici."
    ),
    "Login {login!r} copied to the clipboard.": (
        "Identifiant « {login} » copié dans le presse-papiers."
    ),
    "Console opened in its own window — Ctrl-] there detaches.": (
        "Console ouverte dans sa propre fenêtre — Ctrl-] là-bas pour détacher."
    ),
    "Couldn't open a terminal window — `a` attaches here instead.": (
        "Impossible d’ouvrir une fenêtre de terminal — `a` attache ici à la place."
    ),
    "── {name} · serial console — {detach} returns to fbx; "
    "Enter wakes an idle prompt.": (
        "── {name} · console série — {detach} pour revenir à fbx ; "
        "Entrée réveille une invite endormie."
    ),
    "The VM must be running to run a command.": (
        "La VM doit être allumée pour exécuter une commande."
    ),
    "Run on {name}'s serial console": "Exécuter sur la console série de {name}",
    "Command": "Commande",
    "Running (collects until the tty goes quiet)…": (
        "Exécution (capture jusqu’au silence du tty)…"
    ),
    "(no output)": "(aucune sortie)",
    "(no cloud-init userdata)": "(pas de user-data cloud-init)",
    "{name} — cloud-init userdata": "{name} — user-data cloud-init",
    # ---------- wire values (context|value, via i18n._p) ------------------------
    # Connection state.
    "state|up": "connecté",
    "state|down": "déconnecté",
    "state|going_up": "connexion…",
    "state|going_down": "déconnexion…",
    # Wi-Fi AP state.
    "ap-state|active": "actif",
    "ap-state|disabled": "désactivé",
    "ap-state|scanning": "scan en cours",
    "ap-state|failed": "en échec",
    # MAC filter mode/type (Freebox OS: « Liste noire »/« Liste blanche »).
    "mac-filter|disabled": "désactivé",
    "mac-filter|blacklist": "liste noire",
    "mac-filter|whitelist": "liste blanche",
    # Download task status (Freebox OS: « Téléchargement », « Terminé »…).
    "dl-status|downloading": "téléchargement",
    "dl-status|done": "terminé",
    "dl-status|error": "erreur",
    "dl-status|stopped": "arrêté",
    "dl-status|seeding": "partage",
    "dl-status|queued": "en attente",
    "dl-status|checking": "vérification",
    "dl-status|stopping": "arrêt en cours",
    "dl-status|extracting": "extraction",
    "dl-status|repairing": "réparation",
    # Call types (Freebox OS: « Appels manqués/entrants/sortants »).
    "call-type|missed": "manqué",
    "call-type|accepted": "reçu",
    "call-type|outgoing": "sortant",
    # VM status (Freebox OS: « Allumé »/« Éteint »).
    "vm-status|running": "allumé",
    "vm-status|stopped": "éteint",
    "vm-status|starting": "démarrage",
    "vm-status|stopping": "arrêt en cours",
    # Disk state.
    "disk-state|enabled": "actif",
    "disk-state|disabled": "désactivé",
    "disk-state|formatting": "formatage",
}
