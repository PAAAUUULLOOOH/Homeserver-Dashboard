# Testbericht · 0.10.0 Testpaket

Prüfstand: 30. Oktober 2026. Entwicklung und Tests erfolgten in einem separaten Arbeitsordner. Das vorhandene Vitalux-Checkout wurde nicht verändert. Kein Systemdienst und keine Installation auf dem Homeserver des Benutzers. Die Distribution erfolgt als Quellcode-Repository und vollständiges GitHub-Release-ZIP.

## Bestanden

- **21 automatisierte Python-Tests**: Anmeldung/Abmeldung, Sitzungsschutz, CSRF, Medienordner, NFO-Metadaten, HTTP-Range-Streaming, erlaubte Docker-Vorlagen, Lizenzbestätigung, Portkollisionen, fremde Container, unveränderte Konsolenargumente, Mod-Pfade, Backup/Wiederherstellung und Symlink-/Archivpfad-Prüfung.
- **Echter Docker-Test mit isoliertem Alpine-Container**: Erstellen, Starten, Status lesen, Logs, Stoppen, Backup, Wiederherstellung, erneutes Starten und Entfernen. Fortbestehen der Spielstanddatei nach Containerentfernung geprüft; Testcontainer anschließend entfernt. Dies war ein Test der Docker-Verwaltung, kein Minecraft-Spieltest.
- **Chromium-Browserprüfung**: erfolgreiche Formularanmeldung, Übersicht, Katalog, TeamSpeak, Protokoll, Homeserver, PAULFLIX, Installationsdialog und zunächst unbestätigte Lizenzcheckbox. Alle sieben Designs ausgewählt. Mobile Ansicht mit 390 Pixel Breite ohne horizontalen Überlauf. Keine JavaScript-Laufzeitfehler.
- **Native Qt-Prüfung mit der mitgelieferten Laufzeit**: alle sieben Designs gerendert, Katalog und Designauswahl geöffnet. Offscreen-Aufnahmen liegen unter Vorschau/. Kein Qt-WebEngine-Download erforderlich.
- Python-Kompilierung, JavaScript-Syntaxprüfung und Shell-Syntaxprüfung.
- Registry-Metadaten für alle neun verwendeten Container-Abbilder: die angegebenen Tags sind vorhanden. Dabei wurden keine Gameserver installiert.

Beim Browser-Test wurde ein bereits in der Ausgangsversion vorhandenes Problem behoben: `Referrer-Policy: no-referrer` erzeugte beim Login-Formular einen `Origin: null` und damit eine abgelehnte Anmeldung. Die Einstellung ist jetzt `same-origin`; der bestehende Schutz gegen fremde POST-Ursprünge bleibt erhalten.

## Grenzen der Prüfung

- Nicht auf dem tatsächlichen Ubuntu-/Debian-Homeserver des Benutzers ausgeführt.
- Kein vollständiger Download und kein echter Spielbeitritt für jeden Katalogtitel. Vorlagen können wegen Herstelleränderungen, Registry-Zugriff, Steam-Downloads oder Host-Berechtigungen weitere Anpassungen benötigen.
- TeamSpeak-Kanäle und Rechte werden im normalen TeamSpeak-Client verwaltet. Keine Abfrage von Online-Spielern oder Kanälen im Dashboard.
- Qt wurde offscreen geprüft; die Desktopdarstellung unter dem konkreten KDE/GNOME-/Wayland-/X11-System bleibt lokal zu prüfen.
- PAULFLIX-Streaming und Scanner sind geprüft; die Abspielbarkeit jedes Film-Codecs wurde nicht getestet. Kein Transcoding.
- Das ZIP enthält eine vorbereitete Linux-x86_64-App-Laufzeit, keine vollständige Offline-Sammlung aller Spiele/Container.
