# React-Testansicht des Arbeitsgedächtnisses

Stand: 6. September 2026. Lokaler, isolierter Testbestand; keine produktive Migration.

## Verhalten

Die neue Ansicht zeigt eigene offene Zusagen, eigene Zusagen mit Voraussetzung, Zusagen anderer, Änderungen am ausgewählten Meeting-Tag, Wissen je Vorgang und belegte Abschlüsse. Wissensstand, Vorgangsfilter und lokale Textsuche wirken auf die jeweiligen sichtbaren Mengen. Die Quellenzahl nennt ausdrücklich alle Quellen bis zum gewählten Datum; die Vorgangs- und Aussagezahlen beziehen sich auf die aktuelle Filterauswahl.

Jede Zusage besitzt eine stabile ID, ihren ursprünglichen Titel und einen chronologischen Verlauf mit Quellversion, Originalzitaten und Änderungsart. Eine spätere Statusmeldung löscht weder Frist noch Zuständigkeit. Relative Fristen behalten das Datum ihrer Nennung. Ein Abschluss bleibt bestehen, bis eine belegte Wiederaufnahme erfolgt. Die vollständige Quelle wird erst beim Öffnen des Originaldialogs geladen.

Deine bestätigte Einordnung der Umrechnungskurse steht als Voraussetzung beim Vorgang. Das Gespräch über „VO“ bleibt eine Möglichkeit. Die beiden Nutzerkorrekturen haben Vorrang vor Modellurteilen.

## Start

Im Verzeichnis `meeting-os`, in zwei Terminals:

```sh
python3 working-memory/preview_service.py --db working-memory/.local/finance-corrected-v4.sqlite
pnpm dev --host 127.0.0.1 --port 8795
```

Dann `http://127.0.0.1:8795/memory-preview` öffnen. Der Dienst auf Port 8794 öffnet die bereits vorhandene Datenbank schreibgeschützt und startet keinen Worker. Er benötigt keine Modellzugangsdaten. Die lokalen privaten Ergebnisdateien werden nicht versioniert. Fehlende Datenbanken werden ausdrücklich abgelehnt, nicht als leere Datenbank neu angelegt.

`working-memory/.local/preview-service.json` enthält den privaten lokalen Dienstschlüssel mit Dateirechten 600. Der Vite-Proxy liest ihn serverseitig, erlaubt nur GET für Review und konkrete Quellen und weist fremde Origins ab. Direkte Vite-Zugriffe auf `.local` sind gesperrt. Den Entwicklungsserver auf Loopback belassen.

Die Route und der Dashboard-Navigationseintrag „Arbeitsgedächtnis“ existieren nur im Entwicklungsmodus. Der Produktionsbuild enthält weder Preview-Route noch Preview-Inhalte oder Dienstschlüssel. Eine produktive Benutzerberechtigung am neuen Dienst ist noch nicht umgesetzt.

## Tatsächliche Prüfung

- 42 Python-Tests bestanden. Die beiden neuen HTTP-Tests laufen gegen einen echten Loopback-HTTP-Server mit synthetischen Daten und prüfen Authentifizierung, Originalhash, historischen Leerstand, ungültiges Datum, unbekannte Quelle, Schreibverbot und unveränderte Datenbank. Nach Bereinigung einer Ressourcenwarnung wurden beide HTTP-Tests erneut erfolgreich ausgeführt.
- Alle sieben gespeicherten Vergleichsfälle aus echten Meetings bestehen. Keine neuen Modellaufrufe oder KI-Kosten in diesem Schritt. Synthetische Zustandsprüfungen sind keine Qualitätslabels für das Modell.
- TypeScript-Prüfung und ESLint der neuen bzw. betroffenen isolierten Komponenten/Entry/Dialog/Proxy/Config bestanden. Kein vollständiger Lint-Nachweis für die alte Anwendung.
- Produktionsbuild mit Vite 8.0.9 erfolgreich. Die bestehende große App-Datei löst weiterhin die Größenwarnung über 500 kB aus. Keine erfundene Performance- oder Qualitätsquote.
- Browser: 15.07. zeigt 1 Quelle, 23 Aussagen, 0 eigene Zusagen, 1 fremde Zusage, 0 Abschlüsse. 20.07. zeigt 2 Quellen, 46 Aussagen, 0 eigene Zusagen, 2 fremde Zusagen, 1 Abschluss. 14.07. zeigt einen echten leeren Stand.
- Suche nach Umrechnungskursen: 2 Aussagen in 1 Vorgang, keine Aufgabe; die bestätigte Voraussetzung und ihre Originalzitate lassen sich öffnen. Vorgangsfilter auf den Entscheidungstermin: 3 Aussagen und die passende offene Zusage am 15.07.
- Originaldialog mit vollständigem Juli-Transkript geprüft; API-Inhalt stimmt mit dem gespeicherten SHA-256 überein. Escape schließt, Fokus kehrt zum auslösenden Button zurück; Tab bleibt im Dialog.
- Helle Ansicht und Originaldialog bei 390 × 844 geprüft: kein horizontaler Überlauf, lesbarer umbrochener Originaltext, erreichbarer Schließen-Button. Dunkle Desktopansicht ebenfalls geprüft. Temporäre Viewport-Änderung zurückgesetzt.
- Fehlender lokaler Proxy-Zugang zeigt einen Fehler statt einer leeren Aufgabenliste. Wiederherstellung und „Erneut versuchen“ funktionieren. Während regulärer Nutzung keine Warnungen/Fehler in der Browserkonsole; die absichtlich provozierte HTTP-503-Prüfung ist davon getrennt.
- Direkter Schlüsselabruf über normalen Dateipfad, `?raw` und `/@fs` abgelehnt; legitimer Review-GET funktioniert weiter. POST, unbekannte Routen/Parameter und fremde Origins abgelehnt. Schlüssel und Testansicht im erzeugten Produktions-JavaScript nicht enthalten.

## Reproduzierbarkeit und Grenzen

Ausgelagerte iCloud-Paketdateien blockierten zunächst lokale Node-Lesezugriffe. Für Build und Browser wurde deshalb eine getrennte Arbeitskopie unter `/tmp/dashboard-memory-react-review` verwendet. Sie enthält denselben Quellcode, die Projektkonfiguration und dasselbe unveränderte `pnpm-lock.yaml`; `pnpm install --frozen-lockfile --ignore-scripts` nutzte 468 bereits gecachte Pakete, ohne Versionswechsel. Produktions-Umgebungsdateien und Transkripte wurden nicht in diese Arbeitskopie kopiert. Der private Proxy greift auf den ursprünglichen schreibgeschützten Dienst zu. Die derzeit laufende Browseransicht stammt aus dieser Arbeitskopie.

Ein erneuter Standard-Config-Build blieb lokal bei Rolldown stehen. Der abschließende Produktionsbuild wurde mit `node node_modules/vite/bin/vite.js build --configLoader runner` erfolgreich verifiziert; der TypeScript-Check lief gesondert. Die Vite-Konfiguration verwendet dafür nun auch im ESM-Runner gültige Pfadauflösung.

Die frische Prüfung der Web-Interface-Regeln steht in [der Designprüfung](../../.design-workflow/reviews/working-memory-2026-09-06.md). Selbstprüfung, keine unabhängige Abnahme. Vollständige Screenreader-Prüfung, Windows-Browser, echte iOS-Geräte, große Archivbestände und produktive Authentifizierung sind noch nicht nachgewiesen. Der fachliche Gesamttestsatz, Retrieval, Drive-Übernahme, vollständige Bestandsmigration und Freigabe bleiben separate offene Arbeit.


## Authentifiziertes Archiv auf der bestehenden Domain

Am 6. September zusätzlich unter `https://team-dashboard-rho.vercel.app/memory-next#archiv` bereitgestellt. Vercel-Deployment `dpl_EXdiEdudLWb5HBvrgANybwu7fqzn`; die bisherige Hauptansicht bleibt über `/` und `/legacy` erreichbar. Die neue Hauptansicht ist weiterhin ein begrenzter Auswertungsstand, keine vollständige Bestandsumschaltung.

Vercel leitet `/api/working-memory/*` per HTTPS an den getrennten Lesedienst auf Hetzner weiter. Dieser prüft die bestehende Supabase-Sitzung über `/auth/v1/user` und die explizite Owner-ID. Service-Anmeldung und Owner-Rolle sind getrennt; der Browser enthält keinen Service-Schlüssel. Live-Tests mit Glebs vorhandener Anmeldung: 194 Originale; 22 Treffer für Umrechnungskurse, 13 bis 15.07.; vollständiges Finance-Original 17.063 Zeichen. Ohne Anmeldung 401.

Der erste Live-Test zeigte einen WAL-/Read-only-Mount-Fehler. Konsistente Snapshots werden deshalb mit `readonly_snapshot.py` in den DELETE-Journalmodus überführt. Readiness prüft jetzt beide tatsächlichen Datenbanken; ein laufender HTTP-Prozess allein reicht nicht mehr. Die Produktionsdatenbank selbst wird dabei nicht umgestellt.

Die Vercel-Vorschau `dpl_4U8e6mUmGT9T47bD5fQsXga9xrxp` und die produktive Ergänzung wurden mit dem bestehenden Vercel-Connector aus geprüften öffentlichen Build-Dateien bereitgestellt. Die lokale Vercel-CLI hatte keinen gültigen Zugang; es wurde weder ein neuer Benutzerlogin noch eine zusätzliche Vercel-Berechtigung benötigt.

## Aktuelle produktive Prüfansicht

Die Bereitstellung `dpl_BguCW9ytTMWc1XM4twrfNqr6mne2` ist READY und unter der bestehenden Domain erreichbar. Sie zeigt die zwei geprüften Finance-Quellen mit zwei offenen fremden Zusagen und zwei belegten Abschlüssen. „Am Mittwoch“ erscheint als genannter Termin. Live mit der vorhandenen Eigentümer-Sitzung geprüft; keine Browserfehler. Der schreibgeschützte Review-Snapshot hat SHA256 `b431381493e6d66d84ca0f063daf0584e686bbe312b4d3d1532b1df36d8eb3df`. Der vorige Snapshot bleibt als Rückfallstand erhalten. Der gesamte 194-Quellen-Import ist weiterhin nicht produktiv veröffentlicht.
