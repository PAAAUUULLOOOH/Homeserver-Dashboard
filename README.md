# Vitalux Homeserver · 0.10.0 Testpaket

**[Vollständiges Test-ZIP herunterladen](https://github.com/PAAAUUULLOOOH/Homeserver-Dashboard/raw/refs/heads/main/downloads/Vitalux-Homeserver-v0.10.0-Test-linux-x86_64.zip)** · [Datei und Prüfsumme im Repository](https://github.com/PAAAUUULLOOOH/Homeserver-Dashboard/tree/main/downloads)

Eigenständige Testversion für **Ubuntu/Debian mit Docker, Linux x86_64**. Es wird nichts in eine vorhandene Vitalux-Installation eingebaut. Kein Systeminstaller und kein Autostartdienst. Entpacken und eines der Startskripte ausführen.

## Schnellstart

1. ZIP in einen neuen, beschreibbaren Ordner entpacken. Nicht über dein bestehendes Vitalux entpacken.
2. Terminal in diesem Ordner öffnen.
3. Optional prüfen: `bash PRUEFEN.sh`.
4. **Auf einem Desktop:** `bash START-APP.sh`.
5. **Auf einem Homeserver ohne Desktop:** `bash START-UBUNTU.sh`.

Die erste Ausführung entpackt die **bereits mitgelieferte** Laufzeit lokal. Python 3.12, PySide6 6.12, psutil und die ergänzenden XCB-Bibliotheken sind enthalten. Keine pip-Installation und kein Laufzeitdownload erforderlich. Docker Engine und der Docker-Befehl müssen auf dem Host bereits verfügbar sein; dein Benutzer benötigt Zugriff auf den lokalen Docker-Socket. Das Paket ändert dafür keine Gruppen oder Systemdienste.

Das oben verlinkte **vollständige Test-ZIP** enthält die Laufzeit bereits. Sie liegt außerdem unter `portable-runtime/` im Repository und ist somit auch bei einem Git-Checkout enthalten. Sollte die Datei lokal fehlen, kann das Startskript sie aus demselben Repository nachladen. Vor dem Entpacken wird ihre feste SHA256-Prüfsumme geprüft. Das Test-ZIP unter `downloads/` ist die empfohlene fertig vorbereitete Distribution.

Beim ersten Start ein eigenes Administratorpasswort mit mindestens zwölf Zeichen einrichten. Benutzername: **admin**. Die native App fragt das Passwort ebenfalls ab.

Im Webbetrieb anschließend **http://127.0.0.1:8765** öffnen. Die native App öffnet PAULFLIX und zusätzliche Browserdetails über einen eigenen lokalen Port; beide Oberflächen verwenden dasselbe Backend. PAULFLIX wird im Systembrowser angezeigt, nicht als eingebetteter Qt-WebEngine-Player.

**Von einem anderen Computer testen:** Das Web-Dashboard auf dem Homeserver starten, dann auf dem anderen Computer `ssh -L 8765:127.0.0.1:8765 BENUTZER@HOMESERVER` ausführen und dort http://127.0.0.1:8765 öffnen. Alternativ ist eine explizite LAN-Bindung mit `bash START-UBUNTU.sh --host DEINE_LAN_IP` möglich. Die Standardbindung ist ausschließlich lokal.

Die Startskripte verhindern mit `flock`, dass Web- und Desktopmodus gleichzeitig auf denselben Datenbestand schreiben. Auf ARM lässt sich der Webmodus mit vorhandenem Python 3.12+ über `python3 server.py` starten; die gebündelte Laufzeit und der native Testumfang beziehen sich auf x86_64.

## Enthaltene Funktionen

- Natives Qt-Dashboard mit den originalen Vitalux-Komponenten für Atmosphäre, Glasflächen, Navigation, Karten und Designauswahl.
- Sieben auswählbare Designs: **Obsidian Gold, Glass, Crystal Atrium, Nebula Prism, Quantum Core, Light und Aurora Bloom**. Die Browseroberfläche übernimmt die originalen Farbpaletten und aus Qt gerenderte Hintergründe; ihre Bedienelemente sind in CSS umgesetzt. Die neue Anordnung enthält die Homeserver-Funktionen und entspricht nicht jeder Monitorseite der ursprünglichen Vitalux-App.
- Spielekacheln mit Installation in Docker, getrennten Spielständen, Ressourcenlimit und Portprüfung.
- Minecraft Java mit **Paper, Vanilla, Fabric und Forge**; weitere Vorlagen für **Valheim, Palworld, Counter-Strike 2, Terraria, Satisfactory, Factorio und Project Zomboid**.
- TeamSpeak 3 als eigener Docker-Server. Voice-Port standardmäßig 9987/UDP, Dateitransfer 30033/TCP. ServerQuery wird nicht an den Host veröffentlicht. Den ersten Berechtigungsschlüssel zeigt das Container-Protokoll. Kanäle, Servername und Rechte anschließend im TeamSpeak-Client verwalten.
- Starten, Stoppen, Neustart, Container-Protokolle und lokale Ereignisliste. „Läuft“ bedeutet, dass der Container läuft; Spielbereitschaft nach dem Download steht im Protokoll.
- Minecraft-Konsolenbefehle über internes RCON. Kein öffentlicher RCON-Port.
- JAR-Dateien für Paper-Plugins beziehungsweise Fabric-/Forge-Mods hochladen, aktivieren und deaktivieren. Vor Änderungen erfolgt ein Backup. Dateien müssen zu Spielversion und Loader passen; Fabric API und andere Mod-Abhängigkeiten werden als passende JARs ebenfalls hochgeladen. Ein externer Mod-Marktplatz oder eine automatische Auflösung von Mod-Abhängigkeiten ist noch nicht enthalten.
- Gestoppte Server sichern und wiederherstellen. Vor dem Wiederherstellen entsteht ein Sicherheitsbackup. Entfernen eines Containers lässt Spielstände, Mods und Backups erhalten.
- Reale Host-Messwerte anstelle der simulierten Zahlen der ursprünglichen HTML-Seite. Spielerzahlen und Online-Spieler werden noch nicht abgefragt.

Die aufgeführten Spielvorlagen sind im Installer integriert. Der Test dieser Ausgabe umfasst die allgemeine Docker-Steuerung mit einem isolierten Testcontainer, **keine vollständigen Downloads und Spielbeitritte für jeden einzelnen Titel**. CS2 benötigt einen eigenen Steam Gameserver Login Token. Valheim benötigt ein Serverpasswort von mindestens fünf Zeichen. Die Lizenzbedingungen werden beim Installieren ausdrücklich bestätigt.

## PAULFLIX

PAULFLIX öffnen → **Einstellungen → Ordner auf dem Homeserver**. Absolute Film-/Serienpfade eingeben, speichern und scannen. Unterstützt werden Dateinamen, Serienfolgen, lokale NFO-/JSON-Metadaten und vorhandene Cover. Favoriten, Suche, Weiterschauen und geschütztes HTTP-Range-Streaming sind enthalten. Es werden keine Filme mitgeliefert.

Die Videos bleiben in deinen Medienordnern und werden weder hochgeladen noch verschoben. Browserkompatible MP4-/WebM-Dateien können direkt abgespielt werden. **Kein Transcoding**, kein Netflix-Konto und keine Online-Filmdatenbank-Anbindung. MKV/AVI hängt von Browser und Codec ab. Browserimporte bleiben auf dem jeweiligen Wiedergabegerät; für die dauerhafte Bibliothek die serverseitigen Ordner einrichten.

## Vorladen und Offline-Transfer

Die App-Laufzeit und Designs sind vollständig im ZIP enthalten. **Gameserver-Abbilder und proprietäre Spieldateien sind nicht im ZIP enthalten.** Dafür gibt es im Spielekatalog je Kachel „Vorladen“ und zusätzlich:

```bash
bash VORLADEN.sh --list
bash VORLADEN.sh minecraft teamspeak
bash VORLADEN.sh --all
```

`--all` kann mehrere GB herunterladen. Vorladen lädt Container-Abbilder und startet keine Server. Steam-/Spieldateien können je nach Abbild erst beim ersten Serverstart heruntergeladen werden. Ein vorgeladenes Abbild garantiert daher noch keinen vollständig offline verfügbaren Gameserver.

Abbilder auf einem Online-Rechner exportieren und auf einem anderen Docker-Host importieren:

```bash
bash VORLADEN.sh minecraft teamspeak --export /dein/pfad/abbilder.tar
bash VORLADEN.sh --import-file /dein/pfad/abbilder.tar
```

## Daten und Beenden

Alles liegt standardmäßig unter **data/** im entpackten Testordner:

- `admin.json`: Passwort-Hash des Testkontos.
- `servers.json`: Containerkonfiguration; enthält gegebenenfalls Spielpasswörter/Steam-Token. Als lokale Administratordatei behandeln.
- `servers/ID/`: Spielstände, Konfiguration und Mods.
- `backups/ID/`: Backups.
- `paulflix-*.json`: Medienquellen und Metadaten.
- `native-profile/`: eigene Darstellungseinstellungen, vollständig getrennt vom installierten Vitalux.

Server im Dashboard stoppen, wenn du sie beenden möchtest. Das Beenden des Dashboards beendet laufende Docker-Gameserver nicht automatisch. Deren Neustartregel ist `unless-stopped`. Das Dashboard selbst installiert keinen Autostartdienst.

Container-Abbilder lassen sich erneut vorladen. Eine automatische Aktualisierung/Rekonstruktion bestehender Spielcontainer, Zeitpläne, ein allgemeiner Dateimanager und Mehrbenutzerverwaltung sind in dieser Testausgabe nicht enthalten. Die entsprechenden früheren Demo-Schaltflächen wurden entfernt.

## Prüfung und Quellen

Siehe **TESTBERICHT.md** für die tatsächlich ausgeführten Prüfungen und **Vorschau/** für Aufnahmen der nativen Designs. Tests selbst ausführen: `runtime/bin/python3.12 -m unittest -q test_engine test_local test_media_library` nach dem ersten Entpacken der Laufzeit.

Grundlage ist die Dashboard-Version 0.9.1 sowie Designcode aus [Vitalux unstable](https://github.com/PAAAUUULLOOOH/Vitalux/tree/unstable). Quellcode und Lizenzhinweise liegen bei. Dieses Repository verteilt das eigenständige Homeserver-Testprojekt. **VITALUX-LICENSE-NOTICE.md**, **VITALUX-THIRD-PARTY.md** und **licenses/** bleiben maßgeblich für die jeweiligen Bestandteile.
