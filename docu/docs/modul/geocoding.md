# <center>Geocoding</center> 
---

## Beschreibung
Mit diesem Modul können einem Paket die Koordinaten eines Ortes oder einer Adresse angefügt werden.

## Unterstützte Alarmtypen
- Pocsag

## Resource
`geocoding`

## Konfiguration
|Feld|Beschreibung|Default|
|----|------------|-------|
apiProvider|Der Provider für das Geocoding|
apiToken|Der Api-Token fuer die Geocoding-Api|
regex|Regex mit Capture-Group zum Herausfiltern der Adresse aus der Nachricht (erste Gruppe)|

#### Verfügbare Geocoding Provider
|Name|Einstellungswert|
|----|------------|
|Mapbox|mapbox|
|Google Maps|google|

**Beispiel:**
```yaml
  - type: module
    name: Geocoding Module
    res: geocoding
    config:
      apiProvider: "{{ Provider für Geocoding }}"
      apiToken: "{{ API-Key für Provider }}"
      regex: "Adresse: ([^;]+)"  # Beispiel: Adresse steht nach "Adresse:" bis zum nächsten ";"
```

---
## Modul Abhängigkeiten
- keine

---
## Externe Abhängigkeiten
- geocoder

---
## Paket Modifikationen
- `address`: gefundene Adresse
- `lat`: Latitude der Adresse
- `lon`: Longitude der Adresse

---
## Zusätzliche Wildcards
- `{ADDRESS}`: gefundene Adresse
- `{LAT}`: Latitude der Adresse
- `{LON}`: Longitude der Adresse