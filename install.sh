#!/bin/bash
# -*- coding: utf-8 -*-
#    ____  ____  ______       __      __       __       _____
#   / __ )/ __ \/ ___/ |     / /___ _/ /______/ /_     |__  /
#  / __  / / / /\__ \| | /| / / __  / __/ ___/ __ \     /_ <
# / /_/ / /_/ /___/ /| |/ |/ / /_/ / /_/ /__/ / / /   ___/ /
#/_____/\____//____/ |__/|__/\__,_/\__/\___/_/ /_/   /____/
#                German BOS Information Script
#                     by Bastian Schroll
#@file:        install.sh
#@date:        28.04.2026
#@author:      Claus Schichl
#@description: Installation File for BOSWatch3


# Standardwerte
INSTALL_PATH="/opt/boswatch3"
export REPO_URL="https://github.com/KoenigMjr/BW3-Core"
export BRANCH="develop"
#ORIGINAL
#export REPO_URL="https://github.com/BOSWatch/BW3-Core"
#export BRANCH="master"
export BW3_LANG="${1:-de}"

# Temporäres Log, damit git clone nicht blockiert wird
TMP_LOG="/tmp/bw3_install.log"
FINAL_LOG_DIR="$INSTALL_PATH/log/install"
FINAL_LOG_FILE="$FINAL_LOG_DIR/setup_log.txt"

# Alles in das temporäre Log umleiten
exec > >(tee -a "$TMP_LOG") 2>&1

tput clear
cat <<'EOF'
    ____  ____  ______       __      __       __       _____
   / __ )/ __ \/ ___/ |     / /___ _/ /______/ /_     |__  /
  / __  / / / /\__ \| | /| / / __  / __/ ___/ __ \     /_ <
 / /_/ / /_/ /___/ /| |/ |/ / /_/ / /_/ /__/ / / /   ___/ /
/_____/\____//____/ |__/|__/\__,_/\__/\___/_/ /_/   /____/
                German BOS Information Script
EOF

echo "install-script install.sh | Start: $(date)"
echo "----------------------------------------------------"

# Root-Check
if [[ $EUID -ne 0 ]]; then
   echo "[ERROR] Please run as root (sudo bash install.sh)!"
   exit 1
fi

echo "Preparing BOSWatch3 environment..."

# 1. System-Basics installieren
# Wir brauchen git für das Repo und venv für die Isolation
echo "Updating system and installing basics (git, python3-venv)..."
while fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1 ; do
    echo "Waiting for other software managers to finish..."
    sleep 5
done

apt-get update -y
apt-get install -y python3 python3-venv git

# 2. Zielverzeichnis vorbereiten
mkdir -p "$INSTALL_PATH"

# 3. Repo holen oder aktualisieren
if [ ! -d "$INSTALL_PATH/.git" ]; then
    echo "Initial download of $REPO_URL (Branch: $BRANCH)..."
    git clone -b "$BRANCH" "$REPO_URL" "$INSTALL_PATH"
else
    echo "directory already exists, updating installer..."
    cd "$INSTALL_PATH"
    git fetch origin
    git checkout "$BRANCH"
    git pull
fi

# JETZT ist der Ordner da, jetzt können wir das Log-System finalisieren
cd "$INSTALL_PATH"
mkdir -p "$FINAL_LOG_DIR"
# Kopiere das bisherige Temp-Log in das finale Logfile
cat "$TMP_LOG" > "$FINAL_LOG_FILE"

cd "$INSTALL_PATH"
chmod +x install/manager.py

# 4. Virtuelle Umgebung (VENV) erstellen falls nicht vorhanden
if [ ! -d "venv" ]; then
    echo "Creating virtual python-environment..."
    python3 -m venv venv
fi

# 5. Manager-Abhängigkeiten installieren
# Diese Pakete braucht der Manager, um das Menü und den Fortschritt anzuzeigen (tqdm)
echo "installing venv-modules..."
./venv/bin/pip install --upgrade pip > /dev/null
# Nur Core- und Manager-Abhängigkeiten installieren
# Plugin-spezifische Pakete werden später via Option 6 (sync_dependencies) nachgezogen
echo "Installing core and manager dependencies..."
./venv/bin/pip install $(grep -E '#.*\[(core|manager)\]' requirements-runtime.txt \
    | sed 's/#.*//' \
    | tr -d ' ' \
    | tr '\n' ' ') > /dev/null

echo ""
echo "----------------------------------------------------"
echo "INFO: Only core dependencies were installed."
echo "      Plugin-specific packages (e.g. Telegram, MySQL)"
echo "      can be installed after configuration via option 6."
echo "----------------------------------------------------"
echo ""

# 7. Start manager.py
echo "Starting BOSWatch3 Manager..."
exec > /dev/tty 2>&1
./venv/bin/python3 install/manager.py

# Ende des Skripts
echo "install.sh finished at $(date)"
