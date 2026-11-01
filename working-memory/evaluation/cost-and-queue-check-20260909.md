# Live-Prüfung Kosten und Warteschlange – 09.09.2026

Quelle: Supabase `wm_model_calls`, `wm_jobs`, `wm_archive_documents`, `wm_processing_config` im aktiven Workspace; produktive Funktionsdefinitionen `wm_claim_job` und `wm_reserve_call` direkt gelesen. Beträge sind die aus Provider-Usage berechneten Protokollkosten, keine unabhängig geprüfte Rechnung.

| Abgeschlossenes Meeting am 09.09. | USD | Terra-Aufrufe | Embedding-Aufrufe |
|---|---:|---:|---:|
| Safaei, Kimia (117 Zeichen) | 0.021443 | 2 | 1 |
| Massari, Marika | 0.191847 | 3 | 11 |
| Dreznjak, Miro | 0.199462 | 3 | 13 |
| Renz, Patrick | 0.290191 | 4 | 16 |
| Abstimmung Konso-Files Christopher | 0.453098 | 4 | 21 |

Gesamte verbuchte Produktion: 8.521306 USD, keine offenen Aufrufe mit unbekannten Kosten. Gespeicherte kumulative Grenze: 8.878649 USD. Differenz: 0.357343 USD. Die Grenze ist noch nicht vollständig ausgegeben; die Reservierung des nächsten Aufrufs würde sie überschreiten.

Monatsreporting: review/budget_exceeded, bisher 0.176796 USD; zwei Terra-Aufrufe plus 20 Embedding-Aufrufe gespeichert. Jan und zwei Caroline-Originale: queued, noch keine Aufrufe.

Die produktive Reservierungsfunktion verweigert neue Aufrufe bei Gesamtnutzung plus angeforderter Reservierung oberhalb des Limits. Reservierung in call_budget.py umfasst Eingabe, Sicherheitsspielraum und die maximale erlaubte Ausgabe, nicht nur die wahrscheinlich benötigte Ausgabe. Der Worker wählt den ältesten nicht abgeschlossenen Job. Ein review-Job lässt spätere Quellen nicht passieren; so bleibt der chronologische Bestandsabgleich erhalten.

Die neue Verarbeitung umfasst Extraktion und Zusammenfassung, Suche im Bestand, Abgleich mit bestehenden Aufgaben/Wissen und eine separate Prüfung. Hauptkosten sind Terra-Aufrufe, nicht Embeddings. Beispiel Konso: 0.452719 USD Terra versus 0.000379 USD Embeddings.

Die zuvor vorgeschlagenen zusätzlichen 5 USD waren ein pauschaler Budgetpuffer, keine berechneten Restkosten und kein Meetingpreis. Keine Budgetänderung oder kostenpflichtige Wiederholung in dieser Prüfung.
