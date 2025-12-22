#!/bin/bash
# -*- coding: utf-8 -*-
#     ____  ____  ______       __      __       __       _____
#    / __ )/ __ \/ ___/ |     / /___ _/ /______/ /_     |__  /
#   / __  / / / /\__ \| | /| / / __  / __/ ___/ __ \     /_ < 
#  / /_/ / /_/ /___/ /| |/ |/ / /_/ / /_/ /__/ / / /   ___/ / 
# /_____/\____//____/ |__/|__/\__,_/\__/\___/_/ /_/   /____/  
#                 German BOS Information Script
#                      by Bastian Schroll
# @file:         install.sh
# @date:         26.12.2025
# @author:       Bastian Schroll, Smeti
# @description:  Installation File for BOSWatch3 (incl. Update-Mode & Venv)

set -euo pipefail
IFS=$'\n\t'

trap 'echo "Unexpected error in line $LINENO"; tput cnorm 2>/dev/null || true; exit 1' ERR

# ===  CONFIGURATION CONSTANTS ===

readonly TARGET_RTL_COMMIT="ae0dd6d4f09088d13500a854091b45ad281ca4f0"
readonly TARGET_MULTIMON_VER="1.4.1"
readonly CONFIG_FILES=("logger_client.ini" "logger_server.ini" "client. yaml" "server.yaml")

# Directories & paths
BOSWATCH_PATH="/opt/boswatch3" # can be overridden via -p
BOSWATCH_INSTALL_PATH="/opt/boswatch3_install"
VENV_PATH="${BOSWATCH_PATH}/venv"
VERSION_FILE="${BOSWATCH_PATH}/.version_info"
SETUP_LOG="${BOSWATCH_INSTALL_PATH}/setup_log.txt"

# Script variables
ACTUAL_USER="${SUDO_USER:-$USER}"
ACTUAL_GROUP=$(id -gn "$ACTUAL_USER")
UPDATE_MODE=false
REBOOT=false
BRANCH="master"
RECOMPILE_NEEDED=true

# ===  HELPER FUNCTIONS ===

log_message() {
  local message="$1"
  echo "$message" >> "$SETUP_LOG"
  echo "$message"
}

exit_on_error() {
  local exitcode=$?
  local action="${1:-unknown}"
  local module="${2:-unknown}"
  
  if [ $exitcode -ne 0 ]; then
    log_message "❌ Action:  ${action} on ${module} failed (exit code: ${exitcode})"
    log_message "   Logfile: ${SETUP_LOG}"
    tput cnorm 2>/dev/null || true
    exit "$exitcode"
  else
    log_message "✓ Action: ${action} on ${module} ok"
  fi
}

progress_bar() {
  local step="$1"
  local total=11
  local filled=$((step * 10 / total))
  tput cup 13 15
  printf "[%2d/%2d] [%-10s]\n" "$step" "$total" "$(printf '%*s' "$filled" | tr ' ' '#')---------" | head -c 20
  tput cup 15 5
}

# ===  ROOT CHECK ===

if [[ $EUID -ne 0 ]]; then
  echo "❌ This script must be run as root!" >&2
  exit 1
fi

# ===  DISPLAY BANNER ===

tput clear 2>/dev/null || true
tput civis 2>/dev/null || true

cat << 'BANNER'
    ____  ____  ______       __      __       __       _____
   / __ )/ __ \/ ___/ |     / /___ _/ /______/ /_     |__  /
  / __  / / / /\__ \| | /| / / __  / __/ ___/ __ \     /_ <
 / /_/ / /_/ /___/ /| |/ |/ / /_/ / /_/ /__/ / / /   ___/ /
/_____/\____//____/ |__/|__/\__,_/\__/\___/_/ /_/   /____/
                German BOS Information Script
                     by Bastian Schroll
BANNER

cat << 'WARNING'

This may take several minutes...  Don't panic! 
⚠️  Note: This script does not install a webserver with PHP and MySQL.
   If you need MySQL support, you must configure it manually.

WARNING

# ===  PARSE ARGUMENTS ===

while [[ $# -gt 0 ]]; do
  case $1 in
    -r|--reboot) REBOOT=true; shift ;;
    -b|--branch)
      case $2 in
        dev|develop)
          echo "⚠️  WARNING: Using DEVELOP branch !"
          BRANCH="develop"
          ;;
        *) BRANCH="master" ;;
      esac
      shift 2 ;;
    -p|--path) BOSWATCH_PATH="$2"; VENV_PATH="${BOSWATCH_PATH}/venv"; VERSION_FILE="${BOSWATCH_PATH}/.version_info"; shift 2 ;;
    *) echo "❌ Unknown option: $1"; exit 1 ;;
  esac
done

# Update derived paths if custom BOSWATCH_PATH was set
VENV_PATH="${BOSWATCH_PATH}/venv"
VERSION_FILE="${BOSWATCH_PATH}/.version_info"

# ===  LOAD EXISTING VERSION INFO ===

mkdir -p "$BOSWATCH_INSTALL_PATH" || exit_on_error "mkdir" "install-path"

{
  echo "=== BOSWatch3 Installation Log ==="
  echo "Start:  $(date '+%Y-%m-%d %H:%M:%S')"
  echo "User: ${ACTUAL_USER}: ${ACTUAL_GROUP}"
  echo "Path: ${BOSWATCH_PATH}"
  echo "Branch: ${BRANCH}"
  echo "==============================="
} >> "$SETUP_LOG"

if [ -f "$VERSION_FILE" ]; then
  source "$VERSION_FILE" 2>/dev/null || true
fi

# ===  CHECK FOR UPDATE MODE ===

if [ -d "${BOSWATCH_PATH}/.git" ]; then
  UPDATE_MODE=true
  log_message "➜ EXISTING INSTALLATION DETECTED:  UPDATE MODE"
fi

# ===  CREATE DIRECTORIES ===

mkdir -p "$BOSWATCH_PATH" "$BOSWATCH_INSTALL_PATH" || exit_on_error "mkdir" "boswatch-paths"

# ===  INSTALLATION STEPS ===

# STEP 1: apt-get update
progress_bar 1
log_message "-> apt-get update..."
apt-get update >> "$SETUP_LOG" 2>&1 || exit_on_error "apt-get-update" "system"

# STEP 2: Install build tools & dependencies
progress_bar 2
log_message "-> Install build tools and SDR dependencies..."
apt-get -y install git cmake build-essential libusb-1.0-0-dev qt6-base-dev qt6-base-dev-tools libpulse-dev libx11-dev sox >> "$SETUP_LOG" 2>&1 || exit_on_error "apt-install" "system"

# STEP 3: Install Python & venv
progress_bar 3
log_message "-> Install Python, venv, and utilities..."
apt-get -y --no-install-recommends install python3 python3-pip python3-venv alsa-utils usbutils >> "$SETUP_LOG" 2>&1 || exit_on_error "apt-install" "python"

# STEP 4: Create Python venv
progress_bar 4
log_message "-> Create Python virtual environment..."
python3 -m venv "$VENV_PATH" >> "$SETUP_LOG" 2>&1 || exit_on_error "venv-create" "python3"

# ===  DEPENDENCY COMPILATION CHECK ===

if [ "$UPDATE_MODE" = true ] && [ -f "$VERSION_FILE" ]; then
  INSTALLED_RTL="${INSTALLED_RTL:-}"
  INSTALLED_MULTIMON="${INSTALLED_MULTIMON:-}"
  
  if [ "$INSTALLED_RTL" == "$TARGET_RTL_COMMIT" ] && [ "$INSTALLED_MULTIMON" == "$TARGET_MULTIMON_VER" ]; then
    RECOMPILE_NEEDED=false
  fi
fi

# ===  STEPS 5-8: COMPILE DEPENDENCIES (if needed) ===

if [ "$RECOMPILE_NEEDED" = true ]; then
  
  # Step 5: Download rtl-sdr
  progress_bar 5
  log_message "-> Download rtl-sdr..."
  cd "$BOSWATCH_INSTALL_PATH" || exit_on_error "cd" "install-path"
  
  rm -rf rtl-sdr 2>/dev/null || true
  git clone --branch master https://github.com/osmocom/rtl-sdr.git rtl-sdr >> "$SETUP_LOG" 2>&1 || exit_on_error "git-clone" "rtl-sdr"
  
  cd "$BOSWATCH_INSTALL_PATH/rtl-sdr" || exit_on_error "cd" "rtl-sdr"
  git checkout "$TARGET_RTL_COMMIT" >> "$SETUP_LOG" 2>&1 || exit_on_error "git-checkout" "rtl-sdr"
  
  # Step 6: Compile rtl-sdr
  progress_bar 6
  log_message "-> Compile rtl-sdr..."
  mkdir -p build && cd build || exit_on_error "mkdir" "rtl-sdr-build"
  
  cmake .. -DINSTALL_UDEV_RULES=ON >> "$SETUP_LOG" 2>&1 || exit_on_error "cmake" "rtl-sdr"
  make >> "$SETUP_LOG" 2>&1 || exit_on_error "make" "rtl-sdr"
  make install >> "$SETUP_LOG" 2>&1 || exit_on_error "make-install" "rtl-sdr"
  ldconfig >> "$SETUP_LOG" 2>&1 || exit_on_error "ldconfig" "rtl-sdr"
  
  # Step 7: Download multimon-ng
  progress_bar 7
  log_message "-> Download multimon-ng..."
  cd "$BOSWATCH_INSTALL_PATH" || exit_on_error "cd" "install-path"
  
  rm -rf multimonNG 2>/dev/null || true
  git clone --branch "$TARGET_MULTIMON_VER" https://github.com/EliasOenal/multimon-ng.git multimonNG >> "$SETUP_LOG" 2>&1 || exit_on_error "git-clone" "multimon-ng"
  
  # Step 8: Compile multimon-ng
  progress_bar 8
  log_message "-> Compile multimon-ng..."
  cd "$BOSWATCH_INSTALL_PATH/multimonNG" || exit_on_error "cd" "multimon-ng"
  
  mkdir -p build && cd build || exit_on_error "mkdir" "multimon-build"
  qmake6 ../multimon-ng.pro >> "$SETUP_LOG" 2>&1 || exit_on_error "qmake6" "multimon-ng"
  make >> "$SETUP_LOG" 2>&1 || exit_on_error "make" "multimon-ng"
  make install >> "$SETUP_LOG" 2>&1 || exit_on_error "make-install" "multimon-ng"
  
  log_message "✓ Dependencies compiled successfully"
else
  progress_bar 5
  log_message "-> Skipping compilation (versions already up to date)..."
  sleep 1
  progress_bar 8
fi

# STEP 9: Download/Update BOSWatch3 core
progress_bar 9
if [ "$UPDATE_MODE" = true ]; then
  log_message "-> Updating BOSWatch3 core ($BRANCH)..."
  cd "$BOSWATCH_PATH" || exit_on_error "cd" "boswatch-core"
  
  git stash push -u >/dev/null 2>&1 || log_message "⚠️  No changes to stash (or stash failed)"
  git checkout "$BRANCH" >> "$SETUP_LOG" 2>&1 || exit_on_error "git-checkout" "boswatch-core"
  git pull >> "$SETUP_LOG" 2>&1 || exit_on_error "git-pull" "boswatch-core"
else
  log_message "-> Download BOSWatch3 ($BRANCH)..."
  git clone -b "$BRANCH" https://github.com/BOSWatch/BW3-Core "$BOSWATCH_PATH" >> "$SETUP_LOG" 2>&1 || exit_on_error "git-clone" "boswatch-core"
fi

# Install Python dependencies
log_message "-> Install Python requirements..."
"$VENV_PATH/bin/pip" install --upgrade pip >> "$SETUP_LOG" 2>&1 || exit_on_error "pip-upgrade" "pip"

prune_venv_packages() {
    log_message "-> start VENV prune (Hausputz) (delete old pakets)..."
    
    # 1. create a list of currently installed packages (names only)
    # ignore pip, setuptools and wheel as they are part of the venv base
    local installed_pkgs
    installed_pkgs=$("$VENV_PATH/bin/pip" freeze | cut -d'=' -f1 | grep -vE "^(pip|setuptools|wheel|pkg-resources)$")

    # 2. extract names from requirements-runtime.txt
    # delete comments and version constraints (like >=, ==)
    local required_pkgs
    required_pkgs=$(grep -v '^#' "${BOSWATCH_PATH}/requirements-runtime.txt" | cut -d'=' -f1 | cut -d'>' -f1 | cut -d'<' -f1 | xargs)

    # 3. compare and delete
    for pkg in $installed_pkgs; do
        if [[ ! $required_pkgs =~ (^|[[:space:]])"$pkg"($|[[:space:]]) ]]; then
            log_message "Entferne veraltetes Paket: $pkg"
            "$VENV_PATH/bin/pip" uninstall -y "$pkg" >> "$SETUP_LOG" 2>&1 || true
        fi
    done
}

"$VENV_PATH/bin/pip" install -r "${BOSWATCH_PATH}/requirements-runtime.txt" >> "$SETUP_LOG" 2>&1 || exit_on_error "pip-install" "requirements"

# STEP 10: Configure & blacklist
progress_bar 10
log_message "-> Configure SDR blacklist..."

cat > /etc/modprobe.d/boswatch_blacklist_sdr.conf << 'MODPROBE'
# BOSWatch3 - blacklist the DVB drivers to avoid conflicts with the SDR driver
blacklist dvb_usb_rtl28xxu
blacklist rtl2830
blacklist dvb_usb_v2
blacklist dvb_core
MODPROBE
[ $?  -eq 0 ] || exit_on_error "write-blacklist" "modprobe"

# Handle config files
log_message "-> Copy config examples..."
for FILE in "${CONFIG_FILES[@]}"; do
  if [ -f "${BOSWATCH_PATH}/config/${FILE}. example" ] && [ !  -f "${BOSWATCH_PATH}/config/${FILE}" ]; then
    cp "${BOSWATCH_PATH}/config/${FILE}.example" "${BOSWATCH_PATH}/config/${FILE}" || exit_on_error "copy-config" "$FILE"
  fi
done

# ===  SET FINAL PERMISSIONS (SINGLE PASS) ===

log_message "-> Configure file permissions..."

# Ensure directories exist
mkdir -p "${BOSWATCH_PATH}/log" "${BOSWATCH_PATH}/config" || exit_on_error "mkdir" "config-log-directories"

# SINGLE chown pass - owner gets full control
chown -R "${ACTUAL_USER}:${ACTUAL_GROUP}" "$BOSWATCH_PATH" || exit_on_error "chown" "boswatch-directory"

# Python scripts executable
chmod +x "${BOSWATCH_PATH}"/*.py 2>/dev/null || true

# Config files readable/writable for owner
chmod 644 "${BOSWATCH_PATH}"/config/*.yaml 2>/dev/null || true
chmod 755 "${BOSWATCH_PATH}/config" 2>/dev/null || true

# Log directory:  setgid bit (2775) so new files inherit group ownership
chmod 2775 "${BOSWATCH_PATH}/log" || exit_on_error "chmod" "log-directory"

log_message "✓ File permissions configured"

# STEP 11: Hardware check
progress_bar 11
log_message "-> Hardware Check:  SDR Stick..."

# Check for RTL-SDR devices
if lsusb 2>/dev/null | grep -qiE "0bda:(2832|2838)|Realtek|RTL283[28]"; then
  tput setaf 3 2>/dev/null || true
  echo "⚠️  SDR STICK DETECTED !"
  tput sgr0 2>/dev/null || true
  
  echo "To apply the new driver rules, the SDR stick must be disconnected."
  echo "Please UNPLUG the SDR Stick now (timeout: 120 seconds)..."
  
  TIMEOUT=120
  ELAPSED=0
  while lsusb 2>/dev/null | grep -qiE "0bda:(2832|2838)|Realtek|RTL283[28]"; do
    sleep 1
    ((ELAPSED++))
    if [ $ELAPSED -ge $TIMEOUT ]; then
      echo "⚠️  Timeout:  Stick not removed after ${TIMEOUT}s - continuing anyway..."
      break
    fi
  done
  
  tput setaf 2 2>/dev/null || true
  echo "✓ Stick removed!"
  tput sgr0 2>/dev/null || true
  echo "You can plug it back in after the reboot."
else
  log_message "→ No SDR stick detected"
fi

# ===  CLEANUP & FINALIZATION ===

log_message "→ Installation finalization..."

# Move setup log to permanent location
mkdir -p "${BOSWATCH_PATH}/log/install" || exit_on_error "mkdir" "log-install"
if [ -f "$SETUP_LOG" ]; then
  mv "$SETUP_LOG" "${BOSWATCH_PATH}/log/install/" || exit_on_error "mv" "setup-log"
fi

# Save version info with extended metadata
{
  echo "INSTALLED_RTL=\"${TARGET_RTL_COMMIT}\""
  echo "INSTALLED_MULTIMON=\"${TARGET_MULTIMON_VER}\""
  echo "INSTALL_DATE=\"$(date -Is)\""
  echo "INSTALL_USER=\"${ACTUAL_USER}\""
  echo "BRANCH=\"${BRANCH}\""
} > "$VERSION_FILE" || exit_on_error "write" "version-file"

# Permissions on version file
chmod 644 "$VERSION_FILE" || exit_on_error "chmod" "version-file"

# Final cleanup:  remove installation temp directory
rm -rf "$BOSWATCH_INSTALL_PATH" 2>/dev/null || true

# Restore cursor
tput cnorm 2>/dev/null || true

# ===  FINAL MESSAGE ===

cat << 'EOF'

╔════════════════════════════════════════════════════════════════╗
║         ✓ Installation completed successfully!                ║
║   BOSWatch3 is installed in: ${INSTALL_PATH}$(printf '%*s' $((46 - ${#INSTALL_PATH})) '')║
╚════════════════════════════════════════════════════════════════╝

📋 NEXT STEPS: 

1. Edit configuration files:
   sudo nano /opt/boswatch3/config/client.yaml
   sudo nano /opt/boswatch3/config/server.yaml

2. Install systemd services:
   sudo python3 /opt/boswatch3/install_service.py

3. Check status:
   sudo systemctl status bw3_client. service
   sudo systemctl status bw3_server.service

📖 Documentation:  https://docs.boswatch.de/
📝 Setup Log: /opt/boswatch3/log/install/setup_log.txt
📋 Version Info: /opt/boswatch3/. version_info

⚠️  IMPORTANT: Please REBOOT the system before first start! 

EOF

if [ "$REBOOT" = "true" ]; then
  echo "🔄 Rebooting in 5 seconds..."
  sleep 5
  /sbin/reboot
fi

exit 0
