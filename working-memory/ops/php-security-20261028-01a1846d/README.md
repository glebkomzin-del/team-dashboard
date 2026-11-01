# PHP-Sicherheitsprüfung – 28.10.2026

## Ergebnis
Auf dem Dashboard-/n8n-Server 178.105.167.26 wurde bei der gezielten Prüfung kein PHP gefunden: weder als installiertes Paket auf dem Host oder in den zehn laufenden Containern noch als ausführbare Datei an den üblichen Orten oder als laufender Prozess. Die geprüften aktiven Nginx-Seiten und zusätzlichen Konfigurationsdateien enthalten keinen PHP-/FastCGI-Verweis. Für die konkrete Hetzner-Warnung ergibt sich dort kein PHP-Updatebedarf.

Keine Pakete installiert, keine Einstellungen geändert, kein Dienst neu geladen oder neu gestartet und kein Neustart des Servers. Containerkennungen und Startzeiten waren vor und nach der Prüfung identisch. Der öffentliche Dashboard-Gesundheitstest lieferte zweimal HTTP-Erfolg mit {"status":"ok","mode":"production"}.

Zusätzlich bekannter Klarstand-Server 2.28.57.241: SSH als root mit vorhandenem Standardzugang scheitert mit „Permission denied (publickey)“. Dort sind Softwarestand und Betroffenheit nicht belegt. Kein Update vorbereitet, das ohne vorherige Bestandsprüfung sicher ausführbar wäre.

## Auftrag und Grenzen
Hetzner-Warnung in Gmail finden, tatsächliche PHP-Betroffenheit feststellen und erforderliche Updates nur ohne Beeinträchtigung der parallelen Sitzung durchführen. Updates mit Dienstunterbrechung auf spätere ausdrückliche Ausführung verschieben. Andere Paket-, Betriebssystem- oder Docker-Upgrades sind nicht Gegenstand dieser PHP-Prüfung. Fremde lokale Änderungen wurden nicht bearbeitet.

Die Sitzung „Umsetzung · Verarbeitung · Fehlerbehebung“ war während der Prüfung aktiv. Kein Kontakt oder Eingriff in ihre Arbeit.

## Mail und Quellen
- Gmail: announcement@hetzner.com, 23.10.2026, „Wichtige Kundeninformation: PHP-Update zur kritischen Sicherheitslücke CVE-2026-109618 und CVE-2026-109619“.
- [Mail öffnen](https://mail.google.com/mail/u/?authuser=gleb.komzin%40gmail.com#all/1a1677adcd8cd5b4)
- [PHP-Sicherheitsmeldung](https://www.php.net/archive/2026.php#2026-10-21-5): korrigiert in 8.5.12 / 8.4.27 / 8.3.36 / 8.2.35; Distributionspakete können zurückportierte Korrekturen enthalten. Veröffentlichung vom 23.10. nennt zusätzlich session.upload_progress.enabled=0 für einen seltenen weiteren Angriffsweg.
- [Hetzner-Status](https://status.hetzner.com/de/incident/f4144d55-38c3-48d1-8664-7a3429355cd7): eigene Webhosting-/Managed-Angebote aktualisiert; selbst verwaltete Cloud-/Dedicated-Server bleiben Kundenzuständigkeit.

## Ausgeführte Prüfung
SSH mit BatchMode=yes, StrictHostKeyChecking=yes und ConnectTimeout=10. Kein Schlüsselinhalt gelesen oder ausgegeben.
Host: Betriebssystem, Paketregistrierung, PHP-Binärpfade, Prozessnamen und offene TCP-Ports.
Container: Namen, Kennungen, Startzeiten, Paketregistrierung und übliche PHP-Binärpfade über /proc/<pid>/root; Prozessnamen über docker top <container> -eo pid,comm.
Paketprüfungen lesen ausschließlich Paketmetadaten. Keine Container-Umgebungsvariablen oder Zugangsdaten ausgegeben.
Rohdaten der erfolgreichen Inventur: inventory.jsonl.

Erste Containerprobe hatte Fehler bei Shell-Ersetzungen und docker top ohne PID-Spalte; diese Ergebnisse wurden verworfen. Die anschließende erfolgreiche Inventur nutzte Dateisystem-/Paketregistrierungen und PID-Spalte für alle zehn Container.

## Spätere Ausführung, falls ein weiterer Server PHP verwendet
Zuerst gültigen Zugang und tatsächliche Installation feststellen. Danach Distributionskorrektur bzw. passendes Container-Image und Rückweg bestimmen; Änderung und Dienstneustart erst außerhalb der parallelen Arbeit. Vorherige und nachherige Gesundheitsprüfung und Versionsnachweis erforderlich. Keine pauschalen Upgrade-Befehle hinterlegt.

## Aussagegrenzen
Gezielte Prüfung des Hosts und der aktuell laufenden Container; keine vollständige Suche in beliebig benannten Eigenbauten, gestoppten Containern oder inaktiven Images. Keine forensische Untersuchung und kein Nachweis allgemeiner Angriffsfreiheit. Allgemeiner Betriebssystem-Updatezustand nicht bewertet.

