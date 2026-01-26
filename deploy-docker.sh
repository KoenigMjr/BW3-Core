#!/bin/bash
# -*- coding: utf-8 -*-
"""
    ____  ____  ______       __      __       __       _____
   / __ )/ __ \/ ___/ |     / /___ _/ /______/ /_     |__  /
  / __  / / / /\__ \| | /| / / __  / __/ ___/ __ \     /_ <
 / /_/ / /_/ /___/ /| |/ |/ / /_/ / /_/ /__/ / / /   ___/ /
/_____/\____//____/ |__/|__/\__,_/\__/\___/_/ /_/   /____/
                German BOS Information Script
                     by Bastian Schroll

@file:        deploy-docker.sh
@date:        26.01.2026
@author:      Claus Schichl
@description: Docker Deployer - Prepares the host, sets blacklists, and starts Docker containers
"""

set -e # Beenden bei Fehlern

echo "🔍 Starte BOSWatch3 System-Check..."

# 1. Host-Vorbereitung (Blacklist & Driver Unload)
BLACKLIST_FILE="/etc/modprobe.d/boswatch_blacklist_sdr.conf"

if [ ! -f "$BLACKLIST_FILE" ]; then
    echo "🔧 Schritt 1: Setze SDR-Blacklist auf dem Host..."
    echo -e "blacklist dvb_usb_rtl28xxu\nblacklist rtl2830\nblacklist dvb_usb_v2\nblacklist dvb_core" | sudo tee "$BLACKLIST_FILE" > /dev/null
    
    echo "⚡ Schritt 2: Entlade aktiven DVB-T Treiber (rmmod)..."
    # Wir versuchen den Treiber sofort zu entladen, damit kein Reboot nötig ist
    sudo rmmod dvb_usb_rtl28xxu 2>/dev/null || echo "ℹ️  Treiber war nicht geladen oder bereits blockiert."
    
    echo "✅ Host-Konfiguration abgeschlossen."
else
    echo "✅ SDR-Blacklist bereits konfiguriert."
fi

# 2. Docker-Compose Datei für den User erstellen (falls nicht vorhanden)
if [ ! -f "docker-compose.yml" ]; then
    echo "📄 Schritt 3: Erstelle Standard docker-compose.yml..."
    cat > docker-compose.yml <<EOF
version: '3.8'
services:
  server:
    image: ghcr.io/koenigmjr/bw3-core-server:latest
    container_name: bw3_server
    restart: always
    environment:
      - TZ=Europe/Berlin
    ports:
      - "8080:8080"
    volumes:
      - ./config:/opt/boswatch/config
      - ./log:/opt/boswatch/log

  client:
    image: ghcr.io/koenigmjr/bw3-core-client:latest
    container_name: bw3_client
    restart: always
    privileged: true
    environment:
      - TZ=Europe/Berlin
    devices:
      - "/dev/bus/usb:/dev/bus/usb"
    volumes:
      - ./config:/opt/boswatch/config
      - ./log:/opt/boswatch/log
    command: ["-c", "config/client.yaml"]
    depends_on:
      - server
EOF
fi

# 3. Infrastruktur vorbereiten
mkdir -p config log
if [ ! -f "config/client.yaml" ]; then
    echo "⚠️  HINWEIS: Bitte kopiere deine 'client.yaml' und 'server.yaml' in den Ordner '$(pwd)/config'!"
fi

# 4. Starten
echo "🚀 Schritt 4: Starte BOSWatch3 Container-Landschaft..."
sudo docker compose up -d

echo "-------------------------------------------------------"
echo "✅ Fertig! BOSWatch3 läuft jetzt im Hintergrund."
echo "   Status prüfen:  sudo docker compose ps"
echo "   Logs einsehen:  sudo docker compose logs -f"
echo "-------------------------------------------------------"