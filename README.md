# Public Transport Live

Live-Karte des öffentlichen Verkehrs mit Verspätungsanzeige. Fahrzeuge werden überall angezeigt, wo die Datenquelle Transitous Fahrplan- und Echtzeitdaten hat (große Teile Europas und weitere Regionen). Liniennetz und Stationen sind derzeit für das Rhein-Main-Gebiet eingebaut.

**Karte öffnen:** https://janheisig.github.io/rhein-main-live/

Auf dem Handy im Browser öffnen und über „Zum Home-Bildschirm“ als App ablegen.

## Datenquellen

- Echtzeitdaten: [Transitous](https://transitous.org) (DELFI/RMV-Fahrplan- und Echtzeitdaten)
- Karte: Esri, HERE, OpenStreetMap-Mitwirkende

Die Positionen zwischen den Haltestellen werden aus Ist-Abfahrts- und Ankunftszeiten berechnet, es sind keine GPS-Daten.

## Aufbau

- `index.html`: die komplette Karte (Liniennetz ist als `window.NET` eingebettet)
- `tools/update_network.py`: baut das Liniennetz aus dem aktuellen Fahrplan neu und vergleicht es mit `tools/topology.json`
- `tools/network.json`, `tools/topology.json`: aktueller Netzstand

Aktualisieren:

```
cd tools
python3 update_network.py --baseline network.json --baseline-topo topology.json --html ../index.html --out new_network.json
```

Exit-Code 0 = unverändert, 10 = geändert (HTML aktualisiert), 2 = Datenquelle gestört. Bei Änderungen `new_network.json` → `network.json` und `new_network.topology.json` → `topology.json` übernehmen.
