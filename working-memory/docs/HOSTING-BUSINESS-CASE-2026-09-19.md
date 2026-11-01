# Supabase-Limit und Hosting-Business-Case

Stand: 19.09.2026. Beratung und lesende Prüfung; keine Infrastruktur geändert, keine Daten gelöscht, nichts bestellt.

## Entscheidungsempfehlung

Keinen Supabase-Pro-Plan aus Panik buchen und vorerst keinen Homeserver kaufen. Zunächst Datenbankplatz gezielt zurückgewinnen und die Datensicherung reparieren. Mittelfristig ist Postgres mit pgvector auf dem vorhandenen Hetzner-Server plus bestehendem Python-Backend die wirtschaftlich passende Richtung. Anmeldung kann zunächst bei Supabase Free bleiben; vollständige Unabhängigkeit ist ein gesonderter Auth-Umzug.

Ein zweiter Server ist nach der Kapazitätsstichprobe nicht zwingend. Eine Erweiterung auf 8 GB RAM schafft später Reserven, kostet bei aktuellen Hetzner-Neupreisen allerdings mehr als 8 Euro inklusive IPv4 und Backups. Ein Homeserver bietet zusätzliche private Funktionen, spart gegenüber 4–8 Euro monatlich aber innerhalb von vier Jahren kein Geld.

## 1. Was bei Supabase tatsächlich gemessen wurde

**Aktualisierung 20.09., nach Mitternacht:** 599.739.539 Bytes (599,7 MB) nach produktiver Chatindexierung und Releaseprüfung; keine offenen Backup-Snapshots. Aktiver Suchbestand302,4 MB, alter Chunkindex weiterhin85,3 MB, Chat-Aufrufbelege17,5 MB, gespeicherte Suchergebnisse17,0 MB. Die nachfolgende Tabelle dokumentiert die erste Messung. Das Free-Limit ist damit weiterhin überschritten; es wurde kein Tarifwechsel gebucht.

Organisation im Free-Plan, Projekt Dashboard Job aktiv/healthy. PostgreSQL meldet **527.633.555 Bytes**, also **527,6 MB / 503,2 MiB**. Das liegt über dem veröffentlichten 500-MB-Datenbankkontingent. Die genaue UI-Abrechnungseinheit kann vom gerundeten Marketingwert abweichen; es wird deshalb kein scheinpräziser Überschreitungsprozentsatz behauptet.

`default_transaction_read_only` ist derzeit `off`; die Datenbank ist also nicht bereits auf diesem Weg schreibgeschützt. Ein Auth-Nutzer, keine Objekte im Supabase-Dateispeicher. Monatlicher Egress, Edge-Aufrufe und die konkrete Warnmeldung waren über die verfügbaren Tools nicht sichtbar. Das Dashboard verlangt eine erneute Anmeldung. Die Datenbanküberschreitung ist belegt; ob die erhaltene Nachricht zusätzlich oder stattdessen Egress betrifft, bleibt bis zur Nachricht/Usage-Ansicht offen.

| Bereich | Belegung inkl. Indizes, dezimale MB | Einschätzung |
| --- | ---: | --- |
| Neuer Suchindex `wm_search_documents` | 255,6 | Aktiver Suchbestand; nicht pauschal löschen |
| Alter Index `transcript_chunks` | 85,3 | Stillgelegte Altlogik; nach vollständiger Sicherung Kandidat zum Auslagern |
| Cronlaufhistorie `cron.job_run_details` | 46,2 | 36.931 tatsächlich gezählte Protokolleinträge |
| Technische HTTP-Antworten `net._http_response` | 41,6 | Nur 90 aktuelle Einträge; erhebliche reservierte Relation, kein Beweis für 41 MB löschbare Nutzdaten |
| Gespeicherte Suchergebnisse | 14,3 | Wiederholbarkeit beachten |
| Modellaufrufbelege | 10,2 | Wichtig für Kosten-/Wiederholungsschutz; nicht blind aufräumen |
| Archivoriginale `wm_archive_documents` | 9,7 | Originalnotizen sind nicht der Hauptverbraucher |

Der neue Index enthält 13.654 Suchdokumente. Die Textkörper zusammen sind nur rund 11,1 MB; Vektoren, Indizes, Metadaten und Datenbankverwaltung machen einen erheblichen Anteil aus. 574 Suchdokumente liegen außerhalb aller gespeicherten Suchsnapshots. Das allein erlaubt keine Löschung: offene Jobs und Wiederaufnahme müssen ebenfalls geprüft werden. Gleiche Textkörper an verschiedenen Quellen können fachlich berechtigt sein.

Kurzfristig scheint eine Entlastung um mehrere Dutzend MB plausibel. Die 85,3 MB des alten Chunkbestands plus alte Protokolle sind deutlich relevanter als das Kürzen von Originalnotizen. Das exakte Einsparpotenzial muss nach Sicherung und Abhängigkeitsprüfung ermittelt werden. Normales DELETE gibt nicht automatisch entsprechend viel Platz an das Betriebssystem zurück; Kompaktierung kann Sperren und temporären Platz benötigen. Hier wurde nichts gelöscht oder kompaktiert.

Supabase verlangt keinen automatischen kostenpflichtigen Wechsel: Free bleibt ohne Rechnung, bei anhaltender Überschreitung können Funktionen eingeschränkt werden. Pro beginnt bei 25 USD/Monat; es ist eine Option, keine technisch alternativlose Voraussetzung. Quellen: [Preise](https://supabase.com/pricing), [Kostenkontrolle](https://supabase.com/docs/guides/platform/cost-control), [Datenbank- und Diskgröße](https://supabase.com/docs/guides/platform/database-size).

## 2. Hetzner: live geprüfte Kapazität

Lesende SSH-Stichprobe am 19.09. gegen 20:21 Uhr deutscher Zeit:

- 2 virtuelle CPU-Kerne.
- 3.805 MiB RAM insgesamt, etwa 1.903 MiB verfügbar; kein Swap.
- Root-Dateisystem 38 GiB, 15 GiB belegt, rund 21 GiB verfügbar.
- Dashboard-Container etwa 692,5 MiB bei 1-GiB-Limit.
- n8n etwa 596,8 MiB; dessen Postgres etwa 180,9 MiB; Picnic etwa 23 MiB.
- Kurze CPU-Stichprobe überwiegend im Leerlauf; das ist keine Lastmessung während kompletter Transkriptverarbeitung oder Wiederherstellung.

Die aktuelle Dashboard-Verarbeitung ist pausiert. Deshalb ist der freie RAM kein Beleg, dass beliebige zusätzliche Last sicher hineinpasst. Für einen getrennten, begrenzten Postgres-Container mit pgvector ist ein Test auf dem bestehenden Server trotzdem plausibel. Die vorhandene n8n-Datenbank sollte dabei nicht unkontrolliert mit Appdaten vermischt werden. Datenbank und Backups passen größenmäßig deutlich eher auf die Platte als auf das Supabase-Free-Kontingent; Wachstum und Sicherungskopien bleiben zu planen.

Ein zweiter Server wäre vor allem für Fehlerisolation oder stark wachsende Last sinnvoll. Mehrere Projekte können denselben Host nutzen, jeweils mit eigenen Diensten, Datenbanken, Zugängen und Ressourcenlimits. Ein Hostausfall trifft dann alle Projekte; Container allein sind keine Hochverfügbarkeit.

## 3. Was ein Umzug konkret bedeutet

Aktiver Datenpfad: Browser → Vercel-Weiterleitung → Hetzner-Python → Supabase-Journal-Gateway → PostgreSQL. Supabase-Anmeldung ist weiterhin aktiv. Die alte breite Browser-CRUD-Schicht gehört zur nicht mehr eingebundenen Altoberfläche und muss für diesen Umzug nicht neu gebaut werden.

| Variante | Einschätzung |
| --- | --- |
| Supabase Free aufräumen | Schnellste Entlastung, kein Anbieterwechsel. Muss mit begrenzter Aufbewahrung und Wachstumsüberwachung ergänzt werden. |
| Datenbank + Gateway nach Hetzner, Auth zunächst Free | Bevorzugte Zwischenlösung. Kein kompletter UI-Umbau; pgvector/FTS, SQL-Funktionen, Ownerprüfung, Queue und Wiederholungsschutz übernehmen. Externe Auth-Abhängigkeit bleibt. |
| Vollständiger Supabase-Stack selbst hosten | Technisch möglich und kompatibel, aber für diese App relativ viele zusätzliche Dienste. Hersteller: mindestens 4 GB RAM/2 Kerne/40 GB SSD, empfohlen 8 GB+/4 Kerne/80 GB+. Diese Werte gelten für Supabase allein, nicht zusätzlich zu n8n. |
| Schlankes Backend mit vollständig eigener Anmeldung | Langfristig unabhängig, aber Login, Sitzungen, Passwortzurücksetzung, E-Mail und Rechteprüfung müssen zuverlässig übernommen werden. Bewährten Auth-Baustein verwenden, keine selbst erfundene Kryptografie. |
| Anderer kostenloser Datenbankdienst | Häufig nur Verschiebung desselben Limits. Neon Free hat ebenfalls 0,5 GB pro Projekt; Auth und Gateway wären trotzdem umzuziehen. |

Die Datenmigration benötigt eher mehrere Arbeitstage für Adaption, Tests und sicheren Wechsel als einen einfachen URL-Tausch. Grobe Planungsspanne: Daten/Gateway mit zunächst beibehaltenem Auth 3–7 Arbeitstage; eigener Auth-Umzug zusätzlich 2–5. Das sind technische Schätzungen, keine Zusage oder abrechenbare Beauftragung. Bestehende Tests können den Aufwand verringern, unerwartete Auth-/Restoreprobleme erhöhen ihn.

Vor Umzug: aktuellen Backupfehler beheben, vollständige Sicherung einschließlich Auth und bisher aus dem kanonischen Paket ausgelassener Altbestände erstellen, isoliert wiederherstellen; dann Arbeitsabläufe mit genau einem schreibenden System umschalten. Ein kaputtes Backup wird durch Umzug nicht repariert.

Quellen: [Supabase Self-hosting](https://supabase.com/docs/guides/self-hosting/docker), [Neon Free-Limits](https://github.com/neondatabase/website/blob/main/content/faqs/free-plan-limits-and-quotas.md). Implementierungsbefund aus aktiver Entry/MemoryApp, Auth, Gateway, Server und Restore-Runbook.

## 4. Aktuelle Cloud-Kosten und Alternativen

Deine heutigen knapp 4 Euro sind die von dir genannte Bestandsrechnung, nicht von mir eingesehen. Aktuelle Hetznerpreise für Neubestellung/Rescale seit 15.06.2026 können davon abweichen. Ein Rescale kann einen alten günstigen Tarif auf den neuen Preis umstellen.

| Konfiguration | Monat brutto, DE 19 % | Enthalten / Grenze |
| --- | ---: | --- |
| Bestehender Hetzner unverändert | ca. 4,00 € laut Nutzer | Zunächst Kapazität nutzen, kein Tarifwechsel |
| Hetzner CX23: 2 vCPU / 4 GB / 40 GB | 7,13 € | Server + IPv4; ohne Backup |
| Derselbe mit Hetzner-Backup | 8,43 € | 20-%-Backupaufschlag auf Serverpreis |
| Hetzner CX33: 4 vCPU / 8 GB / 80 GB | 10,70 € | Server + IPv4; ohne Backup |
| Derselbe mit Hetzner-Backup | 12,72 € | Mehr Reserve für mehrere Projekte |
| netcup VPS Lite 2: 4 vCore / 8 GB / 160 GB SSD | 7,92 € | IPv4/IPv6 enthalten, drei Monate Mindestlaufzeit; unabhängiges Backup zusätzlich |

Hetzner-Rechnung: CX23 5,49 € netto + IPv4 0,50 €, optional Backup 1,098 €; CX33 8,49 € + 0,50 € + optional 1,698 €. Danach jeweils 19 % MwSt. Nicht schon Bruttopreise nochmals besteuern.

Hetzner-Tarife sind kapazitätsabhängig; Neubuchbarkeit wurde nicht im eingeloggten Bestellprozess geprüft. Netcup Lite nutzt SSD statt NVMe und hat geringere Bandbreite/Interfaceleistung als dessen reguläre VPS. Nur für wenige Euro Differenz lohnt ein zusätzlicher Anbieterumzug häufig nicht; bei später notwendigem Wechsel ist der 8-GB-Tarif aber eine echte Budgetalternative. Ein zweiter zusätzlich laufender VPS kostet selbstverständlich zusätzlich zum bestehenden Server, solange dieser nicht entfällt.

Netcup-Produktdetails live gelesen: 0 Euro Einrichtung, drei Monate Abrechnungsperiode, 750 MBit/s Interface; Drosselung auf 100 MBit/s bei mehr als 100 MBit/s Durchschnitt über 24 Stunden. Standort wird in Europa zugeteilt. [Konkreter Tarif](https://www.netcup.com/de/server/vps/vps-lite-2-g12s-3m).

Quellen: [Hetzner neue Preise](https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/), [IPv4/Server](https://docs.hetzner.com/cloud/servers/overview/), [Backupabrechnung und Bestandspreise](https://docs.hetzner.com/cloud/billing/faq/), [netcup Lite](https://www.netcup.com/de/server/vps-lite). VM-Snapshots sind kein Ersatz für getestete Datenbankwiederherstellung und unabhängige Datensicherung.

## 5. Homeserver: sinnvolle Zielkonfiguration für 3–4 Jahre

Für einige private Webapps, n8n, Datenbanken und Hausdienste würde ich planen:

- Stromsparender x86-Mini-PC mit etwa 6–8 CPU-Kernen, z. B. Ryzen-U-Klasse; keine dedizierte Grafikkarte nötig.
- **32 GB RAM**, möglichst wechselbar und bis 64 GB erweiterbar. Mehr RAM ist hier wichtiger als eine schnelle Gaming-CPU.
- **1 TB NVMe-SSD**, optional zweiter Speicherplatz; externe Sicherungsplatte getrennt davon.
- Mindestens Gigabit-LAN, 2,5-Gigabit-LAN als sinnvolle Reserve für lokale Dateidienste; verkabelter Betrieb.
- Automatischer Neustart nach Stromausfall, Linux-Kompatibilität, vernünftige Kühlung; kleine USV für sauberes Herunterfahren.
- Planungsbudget **500–700 € für den Rechner**, zusätzlich etwa **150–250 € für Sicherungsmedium/USV**. Das sind Budgetannahmen, kein verbindliches Komplettangebot.

Eine Herstellerreferenz für diese Geräteklasse ist [GEEKOM A5](https://www.geekom.de/geekom-a5-mini-pc/) mit wechselnden Ryzen-/RAM-/SSD-Varianten. Keine konkrete Variante ist hier als fertige Kaufliste freigegeben. Ein generalüberholter Business-Mini-PC kann günstiger sein; Garantie, SSD-Zustand und gemessener Verbrauch zählen mehr als der nominelle Prozessorname.

Diese Konfiguration ist für die genannten kleinen Dienste vernünftig, aber keine Vierjahresgarantie für noch unbekannte Projekte. Videospeicher, viele öffentliche Nutzer, virtuelle Maschinen und lokale große KI-Modelle verändern den Bedarf deutlich. Externe KI-API-Kosten bleiben auch auf eigener Hardware bestehen. Ein kleiner lokaler KI-Test ist möglich, ersetzt nicht automatisch die aktuell genutzte Modellqualität.

Zusatznutzen gegenüber dem kleinen VPS: schneller lokaler Dateispeicher, Backups der eigenen Geräte, Medien-/Dokumentenverwaltung, Hausautomatisierung mit lokalen Geräten, zusätzliche Testsysteme und viel RAM/Speicher ohne einzelne monatliche Aufpreise. Auch ein VPS kann mehrere Apps und Automatisierungen hosten; das allein ist kein exklusiver Heimvorteil.

Nachteile: Strom- und Internetausfall zu Hause betreffen öffentliche Apps; Upload/CGNAT müssen geklärt werden. Ein Tunnel oder verbleibender VPS kann helfen, erhöht aber Abhängigkeiten/Kosten. Datenkopie außerhalb der Wohnung bleibt nötig; RAID, zweite interne Platte und USV sind kein Offsite-Backup.

## 6. Wirtschaftlichkeitsrechnung

Rechenannahmen: 24/7, 0,35 €/kWh, konstante Preise, vorhandener Internetanschluss ohne Mehrpreis, kein Wiederverkaufswert und keine Finanzierung. Strom ist Durchschnitt an der Steckdose, nicht CPU-TDP. KI-Kosten, Domain, Arbeitszeit, Ersatzteile und zusätzliche externe Sicherung sind noch nicht eingerechnet. Wo sie auf beiden Seiten identisch sind, ändern sie den Vergleich nicht; zusätzliche Heimkosten verschlechtern dessen Ergebnis.

| Basiskosten | 2 Jahre | 3 Jahre | 4 Jahre |
| --- | ---: | ---: | ---: |
| Cloud 4 €/Monat | 96 € | 144 € | 192 € |
| Cloud 8 €/Monat | 192 € | 288 € | 384 € |
| Hetzner 4 GB + IPv4 + VM-Backup, aktueller Tarif | 202 € | 304 € | 405 € |
| Hetzner 8 GB + IPv4 + VM-Backup, aktueller Tarif | 305 € | 458 € | 611 € |
| Heim sparsam: 400 € Rechner, 10 W, ohne Zusatzhardware | 461 € | 492 € | 523 € |
| Heim geplant: 600 € Rechner + 200 € Zusatzhardware, 20 W | 923 € | 984 € | 1.045 € |

Backupumfang der Szenarien ist nicht gleichwertig: Cloudzeilen 4/8 Euro sind reine Budgetlinien; Hetzner-Backup ist ein VM-Backup; die 200 Euro Heimzusatz sind nur lokale Ausstattung. Eine unabhängige, getestete Offsite-Sicherung und deren Aufwand sind für beide Betriebsarten zusätzlich zu planen.

Bei 10 / 20 / 30 W fallen rund 2,56 / 5,11 / 7,67 Euro Strom im Monat an. Selbst ein günstiger 400-Euro-Rechner bei konstant 10 W erreicht gegenüber 8 Euro Cloud erst nach **etwa 6,1 Jahren** Kostengleichstand – ohne Backupgerät, Reparaturen oder Arbeitszeit. Das 800-Euro-Gesamtpaket bei 20 W erreicht ihn theoretisch erst nach **23,1 Jahren**; das ist außerhalb sinnvoller Hardwareplanung. Gegenüber 4 Euro Cloud sind bei 20 W bereits die laufenden Stromkosten höher.

Ab wann wäre Heimhosting finanziell interessant? Bei 800 Euro Anschaffung und 20 W müsste es über vier Jahre **mehr als 21,78 Euro tatsächlich wegfallende Cloudkosten pro Monat** ersetzen, bevor weitere Heimkosten berücksichtigt werden. Gegen 25 Euro/Monat läge der rechnerische Break-even bei etwa 40 Monaten. Künftige Projekte können diesen Punkt erreichen, aber nur wenn deren Cloudrechnungen tatsächlich entfallen – nicht wenn sie ohnehin auf demselben 8-Euro-VPS laufen könnten.

Ein bereits vorhandener geeigneter Rechner ist ein anderer Fall: bei 0 Euro Anschaffung kann Heimhosting früher günstig sein. Bleibt parallel der heutige 4-Euro-VPS notwendig, sind bei 20 W zusammen schon rund 9,11 Euro monatlich fällig, bevor Hardware amortisiert wird.

Formeln: Strom/Jahr = Watt ÷ 1.000 × 8.760 × €/kWh. Break-even-Monate = Anschaffung ÷ (ersetzte Cloudkosten/Monat − Heimstrom/Monat − sonstige Heimkosten/Monat). Ist der Nenner null oder negativ, gibt es keine laufende Ersparnis. Bereits 15 Minuten zusätzliche Wartung im Monat bei einem angenommenen Zeitwert von 20 €/h entsprechen weiteren 5 €/Monat; beide selbstverwalteten Varianten benötigen Wartung.

## Nächster sinnvoller Schritt

Die konkrete Supabase-Warnmeldung ergänzen; dann einen gesicherten Aufräumplan und einen begrenzten Migrationstest auf vorhandener Infrastruktur vorbereiten. Erst unter realer Verarbeitungslast entscheiden, ob 4 GB bleiben oder 8 GB sinnvoll sind. Hardwarekauf erst, wenn zusätzliche Heimdienste gewollt sind oder ersetzbare laufende Kosten tatsächlich deutlich höher liegen.

Offen: Wortlaut der Warnung/monatliche Usage-Metriken, tatsächlicher Bestandstarif, Strompreis und Heim-Upload, Spitzenlastmessung und Wachstumstempo. Diese Unsicherheiten ändern die Empfehlung gegen einen sofortigen Neukauf bei 4–8 €/Monat nicht.

## Nachtrag aus dem Betrieb

Die jüngste reparierte Vollsicherung vom 19.09. ist 1,32 GB groß und sowohl auf dem Server als auch auf dem Mac dateiweise geprüft. Nach Sicherung und Release verbleiben rund 18 GiB freier Serverplatz. Die bestehende Regel „14 neueste Vollkopien plus 8 beobachtete Wochen“ ist bei dieser Paketgröße nicht dauerhaft mit dem vorhandenen freien Platz vereinbar. Vor Ausweitung sind kürzere lokale Aufbewahrung mit längerer unabhängiger Mac-/externer Aufbewahrung oder deduplizierende Sicherungen zu wählen. Es wurden keine alten Sicherungen ungefragt gelöscht.

Der vollständige App-Restore wurde zusätzlich in einer frischen, vom Netzwerk getrennten PostgreSQL-Datenbank getestet. Der erste Versuch überschritt das künstliche Containerlimit von 512 MB und wurde vom Speicherschutz beendet; die Sicherungsdatei blieb unverändert. Der erneute vollständige Restore mit 1 GB wurde erfolgreich abgeschlossen: Journal134, Archiv705, 318 Originalversionen und 51 Chat-Aufrufbelege; keine neuen Modellaufrufe. Die kleine Laufzeitgröße der App allein reicht deshalb nicht als Nachweis, dass Datenbank, Sicherung und Wiederherstellung unter Spitzenlast auf dem bestehenden Server ausreichend Reserve haben.
