# <center>Mysql</center> 
---

## Beschreibung
Mit diesem Plugin ist es moeglich, die Alarmierungen in einer Mysql / Mariadb Datenbank zu speichern.
Das Plugin legt die Tabelle "boswatch" selbststaendig an, wenn diese nicht vorhanden ist.
Auf Wunsch werden auch zusätzliche Felder im Paket gespeichert, z.B. die Beschreibung aus dem [Descriptor](../modul/descriptor.md) oder die Adresse aus dem [Geocoding](../modul/geocoding.md) (siehe [Zusätzliche Felder](#zusatzliche-felder)).

## Unterstütze Alarmtypen
- Fms
- Pocsag
- Zvei
- Msg

## Resource
`mysql`

## Konfiguration
|Feld|Beschreibung|Default|
|----|------------|-------|
|host|IP-Adresse bzw. URL des Hosts||
|user|Username||
|password|Passwort||
|database|Name der Datenbank||
|additionalFields|Optional: zusätzliche Felder, die gespeichert werden sollen (kommagetrennt)||
|allFields|Optional: `true` speichert alle zusätzlichen Felder, `additionalFields` wird dann ignoriert|false|

**Beispiel:**
```yaml
  - type: plugin
    name: mysql
    res: mysql
    config:
      host: HOST
      user: USERNAME
      password: PASSWORD
      database: DATABASE
      additionalFields: description, address  # optional
```

### Zusätzliche Felder
Für die Standardfelder eines Pakets (z.B. RIC, Nachricht, FMS-Status, Ton) hat die Tabelle feste Spalten. Alle anderen Felder im Paket gelten als zusätzliche Felder. Sie entstehen durch vorgeschaltete Module, z.B. das `descrField` des Descriptors oder `address`, `lat` und `lon` des Geocodings.

- Ohne `additionalFields` werden nur die Standardfelder gespeichert. Die Tabelle bekommt keine neuen Spalten.
- Mit `additionalFields` werden nur die aufgeführten Felder gespeichert, z.B. `additionalFields: description, lat, lon`. Felder mit fester Spalte werden dabei ignoriert.
- Mit `allFields: true` werden alle zusätzlichen Felder eines Pakets gespeichert. Ist zusätzlich `additionalFields` angegeben, wird es ignoriert und eine Warnung ins Log geschrieben.

- Gibt es für ein Feld noch keine Spalte, legt das Plugin sie automatisch an (Typ `TEXT`, Spaltenname = Feldname). Alle bereits vorhandenen Datensätze haben in der neuen Spalte den Wert `NULL`.
- Bei aufgeführten Feldern werden fehlende Spalten bereits beim Start des Plugins angelegt. Bei `allFields` sind die Felder vorher nicht bekannt, die Spalte wird dann beim ersten Alarm angelegt, in dem das Feld vorkommt.
- Eine bereits vorhandene Spalte wird verwendet. Groß- und Kleinschreibung spielt dabei keine Rolle.
- Warnungen der Datenbank (z.B. abgeschnittene Werte) werden im Log von BOSWatch ausgegeben.

**Rechte:** Zum Anlegen neuer Spalten benötigt der Datenbank-Benutzer das Recht `ALTER` auf die Tabelle, z.B.:
```sql
GRANT ALTER ON DATABASE.boswatch TO 'USERNAME'@'%';
```
Fehlt das Recht, wird das Feld nicht gespeichert und einmalig eine Warnung ins Log geschrieben (bei aufgeführten Feldern bereits beim Start). Der Alarm selbst wird trotzdem gespeichert. Alternativ kann die Spalte auch von Hand angelegt werden:
```sql
ALTER TABLE boswatch ADD COLUMN description TEXT NULL DEFAULT NULL;
```

**Sicherheit und Pflege:**

- Die Feldnamen werden direkt als Spaltennamen verwendet. Erlaubt sind nur Buchstaben, Ziffern und `_` (max. 64 Zeichen). Felder mit anderen Zeichen und Felder mit dem Namen einer festen Spalte (z.B. `id`) werden nicht gespeichert.
- Mit `allFields` entsteht für jedes neue Feld eine neue Spalte. Da die Pakete von den Clients kommen, empfiehlt es sich, die benötigten Felder einzeln aufzuführen, vor allem wenn Clients nicht vollständig vertrauenswürdig sind oder sich die verwendeten Module häufig ändern.
- Die Tabellenstruktur sollte vom Administrator gelegentlich geprüft werden.

---
## Modul Abhängigkeiten
- keine

---
## Externe Abhängigkeiten
- mysql-connector-python
