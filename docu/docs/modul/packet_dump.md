# <center>Packet Dump</center> 
---

## Beschreibung
Ein Diagnose- und Debug-Modul, das den vollständigen Inhalt und alle internen Variablen des aktuellen `bwPacket`-Objekts formatiert im Log ausgibt. Es verändere das Paket nicht und dient rein zur Analyse der Pipeline.

## Unterstützte Alarmtypen
- Alle (FMS, POCSAG, ZVEI, MSG)

## Resource
`packetDump`

## Konfiguration

|Feld|Beschreibung|Default|
|---|---|---|
|title|Überschrift im Log-Fenster, um verschiedene Dump-Punkte in der Route zu unterscheiden.|Packet Dump|

## Modul Abhängigkeiten
- keine

## Externe Abhängigkeiten
- keine

## Paket Modifikationen
- keine (Das Modul verhält sich vollkommen transparent).

### Rückgabewert:
- **None**: Der Router fährt mit dem unveränderten bwPacket fort (Input = Output).

## Richtiges Logging (Beispiel für Entwickler)
Das Modul nutzt den Standard-Python-Logger. Im Logfile von BOSWatch erzeugt ein Aufruf folgende strukturierte Ausgabe:

```yaml
13.04.2026 21:16:09,100 - packetDump     [INFO    ] ======= [DEBUG DUMP: Zustand NACH Multicast] =======
13.04.2026 21:16:09,102 - packetDump     [INFO    ] 
{'_data': {'bitrate': '1200',
           'clientName': 'ILS Musterstadt',
           'frequency': '172.640M',
           'message': 'B3 WOHNHAUS',
           'multicastMode': 'complete',
           'multicastRole': 'recipient',
           'multicastSourceRic': '0456789',
           'multicastRecipientCount': '2',
           'multicastRecipientIndex': '1',
           'ric': '0234567',
           'ric_list': '0234567, 0345678',
           'subric': '4',
           'timestamp': 1776107768.259321}}
13.04.2026 21:16:09,103 - packetDump     [INFO    ] ==================================================
```