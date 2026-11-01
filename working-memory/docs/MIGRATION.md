# Migration von Make zu n8n

## Aktueller Stand nach Freigabe am 6. September

Die Google-App wurde nach ausdrücklicher Nutzerfreigabe als **Dashboard Job** gespeichert und erfolgreich auf **In Produktion** gestellt. Startseite, Datennutzung und Nutzungshinweise sind unter `https://178-105-167-26.nip.io/dashboard-memory-info/` erreichbar. Die drei zuvor autorisierten Domains und beide OAuth-Clients blieben erhalten. Die frühere Aussage weiter unten über den gesperrten Veröffentlichungsstatus beschreibt den damaligen Stand und ist damit überholt. Nachweis: `evaluation/google-production-result.json`.

Der neue Consent in n8n ist noch separat zu bestätigen. „In Produktion“ ändert nicht den belegten Ausstellungszustand des zuvor erzeugten Sieben-Tage-Tokens. Die erneute Verbindung wurde in der Oberfläche gestartet; das separate Bestätigungsfenster verlangt Nutzerbedienung. Erst ein anschließend geprüfter Token-/Lesetest belegt den dauerhaften Zugang.

Die vollständige Wiederherstellung des neuesten Dumps wurde inzwischen in einem separaten internen Docker-Netz erfolgreich geprüft: n8n startet, Health 200, zehn Workflows, drei Credentials, Google-Refresh-Token mit dem gesicherten Schlüssel entschlüsselbar. Keine Google-API-Aufrufe aus der Testumgebung. Zum sicheren Isolieren müssen bei n8n 2.20.9 **zusätzlich zu active=false auch activeVersionId geleert und workflow_published_version entfernt werden – ausschließlich in der wiederhergestellten Testdatenbank**. Die Originaldatenbank blieb unverändert. Testcontainer, Netzwerk und temporäre Klartextdateien sind entfernt. Dump, Datenträgerkonfiguration und Umgebungs-/Compose-Dateien liegen zusätzlich lokal im privaten Backup-Verzeichnis. Nachweise: `evaluation/full-app-restore-result.json`, `evaluation/off-server-backup-result.json`.

Die produktive Domain stellt das schreibgeschützte Archiv unter `/memory-next#archiv` bereit. Der ursprüngliche Einstieg `/` bleibt bestehen. Die vollständige fachliche Migration und Umschaltung der automatischen Verarbeitung sind noch nicht freigegeben oder durchgeführt.


## Aktuell umgesetzt und geprüft

Auf `178.105.167.26` läuft ein eigener Dienst unter `/opt/dashboard-memory-preview`, nur im Docker-Netz `n8n_default`, ohne öffentlichen Port. Er nutzt eine eigene SQLite-Datenablage und verändert keine Supabase-Produktionstabellen. n8n und Picnic wurden nicht neu gestartet. Für den OAuth-Anschluss wurde der bestehende HTTPS-Proxy um den n8n-Editor ergänzt; Details und Rückweg stehen unten. Das Python-Basisimage ist per Digest fixiert; der Testdienst läuft ohne root, mit schreibgeschütztem Root-Dateisystem, eigenem Volume und begrenzter CPU/RAM-Nutzung.

Der inaktive Workflow **Dashboard Job – isolierter Importtest**, ID `cwY12LjLd4UnJoEC`, übergibt ein echtes Juni-Original an `POST http://memory-preview:8791/sources`. Die Header-Authentifizierung liegt verschlüsselt in einem n8n-Credential. Antworten enthalten eine dauerhafte Job-ID. Ein HTTP 202 bestätigt nur die Quellenannahme, nicht die fachliche Verarbeitung. Der Status ist über `GET /jobs/{id}` abrufbar.

Die Quelle wird vor dem Modellaufruf gespeichert. Hash + Quell-ID identifizieren ihre Version. Nur ein Worker besitzt die gültige Lease; die gesamte fachliche Projektion wird atomar übernommen. Transportfehler werden begrenzt wiederholt. Validierungsfehler erhalten höchstens eine technische Korrektur, keine unbegrenzten KI-Schleifen. Korrigierte oder verspätete Quellen verlangen einen getrennten chronologischen Neuaufbau. Modell-/Promptwechsel dürfen nicht still bereits importierte Quellen erneut anlegen.

Der echte n8n-Test endete mit elf Aussagen und einer persönlichen Zusage. Wiederholung, Neustart und Dienstupgrade blieben bei derselben Job-ID, elf Aussagen und drei protokollierten API-Versuchen. Der aktuelle Dienst enthält v4, Streaming, zusätzliche Handlungsprüfung und die beiden Nutzerkorrekturen. Die Juni-Testprojektion stammt weiterhin aus dem ursprünglichen v2-Lauf; das Upgrade behauptet nicht, sie neu fachlich geprüft zu haben.

## Google Drive: vorhandener Zugang, tatsächliche Hürde

Make-Szenario `5388913` besitzt bereits die passenden Verbindungen: `7501532` für Beobachtung, `7501500` für Lesen, `7501561` für Verschieben. Ein lesender RPC über `7501500` konnte die Ordner **Inbox** und **Processed** abrufen. Zugang zu Google besteht.

Der Make-Account ist jedoch pausiert: 1.000 von 1.000 Operationen verbraucht, null Rest. Nächster Reset laut API am 27. September 2026, 21:41 UTC. Der getrennte Dateilesetest `7266049` scheitert an dieser Make-Sperre. Mehr Operationen wurden nicht gekauft.

Die Make-Verbindungs-API stellt in dieser Umgebung IDs, Scopes und Ablaufmetadaten bereit, keine exportierbaren OAuth-Tokens. Ein direkt unterstützter Transfer nach n8n wurde nicht gefunden. Eine Make-Brücke würde zudem vom erschöpften Kontingent abhängen und wäre kein vollständiger Umzug. Für selbst gehostetes n8n beschreibt der Hersteller einen eigenen OAuth-Client mit Client-ID, Secret und Google-Anmeldung: [offizielle n8n-Anleitung](https://github.com/n8n-io/n8n-docs/blob/main/docs/integrations/builtin/credentials/google/oauth-single-service.md). OAuth-Zugang ist an die jeweilige Anwendung gebunden: [Google OAuth](https://developers.google.com/identity/protocols/oauth2).

Der Zielordner ist bereits bekannt: Inbox `1xUMHw3Z3zcvHE96mczw4e9HFZpUJyMoE`, Processed `1QAYD0wNVy28ApPq_Jr6WbECmKNr8TWz-`. Der neue Web-Client **Dashboard Job – n8n** ist nach ausdrücklicher Nutzerfreigabe im bestehenden Google-Projekt registriert. Die bestehende Make-Verbindung wurde nicht verändert. Die n8n-Browser-Anmeldung und Google-Autorisierung sind abgeschlossen.

## Zielablauf und Verantwortlichkeiten

n8n übernimmt Abholung, vollständige Pagination, Metadaten, Originalexport und Betriebsstatus. Die Python-Komponente übernimmt Quellenversionen, Kontextbildung, Modellaufrufe, Belegprüfung, Korrekturen und transaktionale Änderungen. Keine fachlichen Regeln als untestbare Verzweigungssammlung im Workflow.

1. Im Schattenbetrieb Inbox und für den historischen Test ausgewählte Processed-Dateien nur lesen; keine Datei verschieben. Google Docs als Text exportieren, Textdateien unverändert lesen. Dateityp, ID, Revision, Änderungszeit und Originalbytes protokollieren. Andere Typen ausdrücklich als nicht unterstützt behandeln.
2. Alle Seiten der Dateiliste lesen. Cursor erst nach dauerhafter Quellenannahme vorziehen. Wiederholung ist zulässig, Überspringen nicht. Die Umstellung muss erstellte **und geänderte** Dateien berücksichtigen; das bisherige „create“ allein genügt nicht.
3. Stabile ID-Normalisierung einmal festlegen: `drive:<fileId>`. Die lokalen Forschungsdaten enthalten teilweise rohe Drive-IDs, der n8n-Test bereits den Präfix. Vor gemeinsamen Replays eine explizite Alias-Tabelle erstellen; keine stillen parallelen Identitäten.
4. Ereignisdatum aus der tatsächlichen Quellenmetadaten-/Dateinamenskonvention prüfen; Dateierstellung ist kein Ersatz für Meetingdatum. Unklare Zeitmetadaten als Betriebsfall zurückhalten.
5. Auf `applied` warten. Fehler behalten die Quelle und einen begründeten Status; sie erzeugen keine persönliche Aufgabe. Erst nach Freigabe kann eine Datei zusätzlich nach Processed verschoben werden. Idempotenz darf nie vom Verschieben abhängen.
6. Änderungen zuerst in einem getrennten Datenbestand und einer getrennten Übersicht zeigen. Eine abgeschlossene Extraktion ist keine automatische Übernahme in die bisherigen Tabellen.

## Sicherung und Rückweg

Am 6. September erzeugt: PostgreSQL-Dump von n8n, n8n-Datenverzeichnis, Compose-/Umgebungsdateien und Online-SQLite-Backup des Testdienstes. Serverablage `/opt/dashboard-memory-preview/backups/2026-09-06`, Verzeichnisrechte 700, sensible Dateien 600. Der PostgreSQL-Dump wurde in einem separaten temporären PostgreSQL-16-Container ohne Netzwerk wiederhergestellt: sieben Workflows, zwei Credentials. Anschließend wurde nur dieser Testcontainer entfernt. Das SQLite-Backup bestand `integrity_check`; Quelle, Job, elf Beobachtungen, ein Arbeitsereignis und drei Runs blieben erhalten. Das Archiv ersetzt keinen Test der vollständigen n8n-App-Wiederherstellung samt Entschlüsselung der Credentials.

Noch offen: regelmäßige verschlüsselte Offsite-Sicherung, definierte Aufbewahrung, Wiederherstellungsübung der vollständigen Anwendung und Monitoring des verfügbaren Speichers. Keine zusätzliche geplante Automation wurde eingerichtet.

Rückweg heute: den separaten Testworkflow deaktiviert lassen und nur `memory-preview` stoppen. Bestehende Make-/Supabase-Daten bleiben lesbar. Vor einem späteren Cutover müssen Original-Blueprint, Triggerdefinitionen, Tabellenexport mit Prüfsummen und Importcursor als gemeinsamer Stand gesichert werden. Codewechsel des Preview-Dienstes erfordern keine Bearbeitung von Picnic. Für den letzten Upgrade-Schritt liegen vorherige Dienstdateien zusätzlich in `rollback-v2`; für ein vollständiges Rollback sind die dazu passenden Promptdateien und das gesicherte Image/Artefakt mitzunehmen.

## Kontrollierte produktive Umschaltung – noch nicht ausgeführt

Voraussetzungen: eigener funktionsgeprüfter Drive-Zugang in n8n; unabhängige fachliche Abnahme; zuverlässiger Archivkontext; authentifizierte Anbindung der Dashboard-Oberfläche; geprüfte Herkunftszuordnung und Migration des Altbestands; Restore und Monitoring.

Dann ein abgegrenztes Zeitfenster festlegen, Make-Import kontrolliert stoppen, alle bis zum Stichtag übernommenen Quellversionen abgleichen, n8n-Import in Produktion aktivieren und ausschließlich die nachweislich ersetzten Supabase-Folgeprozesse deaktivieren. Die doppelten Embedding-Trigger gezielt korrigieren. Suche und Aufgaben müssen denselben belegten Zustand verwenden. Wiederaufnahme von Make darf nur aus einem geprüften Cursor erfolgen, damit bereits durch n8n angenommene Dateien nicht erneut entstehen.

Der Nutzer verlangt die Freigabe ausdrücklich erst anhand eines konkreten geprüften Ergebnisses. Deshalb erfolgt aktuell weder die produktive Umschaltung noch eine Bestandsänderung. Das ist eine Grenze des Auftrags, keine vom Skill erfundene Zustimmungspflicht.


## Lokaler React-Anschluss

`server.py` unterstützt zusätzlich `MEMORY_READ_ONLY=1`: bestehende SQLite-Datei mit `mode=ro` öffnen, keinen Worker starten, POST mit HTTP 405 ablehnen. `GET /review?as_of=YYYY-MM-DD` liefert den historischen Stand samt Herkunft und Verarbeitungsstatus; `GET /sources/{source_version}` liefert das vollständige Original hinter derselben Bearer-Grenze. `preview_service.py` erzeugt nur einen lokalen Testschlüssel und startet diesen Modus auf Loopback.

Der Vite-Proxy erlaubt nur GET für Review und konkrete Quellversionen, setzt den Schlüssel ausschließlich serverseitig, weist fremde Origins ab und sperrt direkte Zugriffe auf `.local` einschließlich `?raw` und `/@fs`. Das ist eine lokale Entwicklungsanbindung. Eine produktive Supabase-Sitzung wird noch nicht in eine Berechtigung am neuen Dienst übersetzt. Die neuen lokalen Änderungen wurden in diesem Schritt nicht auf Hetzner ausgerollt. Der Docker-Build nimmt das neue API-Modul bereits mit auf.

## Drive-Lesefluss: inzwischen in n8n geprüft

Zusätzlich angelegt, beide inaktiv:

- `HBcyXUYrYVKhf6jG` – **Dashboard Job – Drive-Originale im Lesetest**. Vollständige Inventur von Inbox und Processed; anschließend ausdrücklich nur die Finance-Quelle vom 15.07. lesen. Das neue OAuth2-Credential `a993APea0CMGhIL1` ist mit allen drei HTTP-Knoten verbunden. Der echte Lesetest ist erfolgreich abgeschlossen; siehe Nachweise unten.
- `1hpLAMykma91hFdx` – **Dashboard Job – Drive-Vertragstest (synthetisch)**. Derselbe Ablauf gegen einen temporären privaten HTTP-Testdienst; keine Google-Verbindung und kein Modellaufruf.

Zehn Node-Vertragstests bestehen. Der Ablauf wurde außerdem auf dem bestehenden n8n 2.20.9 ausgeführt: drei Listenseiten, darunter eine leere Zwischenseite, zwei unterschiedliche Originalformate, chronologische Sortierung und korrekte Zuordnung über n8ns Item-Verknüpfung. Beide Texte behalten ihre CRLF-Zeilenenden. Bei einer zwischen Liste und Nachprüfung geänderten Version bricht der Ablauf erwartungsgemäß ab. Der temporäre Testcontainer wurde anschließend entfernt. Die bestehenden n8n-/Picnic-Container wurden dafür nicht neu gestartet.

Der Lesefluss benutzt ausschließlich GET. Er gibt `read_verified_not_imported` aus: gelesen und auf konsistente Version geprüft, noch nicht als Arbeitsgedächtnis-Quelle übernommen. Es gibt bewusst keinen Modell-/Intake-Knoten in diesem Vorabtest. Fehler, Seitenlimits, wiederholte Cursor, doppelte IDs, fehlende ausgewählte Dateien, fremde Ordner, unklare Datumspräfixe, nicht unterstützte Formate und zu große/fehlerhaft decodierte Texte führen zum Abbruch statt zu einem unbemerkten Teilimport. Originalversion und Änderungszeit werden vor/nach dem Lesen verglichen. Ein inhaltlicher SHA-/MD5-Abgleich der ursprünglichen Drive-Bytes ist damit noch nicht nachgewiesen.

Die tatsächlich verwendeten HTTP-Request-Parameter stammen aus dem installierten n8n-Node. Google dokumentiert weitere Seiten über `nextPageToken` und kennzeichnet unvollständige Suchen über `incompleteSearch`: [Drive files.list](https://developers.google.com/workspace/drive/api/reference/rest/v3/files/list). Google-Dokumente werden als vollständiger Text exportiert: [Drive files.export](https://developers.google.com/workspace/drive/api/reference/rest/v3/files/export). Lokale Dateien: `n8n/drive-contract.mjs`, `n8n/drive-contract.test.mjs`, `n8n/build-drive-read-test.py`, `n8n/drive-read-test.json`; Nachweis: `evaluation/n8n-drive-contract-result.json`.

## Tatsächlich vorhandenes Google-Projekt und nächste Zugangsaktion

Die bereits angemeldete Google Cloud Console zeigt das passende Projekt **Tactiq Make Google Drive** (`core-field-493918-h6`). Darin existiert der aktive Web-Client **Make.com**, zuletzt laut Console am 30. August benutzt. Seine einzige registrierte Rückrufadresse ist `https://www.integromat.com/oauth/cb/google-restricted`. Der bestehende Clientschlüssel wird von Google nicht mehr zum Anzeigen oder Herunterladen angeboten. Er wurde weder geändert noch rotiert. Das andere Cloud-Projekt „Finanz-App“ wird hierfür nicht verwendet.

Der separate Web-Client **Dashboard Job – n8n** wurde am 6. September 2026 nach ausdrücklicher Nutzerfreigabe erstellt. Client-ID: `79573689684-0uqv35p1t0dgiii7jqf9io413v1pfede.apps.googleusercontent.com`. Registrierte Rückrufadresse: `https://178-105-167-26.nip.io/rest/oauth2-credential/callback`. Der heruntergeladene Schlüssel liegt mit Dateirechten 600 ausschließlich in privaten lokalen/serverseitigen Dateien und verschlüsselt im n8n-Credential **Dashboard Job – Google Drive (nur Lesen)**, ID `a993APea0CMGhIL1`. Keine Schlüsselwerte in versionierten Dateien.

Das generische n8n-OAuth2-Credential fordert ausschließlich `https://www.googleapis.com/auth/drive.readonly` an. Authorization Code, Google-Tokenendpoint, `access_type=offline&prompt=consent`, Client-Authentifizierung im Request-Body. Die öffentliche Credential-Schema-API von n8n 2.20.9 verlangte zusätzlich `serverUrl` trotz statischem Client; ein leerer Wert sowie `jweEnabled=false` wurden vom Schema akzeptiert. Keine dynamische Client-Registrierung aktiviert. Das Credential ist an alle drei HTTP-Knoten des weiterhin inaktiven Lesetests gebunden. Google hat genau `drive.readonly` gewährt; Access- und Refresh-Token sind im verschlüsselten Credential vorhanden.

### HTTPS und authentifizierter Rückruf

Die Rückrufadresse folgt dem installierten `UrlService`/`FrontendService`: ohne `N8N_EDITOR_BASE_URL` verwendet n8n die vorhandene `WEBHOOK_URL` als Instanzbasis. Eine zunächst nur entworfene exakte Callback-Route genügte bei weiterer Prüfung nicht: Die installierte `OauthService.decodeCsrfState` prüft zusätzlich den angemeldeten Nutzer aus derselben Browser-Sitzung. Eine Anmeldung über localhost würde deshalb beim öffentlichen HTTPS-Rückruf fehlen. Die Authentifizierungsprüfung wurde nicht abgeschaltet.

Am 6. September wurde stattdessen `location /` auf dem vorhandenen TLS-Host als Proxy zur bereits auf Port 5678 erreichbaren n8n-Oberfläche ergänzt. Anmeldung und OAuth-Rückruf verwenden damit denselben HTTPS-Ursprung. Die bestehenden exakten Alexa- und `/webhook/`-Blöcke sind unverändert. Vor der Änderung wurde die Ausgangsprüfsumme geprüft und die Konfiguration mit `nginx -t` separat validiert. Nach Sicherung und Einbau folgten erneut `nginx -t` und ein sanftes Nginx-Reload; n8n und Picnic liefen ohne Neustart weiter.

Geprüft mit normaler TLS-Zertifikatsprüfung: HTTPS-Startseite 200/n8n, `/healthz` 200, nicht angemeldetes `/rest/login` sowie `/rest/oauth2-credential/callback` jeweils 401. Die Browser-Oberfläche zeigt die normale n8n-Anmeldung. Der frühere Entwurf `n8n/nginx-oauth-callback.conf` ist als überholt gekennzeichnet; der tatsächlich ergänzte Block steht in `n8n/nginx-n8n-https.conf`.

Vorherige Konfiguration: `/opt/dashboard-memory-preview/backups/2026-09-06/nginx-alexa-before-n8n-https.conf` (600). Ausgangs-SHA256 `da701f6f006cbedbc3c368f00250f3859deedb0a0588ae9f74551b5c43c587e9`, neuer SHA256 `7c7ebd34fd05ea6300ba20a6e4d99d3e88c657fb93c187cfbc4577f29610a8fa`. Rückweg: nur bei unverändertem neuen Hash die Sicherung auf die ursprüngliche Zieldatei zurückspielen, `nginx -t`, danach Nginx neu laden. Keine Datenbank- oder Workflow-Rücksetzung erforderlich. Maschinenlesbarer Stand: `evaluation/drive-setup-status.json`.

### Erledigter Zugang und verbleibende Integration

Der Nutzer hat seinen Kontozugang wiederhergestellt und sich angemeldet. Die Oberfläche zeigt **Account connected** am vorbereiteten Google-Credential. Der echte Lesetest sowie eine vollständige getrennte Originalsicherung sind abgeschlossen. Anbindung an die dauerhafte Quellenannahme, Versions-/Alias-Migration in den Arbeitszustand, Archivkontext und produktive Umschaltung sind weiterhin offen.

### Vorhandener Google-Teststatus

Die Console zeigt den Veröffentlichungsstatus **Test**, den vorhandenen Testnutzer `gleb.komzin@gmail.com` und weiterhin den gemeinsamen Zustimmungsnamen **Make**. Deshalb kann auch die Anmeldung des neuen Clients unter diesem Namen erscheinen. Google meldet außerdem unvollständige Branding-Angaben; die Veröffentlichungsschaltfläche ist gesperrt. Die vorhandenen Projekt-/Branding-Einstellungen wurden nicht verändert. Der konkrete Test-Consent war trotz dieses Hinweises erfolgreich; eine dauerhafte Veröffentlichung ist damit nicht nachgewiesen.

Für diesen externen Teststatus mit Drive-Scope dokumentiert Google eine Lebensdauer von sieben Tagen für neue Refresh-Tokens. Ein bestandener einmaliger Lesetest wäre deshalb noch kein Nachweis eines dauerhaft unbeaufsichtigten Zugangs. Vor produktiver Umschaltung muss der Veröffentlichungs-/Autorisierungsweg abschließend geklärt werden. Quelle: [Google: Refresh token expiration](https://developers.google.com/identity/protocols/oauth2#expiration), geprüft am 6. September 2026.

### Kontowiederherstellung am 6. September

Nach ausdrücklicher Nutzeranweisung wurde für das bestehende Konto ein auf 20 Minuten begrenzter Passwort-Reset-Link mit den Methoden der installierten `AuthService`/`JwtService` serverseitig erzeugt. Der normale n8n-Endpunkt `resolve-password-token` bestätigte ihn mit HTTP 200; die Oberfläche zeigt die beiden Felder für das neue Passwort. Das ist eine gezielte administrative Wiederherstellung über interne n8n-Methoden, kein dokumentierter separater CLI-Befehl. Die Funktion zur gesamten Rücksetzung der Benutzerverwaltung wurde nicht ausgeführt. Benutzer-, Rollen-, Workflow- und Credential-Datensätze wurden hierfür nicht geändert.

Der Nutzer übernimmt das Eingeben und Bestätigen des neuen Passworts in der n8n-Oberfläche. Der Token ist an den bisherigen Passwortstand gebunden und verfällt nach 20 Minuten. Der Link und zugehörige private Dateien gehören nicht in versionierte Dokumente. Der Nutzer bestätigte anschließend die Anmeldung; die Browser-Oberfläche zeigt die bestehende Workflow-Übersicht mit neun Workflows. Die Passwortwiederherstellung ist damit abgeschlossen.

## Echter Drive-Zugang und vollständiges Originalarchiv

Am 6. September bestätigte die n8n-Oberfläche **Account connected**. Ein ausschließlich auf das neue Credential begrenzter serverseitiger Metadatencheck bestätigt den tatsächlich gewährten Scope `https://www.googleapis.com/auth/drive.readonly`, ein Access-Token und ein Refresh-Token. Google nennt für letzteres `refresh_token_expires_in=604799` Sekunden, also rund sieben Tage. Schlüsselwerte wurden dabei nicht ausgegeben. Der bestehende Google-Teststatus ist deshalb weiterhin eine Betriebsgrenze vor produktiver Umschaltung.

Der einzelne Finance-Lesetest `HBcyXUYrYVKhf6jG` wurde erfolgreich ausgeführt. Die Inventur enthielt 194 Google Docs auf einer vollständigen Seite. Das Original vom 15.07. hat 17.338 Zeichen: einen 275 Zeichen langen Tactiq-Kopf und anschließend exakt den bisher geprüften Transkripttext mit 17.063 Zeichen. Vollständiger Export-SHA256 `7b39c24dd6d8986029c8f3207ddb832bc8fef95f79a3c529dde3e9f3c6863653`; Transkript-SHA256 `d2fc918e906b0d3bd43124ea575f5da313fb2a992fb3d0d19bcb6d6703607130`. Keine Whitespace-Normalisierung, keine entfernte Schlusszeile. Nachweis: `evaluation/n8n-drive-real-result.json`.

Zusätzlich wurde der inaktive Workflow **Dashboard Job – Drive-Archiv im Lesetest**, ID `ShAclE07wIjOSFlI`, angelegt und einmal vollständig ausgeführt. Er liest alle aktuellen Originale aus Inbox und Processed, vergleicht Version/Metadaten vor und nach jedem Export und erzeugt keine fachlichen Imports. Die tatsächlich vorhandenen Dateinamen ohne Leerzeichen nach dem ISO-Datum werden jetzt ausdrücklich unterstützt. Unterschiedliche Drive-IDs bleiben auch bei gleichem Namen getrennt. Zehn Node-Tests bestehen. Der Archivlauf erlaubt bis zu vier Millionen Zeichen je Export; der normale einzelne Intake-Lesetest behält seine Grenze von 140.000 Zeichen. Das Modell-Kontextlimit wurde nicht angehoben.

Ergebnis: **194 von 194 Quellen**, 7.595.705 exportierte Zeichen, Ereigniszeitraum 24.02.–31.08.2026. Alle Quellen verwenden den erkannten Tactiq-Kopf. Der größte Export umfasst 218.955 Zeichen; zwei Transkriptkörper überschreiten 140.000 Zeichen und verlangen vor Verarbeitung eine gesonderte Kontextstrategie. Alle acht bisher lokal geprüften Referenztranskripte stimmen exakt mit jeweils einem eindeutigen Drive-Transkriptkörper überein. Keine automatischen Zusammenführungen aufgrund ähnlicher Titel. Nachweis einschließlich der acht Zuordnungen: `evaluation/n8n-drive-archive-result.json`.

`archive_drive.py` archiviert ausschließlich vollständig erfolgreiche Ausführungen und verlangt genau eine Ausgabe je Inventur-ID. Bestehende Archivverzeichnisse werden nicht überschrieben. Vollständiger UTF-8-Textexport und abgeleiteter Transkriptkörper erhalten eigene SHA256-Dateien, Herkunftsmetadaten und den expliziten Zeichenoffset des erkannten Kopfes. Beide gespeicherten Inhalte werden nach dem Schreiben nochmals gegen Hash und Ableitung geprüft. Unbekannte Kopf-/Exportformate bleiben unverändert. Die Prüfung am echten Finance-Ergebnis bestätigt zusätzlich: Teilinventur wird abgewiesen, vorhandenes Ziel wird abgewiesen, bisheriger Korrekturhash bleibt im abgeleiteten Körper exakt erhalten. Das sind geprüfte Exporttexte, keine Behauptung über die nativen internen Google-Docs-Bytes.

Private Ablagen: lokal `working-memory/.local/drive-archive-2026-09-06`, serverseitig `/opt/dashboard-memory-preview/drive-archive-2026-09-06`; Verzeichnisrechte 700, Text-/Manifestdateien 600. Vollständige n8n-Ausgaben bleiben ebenfalls privat. Die versionierten Nachweise enthalten Zusammenfassungen/Hashes, keine Originaltranskripte oder Tokens. **Keine Modellaufrufe, keine Aufgabenübernahme, keine Änderung oder Verschiebung in Drive, keine produktive Umschaltung.** Ein erneuter Quellenabgleich vor der späteren Umschaltung bleibt nötig, da eine Dateiliste keine globale, zeitlich eingefrorene Drive-Sicherung darstellt.

Nach Google-Verknüpfung und Kontowiederherstellung wurde ein weiterer PostgreSQL-Dump erstellt: `backups/2026-09-06/n8n-after-google-connection.dump`, 3.364.340 Bytes, SHA256 `903dddc180aa9ad13fb7b43bc28fc61b5ed33e1971b5fca085a8718fde59904d`. Der Dump-Katalog ist mit `pg_restore --list` lesbar. Für diesen neuesten Stand wurde keine erneute vollständige App-Wiederherstellung behauptet. Der temporäre lokale Passwort-Linkdienst wurde beendet und die dafür angelegten privaten Linkdateien wurden entfernt.

## Backend-Vorbereitung Hetzner, 03.10.2026

Das isolierte Paket `HZ-MIGRATION-20261003` liegt unter `../ops/hetzner-migration/`; prüfbare Ergebnisse stehen in `stage-evidence.json`. Fünf gepinnte ARM64-Dienste sind intern gesund, der vollständige Source-Dump wurde einmal restauriert und alle 88 abgedeckten Tabellen mit 68.572 Zeilen stimmen mit dem Export überein. Auth/RLS/Owner- und Journal-Verträge sind integriert geprüft; das einzelne Vault-Secret ist mit ursprünglicher UUID und gleichem entschlüsseltem Hash unter dem Zielschlüssel wiederhergestellt. Vollständiger Dump, Vault-Recovery-Sidecar, Edge-Exports und Hashmanifest liegen zusätzlich privat im bestehenden Mac-Offserver-Backuproot.

Recovery bleibt nach zwei gescheiterten lokalen Mailcapture-Prüfungen offen; SMTP-TLS-Authentifizierung ohne Mailversand ist bestanden. Der Lead hält dafür das STALL-Review. Die abgelaufene Source-CLI-Rolle konnte mangels CREATEROLE/ADMIN-Recht nicht gelöscht werden und ist nicht als bereinigt attestiert. Keine öffentliche Zielroute, Produktionsumstellung oder abschließender Source-Export ist erfolgt. Vor dem späteren Cutover sind tägliche/offserver PostgreSQL-/Auth-/Crypto-Sicherung, Recovery-Abnahme und kontrollierter einzelner Writer nach Lead-Gate erforderlich.

Das einmalige, nach STALL-Review freigegebene Recovery-Folgepaket scheiterte ebenfalls: SMTP Greeting/EHLO aus dem Auth-Netz bestanden, danach genau ein Recoveryrequest HTTP500 wegen Docker-DNS-Auflösung des Capturehosts. Temporäre SMTP-Konfiguration ist zurückgesetzt, Capture entfernt; Link/Reset bleiben offen. Keine weitere automatische Runde ist freigegeben.
