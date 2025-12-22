#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""!
    ____  ____  ______       __      __       __       _____
   / __ )/ __ \/ ___/ |     / /___ _/ /______/ /_     |__  /
  / __  / / / /\__ \| | /| / / __ `/ __/ ___/ __ \     /_ <
 / /_/ / /_/ /___/ /| |/ |/ / /_/ / /_/ /__/ / / /   ___/ /
/_____/\____//____/ |__/|__/\__,_/\__/\___/_/ /_/   /____/
                German BOS Information Script
                     by Bastian Schroll

@file:        install_service.py
@date:        26.12.2025
@author:      Claus Schichl, Bastian Schroll
@description: Install Service File with argparse CLI
"""

import os
import subprocess
import sys
import logging
import argparse
import yaml
from pathlib import Path

# === CONSTANTS ===
BW_DIR = Path('/opt/boswatch3')
BW_VENV = BW_DIR / 'venv' / 'bin' / 'python'
SERVICE_DIR = Path('/etc/systemd/system')
CONFIG_DIR = BW_DIR / 'config'
LOG_DIR = BW_DIR / 'log' / 'install'
LOG_FILE = LOG_DIR / 'service_install.log'


# Get the actual user (sudo or current) - ONCE
def _get_actual_user():
    """Get the user who ran sudo, or current user."""
    user = os.environ.get('SUDO_USER') or os.getenv('USER', 'root')
    try:
        result = subprocess.run(['id', '-gn', user], capture_output=True, text=True, timeout=5, check=True)
        group = result.stdout.strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        group = 'root'
    return user, group


ACTUAL_USER, ACTUAL_GROUP = _get_actual_user()

# Create log directory if it doesn't exist
LOG_DIR.mkdir(parents=True, exist_ok=True)

# === LANGUAGE MANAGEMENT ===
_lang = 'de'


def get_lang():
    return _lang


def set_lang(lang):
    global _lang
    _lang = lang


# === TEXT DICTIONARY ===
TEXT = {
    "de": {
        "script_title": "🛠️ BOSWatch Service Manager",
        "mode_dry": "🧪 DRY-RUN (nur Vorschau)",
        "mode_live": "🚀 LIVE MODE",
        "no_yaml": "❌ Keine . yaml-Dateien im config-Verzeichnis gefunden.",
        "found_yaml": "🔍 Gefundene YAML-Dateien:  {}",
        "action_prompt": "\nWas möchtest du tun?\n  [i] installieren\n  [r] entfernen\n  [e] beenden\n→ ",
        "edited_prompt": "Wurden die YAML-Dateien korrekt bearbeitet?  (y/n): ",
        "edit_abort": "⚠️  Bitte YAML-Dateien zuerst bearbeiten.  Vorgang abgebrochen.",
        "install_confirm": "Service für '{}' installieren?  (y/n): ",
        "skip_invalid_yaml": "⏭️  Überspringe fehlerhafte YAML:  {}",
        "install_done": "✅ Installation abgeschlossen.\n   Services installiert:  {}\n   Services übersprungen: {}",
        "invalid_input": "❌ Ungültige Eingabe. Erlaubt sind: {}",
        "no_services": "Keine bw3-Services gefunden.",
        "available_services": "\n📋 Verfügbare bw3-Services:",
        "remove_prompt": "❓ Was soll deinstalliert werden?\n→ ",
        "invalid_choice": "❌ Ungültige Auswahl.",
        "not_root": "🛑 Dieses Skript muss mit Root-Rechten ausgeführt werden (sudo).",
        "help_dry_run": "Nur anzeigen, nicht ausführen",
        "help_verbose": "Ausführliche Ausgabe",
        "help_quiet": "Weniger Ausgabe",
        "help_lang": "Sprache für alle Ausgaben [de/en] (Standard: de)",
        "creating_service_file": "📄 Erstelle Service-Datei:  {} → {}",
        "removing_service": "🗑️  Entferne Service: {}",
        "service_deleted": "✅ {} gelöscht.",
        "service_not_found": "⚠️  {} nicht gefunden oder im Dry-Run-Modus.",
        "yaml_error": "⚠️  Fehler in YAML {}: {}",
        "unknown_yaml_type": "⚠️  YAML-Typ für {} nicht erkannt.  Service wird übersprungen.",
        "verify_error": "⚠️  Fehler bei systemd-analyze verify für {}: {}",
        "verify_warn": "⚠️  Warnung bei systemd-analyze verify:\n{}",
        "verify_ok": "✅ {} erfolgreich verifiziert.",
        "install_skipped": "⏭️  Installation für '{}' übersprungen",
        "file_write_error": "⚠️  Fehler beim Schreiben der Datei {}: {}",
        "all": "[a] Alle deinstallieren",
        "exit": "[e] Beenden",
        "service_active": "✅ Service {} läuft erfolgreich.",
        "service_inactive": "⚠️  Service {} ist **nicht aktiv** – bitte prüfen.",
        "service_status_timeout": "⚠️  Timeout beim Prüfen des Service-Status: {}",
        "dryrun_status_check": "🧪 [Dry-Run] Service-Status von {} würde jetzt geprüft.",
        "max_attempts_exceeded": "❌ Maximale Anzahl an Eingabeversuchen überschritten.",
        "user_interrupt": "\n⚪ Abbruch durch Benutzer.",
        "unhandled_error": "❌ Unbehandelter Fehler: {}",
        "max_retries_skip": "Maximale Anzahl Eingabeversuche überschritten. Überspringe Service.",
        "max_retries_exit": "Maximale Anzahl Eingabeversuche überschritten. Beende Programm.",
        "verify_timeout": "⚠️  Timeout bei systemd-analyze verify für:  {}",
        "config_dir_missing": "❌ Config-Verzeichnis nicht gefunden: {}",
        "run_as_user": "👤 Services werden als User '{}' ausgeführt"
    },
    "en": {
        "script_title": "🛠️ BOSWatch Service Manager",
        "mode_dry": "🧪 DRY-RUN (preview only)",
        "mode_live": "🚀 LIVE MODE",
        "no_yaml": "❌ No .yaml files found in config directory.",
        "found_yaml": "🔍 YAML files found: {}",
        "action_prompt": "\nWhat would you like to do?\n  [i] install\n  [r] remove\n  [e] exit\n→ ",
        "edited_prompt": "Have the YAML files been edited correctly? (y/n): ",
        "edit_abort": "⚠️  Please edit YAML files first. Aborting.",
        "install_confirm": "Install service for '{}' ? (y/n): ",
        "skip_invalid_yaml": "⏭️  Skipping invalid YAML: {}",
        "install_done": "✅ Installation complete.\n   Services installed: {}\n   Services skipped: {}",
        "invalid_input": "❌ Invalid input. Allowed: {}",
        "no_services": "No bw3 services found.",
        "available_services": "\n📋 Available bw3 services:",
        "remove_prompt": "❓ What should be removed?\n→ ",
        "invalid_choice": "❌ Invalid choice.",
        "not_root": "🛑 This script must be run as root (sudo).",
        "help_dry_run": "Show actions only, do not execute",
        "help_verbose": "Show detailed output",
        "help_quiet": "Reduce output verbosity",
        "help_lang": "Language for all output [de/en] (default: de)",
        "creating_service_file": "📄 Creating service file: {} → {}",
        "removing_service": "🗑️  Removing service: {}",
        "service_deleted": "✅ {} deleted.",
        "service_not_found": "⚠️  {} not found or in dry-run mode.",
        "yaml_error": "⚠️  YAML error in {}: {}",
        "unknown_yaml_type": "⚠️  Unknown YAML type for {}.  Skipping service.",
        "verify_error": "⚠️  Error systemd-analyze verify for {}: {}",
        "verify_warn": "⚠️  Warning in systemd-analyze verify:\n{}",
        "verify_ok": "✅ {} verified successfully.",
        "install_skipped": "⏭️  Installation skipped for '{}'",
        "file_write_error": "⚠️  Error writing file {}: {}",
        "all": "[a] Remove all",
        "exit": "[e] Exit",
        "service_active": "✅ Service {} is running successfully.",
        "service_inactive": "⚠️  Service {} is **not active** – please check.",
        "service_status_timeout": "⚠️  Timeout while checking service status: {}",
        "dryrun_status_check": "🧪 [Dry-Run] Service status of {} would be checked now.",
        "max_attempts_exceeded": "❌ Maximum number of input attempts exceeded.",
        "user_interrupt": "\n⚪ Interrupted by user.",
        "unhandled_error": "❌ Unhandled error: {}",
        "max_retries_skip": "Maximum input attempts exceeded. Skipping service.",
        "max_retries_exit": "Maximum input attempts exceeded.  Exiting program.",
        "verify_timeout": "⚠️  Timeout during systemd-analyze verify for: {}",
        "config_dir_missing": "❌ Config directory not found: {}",
        "run_as_user": "👤 Services will run as user '{}'"
    }
}

# === COLORAMA SETUP ===
try:
    from colorama import init, Fore, Style
    init(autoreset=True)
except ImportError:
    class DummyStyle:
        RESET_ALL = ""
        BRIGHT = ""

    class DummyFore:
        RED = GREEN = YELLOW = BLUE = CYAN = MAGENTA = WHITE = RESET = ""

    Fore = DummyFore()
    Style = DummyStyle()

# === LOGGING SETUP ===


def setup_logging(verbose=False, quiet=False):
    """Setup logging to file and console with colorized output."""
    log_level = logging.INFO
    if quiet:
        log_level = logging.WARNING
    elif verbose:
        log_level = logging.DEBUG

    logger = logging.getLogger()
    logger.setLevel(log_level)
    logger.handlers.clear()  # Remove existing handlers

    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    # File Handler
    fh = logging.FileHandler(LOG_FILE, encoding='utf-8')
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    # Console Handler (colorized)
    class ColorFormatter(logging.Formatter):
        COLORS = {
            logging.DEBUG: Fore.CYAN,
            logging.INFO: Fore.GREEN,
            logging.WARNING: Fore.YELLOW,
            logging.ERROR: Fore.RED,
            logging.CRITICAL: Fore.RED + Style.BRIGHT,
        }

        def format(self, record):
            color = self.COLORS.get(record.levelno, Fore.RESET)
            message = super().format(record)
            return f"{color}{message}{Style.RESET_ALL}"

    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(ColorFormatter('%(levelname)s: %(message)s'))
    logger.addHandler(ch)

# === HELPER FUNCTIONS ===


def t(key):
    """Translation helper."""
    lang = get_lang()
    return TEXT.get(lang, TEXT['de']).get(key, key)


def get_user_input(prompt, valid_inputs, max_attempts=3):
    """Prompt user for input."""
    attempts = 0
    while attempts < max_attempts:
        value = input(prompt).strip().lower()
        if value in valid_inputs:
            return value
        logging.warning(t("invalid_input").format(", ".join(valid_inputs)))
        attempts += 1
    raise RuntimeError(t("max_attempts_exceeded"))


def list_yaml_files():
    """Returns a list of .yaml or .yml files in config directory."""
    if not CONFIG_DIR.exists():
        logging.error(t("config_dir_missing").format(CONFIG_DIR))
        return []
    return sorted([f.name for f in CONFIG_DIR.glob("*.y*ml")])


def test_yaml_file(file_path):
    """Tests if YAML file can be loaded without error."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            yaml.safe_load(f)
        return True
    except yaml.YAMLError as e:
        logging.error(t("yaml_error").format(file_path.name, str(e)))
        return False
    except Exception as e:
        logging.error(t("yaml_error").format(file_path.name, str(e)))
        return False


def detect_yaml_type(file_path):
    """Detects if YAML config is 'client' or 'server' type."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        # Prüfe ob data ein Dictionary ist
        if not isinstance(data, dict):
            logging.error(t("yaml_error").format(file_path.name, "YAML is not a dictionary"))
            return None

        if 'client' in data:
            return 'client'
        elif 'server' in data:
            return 'server'
        else:
            logging.error(t("unknown_yaml_type").format(file_path.name))
            return None
    except Exception as e:
        logging.error(t("yaml_error").format(file_path.name, str(e)))
        return None


def execute(command, dry_run=False):
    """Executes shell command unless dry_run is True."""
    cmd_str = " ".join(command) if isinstance(command, list) else command
    logging.debug("$ %s", cmd_str)

    if dry_run:
        return 0

    result = subprocess.run(
        command,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        logging.warning("Command failed: %s", result.stderr.strip())

    return result.returncode


def verify_service(service_path):
    """Runs 'systemd-analyze verify' on the service file."""
    try:
        result = subprocess.run(
            ['systemd-analyze', 'verify', str(service_path)],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode != 0:
            if result.stderr:
                logging.warning(t("verify_warn").format(result.stderr.strip()))
        else:
            logging.info(t("verify_ok").format(service_path.name))
    except subprocess.TimeoutExpired:
        logging.warning(t("verify_timeout").format(service_path.name))
    except Exception as e:
        logging.error(t("verify_error").format(service_path.name, str(e)))

# === SERVICE INSTALLATION ===


def install_service(yaml_file, dry_run=False):
    """Creates and installs systemd service based on YAML config."""
    yaml_path = CONFIG_DIR / yaml_file
    yaml_type = detect_yaml_type(yaml_path)

    if yaml_type not in ('client', 'server'):
        logging.error(t("unknown_yaml_type").format(yaml_file))
        return

    service_name = f"bw3_{yaml_path.stem}.service"
    service_path = SERVICE_DIR / service_name

    # Service configuration per type
    is_server = (yaml_type == 'server')

    # Build service file content cleanly (no empty lines hack)
    unit_section = [
        "[Unit]",
        f"Description={'BOSWatch Server' if is_server else 'BOSWatch Client'}",
        f"After={'network-online.target' if is_server else 'network.target'}",
    ]
    if is_server:
        unit_section.append("Wants=network-online.target")

    service_section = [
        "[Service]",
        "Type=simple",
        f"User={ACTUAL_USER}",
        f"Group={ACTUAL_GROUP}",
        f"WorkingDirectory={BW_DIR}",
        f"ExecStart={BW_VENV} {BW_DIR}/bw_{'server' if is_server else 'client'}.py -c {CONFIG_DIR}/{yaml_file}",
        "Restart=on-failure",
        "RestartSec=10s",
        "StandardOutput=journal",
        "StandardError=journal",
    ]

    install_section = [
        "[Install]",
        "WantedBy=multi-user.target",
    ]

    service_content = '\n'.join(unit_section + [''] + service_section + [''] + install_section) + '\n'

    logging.info(t("creating_service_file").format(yaml_file, service_name))

    if not dry_run:
        try:
            with open(service_path, 'w', encoding='utf-8') as f:
                f.write(service_content)
            logging.debug(f"Service file created: {service_path}")
        except IOError as e:
            logging.error(t("file_write_error").format(service_path, str(e)))
            return
        verify_service(service_path)

    execute(["systemctl", "daemon-reload"], dry_run=dry_run)
    execute(["systemctl", "enable", service_name], dry_run=dry_run)
    execute(["systemctl", "start", service_name], dry_run=dry_run)

    if not dry_run:
        try:
            subprocess.run(
                ["systemctl", "is-active", "--quiet", service_name],
                check=True,
                timeout=5
            )
            logging.info(t("service_active").format(service_name))
        except subprocess.CalledProcessError:
            logging.warning(t("service_inactive").format(service_name))
        except subprocess.TimeoutExpired:
            logging.warning(t("service_status_timeout").format(service_name))
    else:
        logging.info(t("dryrun_status_check").format(service_name))

# === SERVICE REMOVAL ===


def remove_service(service_name, dry_run=False):
    """Stops, disables and removes the given systemd service."""
    logging.warning(t("removing_service").format(service_name))
    execute(["systemctl", "stop", service_name], dry_run=dry_run)
    execute(["systemctl", "disable", service_name], dry_run=dry_run)

    service_path = SERVICE_DIR / service_name
    if not dry_run and service_path.exists():
        try:
            service_path.unlink()
            logging.info(t("service_deleted").format(service_name))
        except Exception as e:
            logging.error(t("file_write_error").format(service_path, str(e)))
    else:
        logging.warning(t("service_not_found").format(service_name))

    execute(["systemctl", "daemon-reload"], dry_run=dry_run)


def remove_menu(dry_run=False):
    """Interactive menu to remove services."""
    while True:
        services = sorted([
            f for f in os.listdir(SERVICE_DIR)
            if f.startswith('bw3_') and f.endswith('.service')
        ])

        if not services:
            print(Fore.YELLOW + t("no_services") + Style.RESET_ALL)
            return

        print(Fore. CYAN + t("available_services") + Style.RESET_ALL)
        for i, s in enumerate(services):
            try:
                if dry_run:
                    status = "🧪"
                else:
                    is_active = subprocess.run(
                        ["systemctl", "is-active", "--quiet", s],
                        capture_output=True,
                        timeout=3
                    ).returncode == 0
                    status = "✅" if is_active else "⚫"
            except (subprocess.TimeoutExpired, Exception):
                status = "❓"  # Unknown status
            print(f" [{i}] {status} {s}")
        print(" " + t("all"))
        print(" " + t("exit"))

        try:
            choice = get_user_input(
                t("remove_prompt"),
                ['e', 'a'] + [str(i) for i in range(len(services))]
            )
        except RuntimeError:
            logging.error(t("max_attempts_exceeded"))
            break

        if choice == 'e':
            break
        elif choice == 'a':
            for s in services:
                remove_service(s, dry_run=dry_run)
            continue
        else:
            remove_service(services[int(choice)], dry_run=dry_run)
            continue

# === MAIN PROGRAM ===


def init_language():
    """Parses --lang/-l argument early."""
    lang_parser = argparse.ArgumentParser(add_help=False)
    lang_parser.add_argument(
        '--lang', '-l',
        choices=['de', 'en'],
        default='de',
        metavar='LANG'
    )
    lang_args, remaining_argv = lang_parser.parse_known_args()
    set_lang(lang_args.lang)
    return lang_parser, remaining_argv


def main(dry_run=False):
    """Main program:  install or remove service."""
    print(Fore.GREEN + Style.BRIGHT + t("script_title") + Style.RESET_ALL)
    print(Fore.CYAN + (t('mode_dry') if dry_run else t('mode_live')) + Style.RESET_ALL)
    print(Fore.MAGENTA + t("run_as_user").format(ACTUAL_USER) + Style.RESET_ALL)
    print()

    if not CONFIG_DIR.exists():
        print(Fore.RED + t("config_dir_missing").format(CONFIG_DIR) + Style.RESET_ALL)
        sys.exit(1)

    yaml_files = list_yaml_files()
    if not yaml_files:
        print(Fore.RED + t("no_yaml") + Style.RESET_ALL)
        sys.exit(1)

    print(Fore.GREEN + t("found_yaml").format(len(yaml_files)) + Style.RESET_ALL)
    for f in yaml_files:
        file_path = CONFIG_DIR / f
        valid = test_yaml_file(file_path)
        status = Fore.GREEN + "✅" if valid else Fore.RED + "❌"
        print(f" - {f} {status}{Style.RESET_ALL}")

    try:
        action = get_user_input(t("action_prompt"), ['i', 'r', 'e'])
    except RuntimeError:
        logging.error(t("max_retries_exit"))
        sys.exit(1)

    if action == 'e':
        sys.exit(0)
    elif action == 'r':
        remove_menu(dry_run=dry_run)
        return

    try:
        edited = get_user_input(t("edited_prompt"), ['y', 'n'])
    except RuntimeError:
        logging.error(t("max_retries_exit"))
        sys.exit(1)

    if edited == 'n':
        print(Fore.YELLOW + t("edit_abort") + Style.RESET_ALL)
        sys.exit(0)

    installed = 0
    skipped = 0

    for yaml_file in yaml_files:
        file_path = CONFIG_DIR / yaml_file
        if not test_yaml_file(file_path):
            print(Fore.RED + t("skip_invalid_yaml").format(yaml_file) + Style.RESET_ALL)
            skipped += 1
            continue

        try:
            install = get_user_input(t("install_confirm").format(yaml_file), ['y', 'n'])
        except RuntimeError:
            logging.error(t("max_retries_skip"))
            skipped += 1
            continue

        if install == 'y':
            install_service(yaml_file, dry_run=dry_run)
            installed += 1
        else:
            logging.info(t("install_skipped").format(yaml_file))
            skipped += 1

    print()
    logging.info(t("install_done").format(installed, skipped))


if __name__ == "__main__":
    lang_parser, remaining_argv = init_language()

    parser = argparse.ArgumentParser(
        description=t("script_title"),
        parents=[lang_parser]
    )
    parser.add_argument('--dry-run', action='store_true', help=t("help_dry_run"))
    parser.add_argument('--verbose', '-v', action='store_true', help=t("help_verbose"))
    parser.add_argument('--quiet', '-q', action='store_true', help=t("help_quiet"))

    args = parser.parse_args(remaining_argv)

    setup_logging(verbose=args.verbose, quiet=args.quiet)

    if os.geteuid() != 0:
        print(Fore.RED + t("not_root") + Style.RESET_ALL)
        sys.exit(1)

    try:
        main(dry_run=args.dry_run)
    except KeyboardInterrupt:
        print(t("user_interrupt"))
        sys.exit(1)
    except Exception as e:
        logging.critical(t("unhandled_error").format(str(e)))
        sys.exit(1)
