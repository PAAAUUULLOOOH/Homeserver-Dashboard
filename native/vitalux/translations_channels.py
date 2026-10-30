"""Update channels, customization indicators and network controls."""
EN={

'Liquid Silver · Die Oberfläche von Obsidian Gold mit dunklem Rauchglas und satiniertem Silber. Palette und Hintergrund sind fest.':'Liquid Silver · The Obsidian Gold interface with dark smoked glass and satin silver. The palette and background are fixed.',
'Dieser Wechsel startet automatisch neu. Stable v{version} verwendet bei späteren Updates noch „Jetzt neu starten“.':'This switch restarts automatically. Stable v{version} still uses “Restart now” for subsequent updates.',
'Black Glass · Tiefschwarze Glasflächen mit dezenten Reflexionen und silbernen Kanten. Akzentfarben und Hintergründe sind frei anpassbar.':'Black Glass · Deep black glass with subtle reflections and silver edges. Accent colors and backgrounds are fully customizable.',
'Vitalux läuft bereits.':'Vitalux is already running.',
'Versionsverlauf':'Version history',
'Für diese Version ist noch kein Changelog verfügbar.':'No release notes are available for this version yet.',
'Die Versionsauswahl zeigt nur Hinweise und ändert nicht das Installationsziel.':'Browsing versions only shows release notes; it does not change the installation destination.',

'Im Updates-Reiter stehen laufender Stand, Stable/Unstable und dauerhaft sichtbare Changelogs zusammen. Die Versionsauswahl blättert durch die Historie des Kanals, ohne das Installationsziel zu ändern; nur die separate Installationsaktion wechselt den Kanal.':'The Updates tab groups the running version, Stable/Unstable and release notes that always remain visible. The version selector browses the channel’s history without changing the installation destination; only the separate installation action switches channels.',

'Aktiver Kanal':'Active channel',
'Update-Kanal':'Update channel',
'Stable und Unstable verwenden getrennte Einstellungen. Ein Kanalwechsel wird erst mit der Installation ausgeführt.':'Stable and Unstable use separate settings. A channel switch takes effect when its package is installed.',
'Ein aktiver Vorgang verhindert den Neustart. Bitte später erneut versuchen.':'An active operation prevents restarting. Please try again later.',
'Zu Unstable wechseln':'Switch to Unstable',
'Zu Stable zurückkehren':'Return to Stable',
'Unbekannter Update-Kanal.':'Unknown update channel.',
'Noch kein Unstable-Testpaket veröffentlicht.':'No Unstable test package has been published yet.',
'Testpaket und Manifest stimmen nicht überein. Bitte erneut prüfen.':'The test package does not match its manifest. Please check again.',
'Akzentfarben: Voreinstellungen verfügbar; eigene Farben gesperrt':'Accent colors: presets available; custom colors locked',
'Akzentfarben anpassbar':'Accent colors adjustable',
'Hintergrund anpassbar':'Background adjustable',
'Erweiterte Verbindungen':'Advanced connections',
'Verbindung sperren':'Block connection',
'Verbindung entsperren':'Unblock connection',
'Entsperren':'Unblock',
'Sperren':'Block',
'Wird geändert …':'Applying …',
'Netzwerkzugriff':'Network access',
'Ein- und ausgehenden Netzwerkverkehr dieser App sperren oder freigeben.':'Block or allow inbound and outbound network traffic for this app.',
'Bei Bedarf wird die Systemfreigabe direkt angefragt.':'System authorization will be requested if needed.',
'Zuerst die vollständige App-Sperre aufheben.':'First remove the application-wide block.',
'Für einzelne Verbindungen ist eine vollständige Messung mit Kernel-Socketkennung erforderlich.':'Individual connection controls require full accounting with kernel socket identities.',
'Netzwerk → Programme & Verbindungen zeigt laufende Apps und Verbrauch. Sperren und Entsperren stehen direkt in der App-Liste; die Systemfreigabe wird bei Bedarf angefragt. Einzelne TCP-/UDP-Sockets findest du unter Erweiterte Verbindungen.':'Network → Apps & connections shows running apps and usage. Block and Unblock are directly in the app list; system authorization is requested when needed. Individual TCP/UDP sockets appear under Advanced connections.',


}

EN.update({


'Kanal ansehen':'Browse channel',
'Ein Klick zeigt den Changelog. Ein Kanalwechsel wird separat vorbereitet und erst nach dem Neustart aktiv.':'Click a channel to read its changelog. Prepare a switch separately; it takes effect after restarting.',
'Stable ansehen':'View Stable',
'Deine Teständerungen sind jetzt in Stable verfügbar.':'Your test changes are now available in Stable.',
'Installation':'Installation',
'Aktuell':'Current',
'Zielstand':'Destination',
'Neustart erforderlich.':'Restart required.',
'Neustart erforderlich. Du kannst Vitalux bis dahin weiterverwenden.':'Restart required. You can continue using Vitalux until then.',
'Jetzt neu starten':'Restart now',
'Später':'Later',
'Unstable · Teststand für v{version}':'Unstable · testing v{version}',
'Unstable · entspricht Stable v{version}':'Unstable · matches Stable v{version}',
'Unstable · derzeit kein neuerer Teststand':'Unstable · no newer test build',
'Paket herunterladen …':'Downloading package …',
'Paket prüfen …':'Verifying package …',
'Installation vorbereiten …':'Preparing installation …',
'Derzeit gibt es keinen neueren Unstable-Teststand.':'There is currently no newer Unstable test build.',
'Der gewählte Kanal kann separat installiert werden.':'The selected channel can be installed separately.',
'Prüfung nicht möglich.':'Unable to check.',
'Prüfung unvollständig: {reason}':'Check incomplete: {reason}',
'Zuletzt geprüft: {time}':'Last checked: {time}',
'Noch nicht geprüft.':'Not checked yet.',
'Gespeicherter Stand; offline lesbar.':'Saved information; available offline.',
'Ein Wechsel ist nur mit einem geprüften, neueren Teststand möglich.':'Switching requires a verified, newer test build.',
'Keine zusätzlichen Teständerungen. Es gilt der aktuelle Stable-Changelog.':'No additional test changes. The current Stable changelog applies.',
'Für diesen Kanal ist noch kein Changelog verfügbar.':'No changelog is available for this channel yet.',
})

EN.update({
'Unstable · Verfügbarkeit nicht bestätigt':'Unstable · availability unconfirmed',
'Hinweis: {reason}':'Note: {reason}',
'Vorgang fehlgeschlagen.':'Operation failed.',
})

EN['Vitalux – Versionsstatus']='Vitalux – version status'

EN['Vitalux-Ordner ist schreibgeschützt. Bitte eine beschreibbare Installation verwenden.']='The Vitalux folder is read-only. Please use a writable installation.'

EN.update({
'Nach Updates suchen':'Check for updates',
'Changelog ansehen':'View changelog',
'Changelog ausblenden':'Hide changelog',
'Für diesen Kanal gilt der aktuelle Stable-Changelog.':'The current Stable changelog applies to this channel.',
'Updatekanäle':'Update channels',
'Zielversion':'Target version',
'Changelog ansehen; ein Wechsel wird separat gestartet.':'View the changelog; start a channel switch separately.',
'Stabile Versionen für den täglichen Einsatz.':'Stable releases for everyday use.',
'Testversionen mit neuen Änderungen vor dem Stable-Release.':'Test builds with new changes ahead of the Stable release.',
'Verfügbarkeit nicht bestätigt. Gespeicherte Changelogs bleiben lesbar.':'Availability is unconfirmed. Saved changelogs remain readable.',
'Die vorbereitete Version wird beim Neustart aktiv. Bis dahin kannst du Vitalux weiterverwenden.':'The prepared version takes effect after restarting. You can continue using Vitalux until then.',
})

EN.update({
'Update geprüft. Vitalux wird automatisch neu gestartet.':'Update verified. Vitalux is restarting automatically.',
'Hintergrundaufgaben werden beendet. Anschließend startet Vitalux automatisch mit der vorbereiteten Version.':'Background tasks are finishing. Vitalux will then restart automatically into the prepared version.',
'Neustart fehlgeschlagen. Bitte unter Updates erneut versuchen.':'Restart could not be prepared. Please retry in Updates.',
'Vitalux wird gerade neu gestartet. Bitte einen Moment warten.':'Vitalux is restarting. Please wait a moment.',


})
