# Terra-Implementierung, 7. September 2026

GPT-5.6 Terra wurde als Standard in der produktiven App bereitgestellt. Modellzugang mit dem vorhandenen OpenAI-Schlüssel bestätigt, anschließend durch einen rein synthetischen Responses-Aufruf geprüft (0,000238 USD). Der Dienst ist gesund; Journalrevision 110 und Archivrevision 492 unverändert.

## Änderung und bestehende Verträge

| Stelle | Bisher | Jetzt |
|---|---|---|
| Produktiver Serverstandard | Opus 5 / Anthropic Messages | Terra / OpenAI Responses |
| Extraktion und Zusammenfassung | Gemeinsamer strukturierter Aufruf | Derselbe fachliche Prompt und dasselbe Schema, Terra |
| Handlungsprüfung und Lebenszyklusprüfung | Anthropic-Aufrufe | Terra über dieselbe dauerhafte Reservierung; kein Opus-Zusatzprüfer |
| Effektives Reasoning | Thinking deaktiviert | reasoning.effort none ausdrücklich gesetzt |
| Ausgabevertrag | content/text und end_turn | Responses-Endereignis in bestehenden internen Vertrag übersetzt |
| Kosten | Anthropic Usage | OpenAI-Input inkl. Cache-Aufteilung; Schreibpreis und Langkontextaufschlag |
| Wiederaufnahme | Dauerhaft reservierte, gespeicherte Antworten | Unverändert; kein automatischer Neuversand bei unklarem Ergebnis |

Store false, Truncation disabled und strict JSON Schema sind ausdrücklich gesetzt. Keine Tools, keine providerseitige Modellweiterleitung, kein Pro-Modus. Ausgabelimits 24.000 / 6.000 / 12.000 bleiben erhalten. Ein unvollständiger Stream, Refusal, Providerfehler oder falsches Antwortmodell erzeugt kein erfolgreiches Ergebnis. Fehlende oder ungültige Usage lässt die volle Kostenreserve bestehen. Reasoning-Tokens sind bereits in output_tokens enthalten und werden nicht doppelt bepreist.

Input bis 272.000 Tokens: 2 USD je Million normale Eingabe, 0,20 Cache-Lesen, 2,50 Cache-Schreiben; Ausgabe 12 USD. Darüber gilt für die gesamte Anfrage 4 / 0,40 / 5 / 18 USD. Die Reservierung nimmt konservativ einen Token je UTF-8-Byte plus Rahmen und volle Ausgabe an, einschließlich möglicher Cache-Schreib- und Langkontextkosten. Die tatsächliche Abrechnung verwendet die gemeldeten Tokens. Keine Preisersparnis für beliebige Meetings behauptet.

Historische Modellantworten, Evaluationen, Altbestandsmigration und Fachregeln wurden nicht umgeschrieben. Der Anthropic-Adapter bleibt für ausdrücklich benannte historische/isolierte Aufrufe vorhanden; die produktive Modellkonfiguration lautet Terra. Alte Automatisierungen bleiben stillgelegt.

## Prüfung

225 Backendtests bestanden (10,915 s), darunter Terra-Responses-Transport, alle verwendeten strikten Schemas, Refusal/Abbruch/HTTP-Fehler, Cache-Aufteilung, Preisgrenze, persistentes Budget, Wiederaufnahme ohne Doppelaufruf und synthetische vollständige Quelle durch den kanonischen Worker. Alte Tests ersetzen jetzt die Providerschnittstelle statt einer fest verdrahteten Anthropic-Funktion. Ein echter GET auf den Terra-Modellendpunkt bestätigt den Zugang. Ein echter synthetischer Responses-Aufruf lieferte schema-konform {"ok":true}, 41 Input-/13 Output-Tokens, bestätigte Usage und 0,000238 USD berechnete Kosten. Kein Altbestandsimport oder historisches Transkript über die API. Dieser isolierte Verbindungstest steht nicht im Meeting-Kostenjournal. Damit ist die technische Migration getestet; ein neuer realer Qualitätsvergleich wurde nicht durchgeführt.

Paket-SHA256: d59c4821dd68c0f6856b18dc16c585240e410be634006e0470967b4b0527a36d. 61 Runtime-Dateien, verifizierter Vorgänger und Rückfallimage vorhanden. Lokale geänderte Quelldateien bytegleich mit dem Release. Details: [Prüfquittung](../evaluation/terra-deployment-2026-09-07.json).

## Zugang und Betrieb

Der vorhandene Supabase-OpenAI-Schlüssel wurde über einen kurzlebigen, authentifizierten Endpunkt RSA-OAEP-verschlüsselt ausschließlich für den bestehenden App-Server bereitgestellt. Kein Klartextschlüssel in Ausgaben oder Browser. Endpunkt danach durch netzwerkfreie HTTP-410-Antwort ersetzt, privater Transport-Schlüssel entfernt. Laufzeitschlüssel nur in der privaten Serverkonfiguration.

Der Nutzer hat ausdrücklich „keine grenze. ich tracke das selbst“ entschieden. Terra-Automatik und Eingang sind aktiviert. budget_micro_usd=NULL bedeutet ausdrücklich unbeschränkt; Standardwert 0 bleibt für neue Konfigurationen gesperrt. Reservierungen und gemeldete Kosten werden unverändert gespeichert. Frühester erlaubter Meetingtag ist 08.09.2026, zusätzlich schon im n8n-Eingang vor dem Transkriptlesen gefiltert. Ein isolierter SQL-Test mit ROLLBACK bestätigt 33 USD korrekt angerechnete Kosten/Reserven ohne Obergrenze, Wiederverwendung ohne Doppelaufruf, Altquellen-Ausschluss und unveränderte Konfigurationsrechte. Technische Fehler-/Qualitätsprüfungen bleiben aktiv. Keine automatische Verarbeitung des Altbestands oder der Inbox vom 07.09.2026.

Die produktive Oberfläche zeigt Modell und „Keine Kostenobergrenze“. TypeScript, ESLint und Vite-Build bestanden; alle sieben ausgelieferten Dateien bytegleich geprüft, anonyme Datenroute weiterhin HTTP 401. Vercel: dpl_9vgcENU6pfjeeGrFFdoRgRvhVbr4. n8n-Workflow nzyaKxs5Om9wuPEc ist veröffentlicht und prüft alle zehn Minuten; übrige Dashboard-Testworkflows bleiben aus.

## Quellen

- [Terra-Modell](https://developers.openai.com/api/docs/models/gpt-5.6-terra)
- [OpenAI-Preise](https://developers.openai.com/api/docs/pricing)
- [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
- [Migrationshinweise](https://developers.openai.com/api/docs/guides/upgrading-to-gpt-5p6-sol)


## Sicherung des aktivierten Stands

Vollständige Sicherung dashboard-20260907T133251Z.tar.gz einschließlich neuer Schema-Migration, aktivierter Konfiguration und n8n-Version. Wiederherstellung isoliert geprüft, unveränderte Revisionen 110/492, 194 Originale, 298 Notizen, keine kanonischen Modellaufrufe. SHA256: 1947ba85ecfc6e3c7b74ba8b95c91bdd030d820ab69c7dbcbd60d1d01b371720. Zweite Kopie auf dem Mac am 07.09.2026 15:35 bestätigt, 90 Archivdateien geprüft. Die im Sicherungsbericht genannten inaktiven Workflows betreffen ausschließlich die isolierte Wiederherstellung. Der produktive Dashboard-Eingang ist aktiv.

Der erste Eingangstest (n8n 20220) bestätigte Trigger, authentifizierten Archivabgleich, Google-Drive-Inventur und Stichtagsauswahl. Null ausgewählte Transkripte, somit keine erneute Inhaltsauswertung. Abschluss am 07.09.2026 15:32:43; manuelle Ausführungsdaten werden gemäß Einstellung direkt als gelöscht markiert.
