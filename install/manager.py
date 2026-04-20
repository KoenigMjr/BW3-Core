#!/usr/bin/python3
# -*- coding: utf-8 -*-
r"""
    ____  ____  ______       __      __       __       _____
   / __ )/ __ \/ ___/ |     / /___ _/ /______/ /_     |__  /
  / __  / / / /\__ \| | /| / / __  / __/ ___/ __ \     /_ <
 / /_/ / /_/ /___/ /| |/ |/ / /_/ / /_/ /__/ / / /   ___/ /
/_____/\____//____/ |__/|__/\__,_/\__/\___/_/ /_/   /____/
                German BOS Information Script
                     by Bastian Schroll
@file:        manager.py
@date:        07.05.2026
@author:      Claus Schichl
@description: Main Management File for BOSWatch3 (install, update, service management)
"""

import json
import os
import pwd
import shutil
import subprocess
import time
import re
import packaging.version
from pathlib import Path

import yaml
from alive_progress import alive_bar
from colorama import Fore, Style, init

# Initialize colors
init(autoreset=True)


class BW3Manager:
    def __init__(self):
        # Central path to project root
        self.base_path = Path(__file__).parent.parent.resolve()
        self.install_path = Path(__file__).parent.resolve()

        # SUDO_USER detection
        self.real_user = os.environ.get('SUDO_USER') or os.getlogin()

        self.config_path = self.install_path / "manager_config.yaml"
        self.trans_path = self.install_path / "translations.yaml"

        # ============== CENTRAL DEFINITION ==============
        self.defaults = {
            'repo_url': os.environ.get('BW3_REPO_URL', "https://github.com/BOSWatch/BW3-Core"),
            'branch': os.environ.get('BW3_BRANCH', "master"),
            'language': os.environ.get('BW3_LANG', "de"),
            'installed': False,
            'rtlsdr_commit': "2659e2df31e592d74d6dd264a4f5ce242c6369c8",
            'multimon_branch': "1.1.8",
            'installed_rtlsdr': None,
            'installed_multimon': None,
            'installed_packages': {}  # ← will be filled dynamically
        }

        self.load_config()
        self.load_translations()
        self.lang = self.config['language']

    # ============== LOAD CONFIG ==============

    def load_config(self):
        """Loads the config and fills missing values with defaults."""
        if self.config_path.exists():
            with open(self.config_path, 'r') as f:
                loaded = yaml.safe_load(f) or {}
            self.config = {**self.defaults, **loaded}
        else:
            self.config = self.defaults.copy()
            self.save_config()

    def save_config(self):
        """Saves the current state of the config with fixed sorting and manual change protection."""
        header = r"""# -*- coding: utf-8 -*-
#    ____  ____  ______       __      __       __       _____
#   / __ )/ __ \/ ___/ |     / /___ _/ /______/ /_     |__  /
#  / __  / / / /\__ \| | /| / / __ `/ __/ ___/ __ \     /_ <
# / /_/ / /_/ /___/ /| |/ |/ / /_/ / /_/ /__/ / / /   ___/ /
#/_____/\____//____/ |__/|__/\__,_/\__/\___/_/ /_/   /____/
#                German BOS Information Script
#                     by Bastian Schroll
"""
        # 1. Get clean copy of disk to preserve manual edits
        disk_config = {}
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    disk_config = yaml.safe_load(f) or {}
            except Exception:
                pass

        # 2. Merge actual changes from program into disk state
        disk_config.update(self.config)
        self.config = disk_config

        # 3. Defining fixed order
        order = [
            'installed', 'version', 'branch',
            'installed_multimon', 'multimon_branch',
            'installed_rtlsdr', 'rtlsdr_commit',
            'installed_packages'
        ]

        # 4. Rebuilding dict in correct order
        sorted_config = {}
        for key in order:
            if key in self.config:
                sorted_config[key] = self.config[key]

        # Add all other keys (like repo_url, etc.)
        for key in self.config:
            if key not in sorted_config:
                sorted_config[key] = self.config[key]

        # 5. Save with sort_keys=False
        with open(self.config_path, 'w', encoding='utf-8') as f:
            f.write(header + "\n")
            yaml.dump(sorted_config, f, default_flow_style=False, sort_keys=False)

    def load_translations(self):
        """Loads translation strings from YAML file."""
        with open(self.trans_path, 'r') as f:
            self.translations = yaml.safe_load(f)

    def t(self, key):
        """Gets the translation for the key. Returns the key itself if not found."""
        lang = self.config.get('language', 'de')

        # If language is missing in YAML, fallback to German
        if lang not in self.translations:
            lang = 'de'

        # Use .get() to return a default value (the key itself) if missing.
        return self.translations[lang].get(key, f"[{key}]")

    def run_with_progress(self, commands, desc):
        """Executes a list of commands with a progress bar and writes everything to a log file."""
        log_dir = self.base_path / "log" / "install"
        log_dir.mkdir(parents=True, exist_ok=True)  # Ensure folder exists
        log_file = log_dir / "setup_log.txt"

        # Open log in 'a' (Append) mode
        with open(log_file, "a") as f:
            f.write(f"\n--- Starting Task: {desc} ---\n")

            with alive_bar(len(commands), title=desc, bar='smooth', spinner='dots') as bar:
                for cmd in commands:
                    f.write(f"Executing: {cmd}\n")
                    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

                    if result.stdout:
                        f.write(result.stdout)
                    if result.stderr:
                        prefix = ("STDERR" if result.returncode != 0 else "INFO/STDERR")
                        f.write(f"{prefix}: {result.stderr}")

                    if result.returncode != 0:
                        f.write(f"FAILED with return code {result.returncode}\n")
                        self.log(Fore.RED + self.t('run_cmd_failed').format(cmd, log_file))
                        raise subprocess.CalledProcessError(result.returncode, cmd)

                    bar()  # ← step forward

    # ============== LOGGING ==============

    def log(self, message, color=Fore.WHITE, bright=False):
        """Prints in color to the terminal and cleanly to the logfile."""
        # 1. Terminal Output (Colored)
        style = Style.BRIGHT if bright else Style.NORMAL
        print(f"{color}{style}{message}{Style.RESET_ALL}")

        # 2. Log File Output (Plain text)
        log_file = self.base_path / "log" / "install" / "setup_log.txt"
        with open(log_file, "a") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {message}\n")

    # ============== EXAMPLE CONFIG INSTALL ==============

    def setup_example_configs(self):
        """Copies .example files from config/examples/ to real config files."""
        self.log(f"\n{Fore.CYAN}--- {self.t('check_configs_header')} ---")
        config_dir = self.base_path / "config"
        examples_dir = config_dir / "examples"

        if not examples_dir.exists():
            self.log(Fore.YELLOW + self.t('config_no_examples_dir'))
            return

        # Find all .example files
        for example_file in examples_dir.iterdir():
            # Only consider .yaml and .ini files
            if example_file.suffix not in ('.yaml', '.ini'):
                continue

            real_file = config_dir / example_file.name

            if not real_file.exists():
                self.log(Fore.GREEN + self.t('config_standard').format(real_file.name))
                shutil.copy(example_file, real_file)
                try:
                    # Correct owner (so normal user can edit them)
                    uid = pwd.getpwnam(self.real_user).pw_uid
                    gid = pwd.getpwnam('www-data').pw_gid  # or another group
                    os.chown(real_file, uid, gid)
                    # Set permissions so user can edit them
                    os.chmod(real_file, 0o664)
                except KeyError:
                    # www-data might not exist on all systems
                    pass
                self.log(Fore.GREEN + self.t('config_created').format(real_file.name))
            else:
                # Already exists — check for new keys (only prints on drift)
                self._check_config_drift(example_file, real_file)
                self.log(Fore.YELLOW + self.t('config_exists').format(real_file.name))

    def _check_config_drift(self, example_file, real_file):
        """Warns if example file contains keys missing in user config."""
        # Only useful for YAML, skip .ini
        if example_file.suffix != '.yaml':
            return
        try:
            with open(example_file) as f:
                example_keys = set(yaml.safe_load(f) or {})
            with open(real_file) as f:
                real_keys = set(yaml.safe_load(f) or {})

            new_keys = example_keys - real_keys
            if new_keys:
                self.log(
                    Fore.YELLOW +
                    f"  ⚠ {real_file.name}: "
                    f"{self.t('config_new_keys').format(', '.join(sorted(new_keys)))}")
                self.log(
                    Fore.YELLOW +
                    f"    → {self.t('config_check_examples')}:"
                    f" config/examples/{example_file.name}")
        except Exception:
            pass

    # ============== RESTART SERVICES ==============

    def restart_active_services(self):
        """Finds all BOSWatch services and restarts them if active."""
        self.log(f"\n{Fore.CYAN}--- {self.t('update_restarting_services')} ---")
        service_dir = "/etc/systemd/system"
        if not os.path.exists(service_dir):
            return

        # Find all bw3_*.service files
        services = [f for f in os.listdir(service_dir) if f.startswith('bw3_') and f.endswith('.service')]

        if not services:
            self.log(f"{self.t('srv_none_found')}")
            return

        restarted = 0
        for service in services:
            # Check if service is currently running
            status = subprocess.run(["systemctl", "is-active", "--quiet", service])
            if status.returncode == 0:  # 0 means 'active'
                subprocess.run(["systemctl", "restart", service])
                self.log(Fore.GREEN + self.t('srv_restarted').format(service))
                restarted += 1
            else:
                self.log(Fore.YELLOW + self.t('srv_skip_inactive').format(service))

        if restarted > 0:
            # Daemon reload never hurts after update in case paths changed
            subprocess.run(["systemctl", "daemon-reload"])

    # ============== CLEANUP ==============

    def safe_venv_cleanup(self):
        """Entfernt Pakete die weder core/manager noch aktiv genutzt sind."""
        self.log(f"\n{Fore.CYAN}{self.t('venv_safe_header')}")

        venv_pip = self.base_path / "venv" / "bin" / "pip"
        req_file = self.base_path / "requirements-runtime.txt"

        if not req_file.exists():
            self.log(Fore.YELLOW + self.t('venv_safe_no_req'))
            return

        tag_mapping = self.parse_requirements_tags()

        # 1. Pakete die IMMER behalten werden: core + manager
        always_keep = set(
            p.split('==')[0].split('>=')[0].lower().replace('-', '_').strip()
            for p in tag_mapping.get('core', []) + tag_mapping.get('manager', [])
        )

        # 2. Pakete die aktiv genutzt werden (aus server/client.yaml)
        active_resources = self.get_required_packages()
        actively_needed = set()

        for resource in active_resources:
            resource_lower = resource.lower()
            # Exakter Match
            if resource_lower in tag_mapping:
                for pkg in tag_mapping[resource_lower]:
                    pkg_name = pkg.split('==')[0].split('>=')[0].lower().replace('-', '_').strip()
                    actively_needed.add(pkg_name)
            # Teil-Match nach Punkt (z.B. modeFilter -> modefilter)
            if '.' in resource_lower:
                sub = resource_lower.split('.')[-1]
                if sub in tag_mapping:
                    for pkg in tag_mapping[sub]:
                        pkg_name = pkg.split('==')[0].split('>=')[0].lower().replace('-', '_').strip()
                        actively_needed.add(pkg_name)

        # 3. Gesamtmenge der erlaubten Pakete
        allowed = always_keep | actively_needed

        # System-Pakete niemals anfassen
        critical = {'pip', 'setuptools', 'wheel', 'pkg_resources'}
        allowed |= critical

        # 4. Installierte Pakete abfragen
        result = subprocess.run(
            [str(venv_pip), "list", "--format=json"],
            capture_output=True, text=True
        )
        installed_packages = [
            pkg['name'].lower().replace('-', '_')
            for pkg in json.loads(result.stdout)
        ]

        # 5. Kandidaten für Entfernung bestimmen
        to_remove = []
        for pkg in installed_packages:
            if pkg in allowed:
                continue

            # Prüfen ob Paket von einem anderen benötigt wird (Transitive Dependency)
            show_result = subprocess.run(
                [str(venv_pip), "show", pkg],
                capture_output=True, text=True
            )
            is_required = False
            for line in show_result.stdout.splitlines():
                if line.startswith("Required-by:"):
                    if line.split(":")[1].strip():
                        is_required = True
                    break

            if not is_required:
                to_remove.append(pkg)

        # 6. Entfernen
        if to_remove:
            self.log(Fore.YELLOW + self.t('venv_safe_remove').format(to_remove))
            for pkg in to_remove:
                subprocess.run(
                    [str(venv_pip), "uninstall", "-y", pkg],
                    capture_output=True
                )
            self.log(Fore.GREEN + self.t('venv_safe_removed').format(len(to_remove), ', '.join(to_remove)))

        else:
            self.log(Fore.GREEN + self.t('venv_safe_clean'))

    # ============== BRANCH-CHANGE ==============

    def change_branch_logic(self):
        """Logic for changing git branch."""
        self.log(f"\n{Fore.YELLOW}" + self.t('branch_loading').format(self.config['repo_url']))
        try:
            result = subprocess.run(
                f"git ls-remote --heads {self.config['repo_url']}",
                shell=True, capture_output=True, text=True, timeout=10)

            branches = []
            for line in result.stdout.splitlines():
                branch_name = line.split("refs/heads/")[-1]
                branches.append(branch_name)

            if not branches:
                self.log(Fore.RED + self.t('branch_not_found'))
                return

            self.log(f"\n{self.t('select_option')}")
            for i, b in enumerate(branches):
                self.log(f"[{i + 1}] {b}")

            choice_idx = int(input(self.t('branch_select_prompt'))) - 1
            new_branch = branches[choice_idx]

            self.config['branch'] = new_branch
            # Save choice in manager_config.yaml
            with open(self.config_path, 'w') as f:
                yaml.dump(self.config, f)

            self.log("\n" + Fore.GREEN + self.t('branch_set_success').format(new_branch))

            # Convenience check
            answer = input("\n" + self.t('branch_ask_update').format(new_branch))
            if answer.lower() == 'y':
                self.update_routine()
            else:
                self.log(Fore.YELLOW + self.t('branch_remembered'))

        except Exception as e:
            self.log(Fore.RED + self.t('branch_error').format(e))

    # ============== SERVICE-DASHBOARD & LOGS ==============

    def get_service_dashboard_data(self):
        """Collects live data of installed BOSWatch services from systemd."""
        service_dir = "/etc/systemd/system"
        if not os.path.exists(service_dir):
            return {}

        # Find all installed bw3_ services
        services = [f for f in os.listdir(service_dir) if f.startswith('bw3_') and f.endswith('.service')]
        if not services:
            return {}

        dashboard_data = {}
        for svc in sorted(services):
            # Name without .service for cleaner display
            display_name = svc.replace('.service', '')

            # systemctl show returns exact Key=Value pairs
            res = subprocess.run(["systemctl", "show", svc, "--property=ActiveState,SubState,Result"], capture_output=True, text=True)

            # Convert output to dictionary
            props = dict(line.split('=', 1) for line in res.stdout.splitlines() if '=' in line)
            dashboard_data[display_name] = props

        return dashboard_data

    def show_service_logs(self):
        """Allows selection of a service and shows journalctl logs."""
        service_dir = Path("/etc/systemd/system")
        services = sorted([f.name for f in service_dir.glob('bw3_*.service')])

        if not services:
            self.log(Fore.YELLOW + self.t('log_none'))
            time.sleep(2)
            return

        while True:
            # "Push" screen up for clean view
            print("\n" * shutil.get_terminal_size().lines)
            self.log(f"{Fore.GREEN}=== {self.t('menu_logs')} ===\n")

            for i, svc in enumerate(services):
                # Check if service currently has a problem
                status = subprocess.run(["systemctl", "is-failed", svc], capture_output=True, text=True).stdout.strip()
                error_hint = Fore.RED + " [FAILED]" if status == "failed" else ""
                self.log(f"[{i + 1}] {svc}{error_hint}")

            self.log("[0] " + self.t('menu_exit'))

            choice = input("\n" + self.t('log_select_prompt'))

            if choice == "0":
                break

            try:
                idx = int(choice) - 1
                if 0 <= idx < len(services):
                    selected_svc = services[idx]
                    self.log(f"\n{Fore.CYAN}" + self.t('log_viewing').format(selected_svc))

                    # journalctl: -u (unit), -n 50 (last 50), --no-pager
                    subprocess.run(["journalctl", "-u", selected_svc, "-n", "50", "--no-pager"])

                    input(Fore.YELLOW + self.t('log_back_prompt'))
            except (ValueError, IndexError):
                continue

    # ============== MENU ==============

    def main_menu(self):
        """Main interaction menu."""
        if os.geteuid() != 0:
            self.log(Fore.RED + self.t('error_not_root'))
            return

        while True:
            # --- GENTLE SCREEN RESET WITH TOP-ALIGNMENT ---
            # terminal_height = shutil.get_terminal_size().lines
            # Push up and set cursor to top with \033[H
            # print("\n" * terminal_height + "\033[H", end="")

            width = shutil.get_terminal_size().columns
            timestamp = time.strftime('%H:%M:%S')
            separator = f"─── {timestamp} " + "─" * (width - len(timestamp) - 5)
            print(f"\n{Style.DIM}{separator}{Style.RESET_ALL}")

            is_installed = self.config.get('installed', False)

            # Header
            self.log(f"\n{Fore.GREEN}=== {self.t('welcome')} ===")

            # --- DASHBOARD BLOCK START ---
            if is_installed:
                services_status = self.get_service_dashboard_data()
                if services_status:
                    self.log(f"{Style.BRIGHT}{self.t('menu_dashboard_title')}:")
                    for name, props in services_status.items():
                        state = props.get('ActiveState', 'unknown')
                        sub = props.get('SubState', 'unknown')

                        if state == 'active':
                            # Green and full dot for running services
                            color = Fore.GREEN
                            dot = "●"
                            info = f"{state} ({sub})"
                        elif state == 'failed':
                            # Red and info for crashes
                            color = Fore.RED
                            dot = "●"
                            reason = props.get('Result', 'error')
                            info = (f"{state} ({self.t('menu_dashboard_reason')}: {reason})")
                        else:
                            # Yellow and empty circle for stopped services
                            color = Fore.YELLOW
                            dot = "○"
                            info = f"{state} ({sub})"

                        # Formatted: Name left-aligned (14 chars), Info in gray
                        self.log(f"  {color}{dot} {Fore.WHITE}{name:<14} {Style.DIM}[{info}]")
                    self.log("")  # Separator line
            # --- DASHBOARD BLOCK END ---

            # --- MAIN MENU OPTIONS ---
            self.log(f"1) {self.t('menu_install')}")

            if is_installed:
                self.log(f"2) {self.t('menu_update')}")
                self.log(f"3) {self.t('menu_service_manager')}")
                self.log(f"4) {self.t('menu_config')}")
                self.log(f"5) {self.t('menu_logs')}")
                self.log(f"6) {self.t('menu_deps')}")
            else:
                # Show as grayed out
                self.log(Style.DIM + f"2) {self.t('menu_update')} "
                         f"{self.t('menu_locked')}")
                self.log(Style.DIM + f"3) {self.t('menu_service_manager')} "
                         f"{self.t('menu_locked')}")
                self.log(Style.DIM + f"4) {self.t('menu_config')} "
                         f"{self.t('menu_locked')}")
                self.log(Style.DIM + f"5) {self.t('menu_logs')} "
                         f"{self.t('menu_locked')}")
                self.log(Style.DIM + f"6) {self.t('menu_deps')} "
                         f"{self.t('menu_locked')}")

            self.log(f"0) {self.t('menu_exit')}")

            choice = input("\n> ")

            if choice == "1":
                self.install_routine()
            elif choice in ("2", "3", "4", "5", "6") and not is_installed:
                self.log(Fore.RED + self.t('menu_not_installed'))
            elif choice == "2":
                self.update_routine()
            elif choice == "3":
                self.service_menu()
            elif choice == "4":
                self.change_branch_logic()
            elif choice == "5":
                self.show_service_logs()
            elif choice == "6":
                self.sync_dependencies()
            elif choice == "0":
                break

    # ============== CHECK AVAILABLE APT-MANAGER ==============

    def wait_for_apt(self, timeout=300):
        """Waits until the APT Package Manager is free."""
        self.log(Fore.YELLOW + self.t('wait_apt_checking'))
        start_time = time.time()

        # Paths to common lock files
        lock_files = ["/var/lib/dpkg/lock-frontend", "/var/lib/apt/lists/lock"]

        while time.time() - start_time < timeout:
            locked = False
            for lock in lock_files:
                # If file exists and is held by a process
                if os.path.exists(lock):
                    # Check with fuser if a process actually accesses it
                    res = subprocess.run(["fuser", lock], capture_output=True)
                    if res.returncode == 0:  # 0 means: Someone is using it
                        locked = True
                        break

            if not locked:
                return True

            remaining = int(timeout - (time.time() - start_time))
            self.log(Fore.YELLOW + self.t('wait_apt_busy').format(remaining))
            time.sleep(5)

        self.log(Fore.RED + self.t('wait_apt_timeout'))
        return False

    # ============== INSTALL ==============

    def install_routine(self):
        """The main installation routine (formerly install.sh)."""

        # 1a. Check if APT is free
        if not self.wait_for_apt():
            return  # Abort if APT is still busy after 5 min

        # 1b. Install system dependencies (APT)
        apt_packages = ["git", "cmake", "build-essential", "libusb-1.0-0-dev", "pkg-config", "libpulse-dev", "libx11-dev", "python3-pip"]

        self.log(f"\n{Fore.CYAN}--- {self.t('installing_sys_deps')} ---")
        self.run_with_progress(
            [f"DEBIAN_FRONTEND=noninteractive apt-get install -y {p}"
             for p in apt_packages], "Apt-Packages")

        # 2. Install hardware tools
        self.check_and_update_hardware_tools()

        # 3. Blacklist DVB-T (so SDR is free for radio)
        self.log(f"\n{Fore.CYAN}--- {self.t('blacklist_sdr')} ---")

        blacklist_path = "/etc/modprobe.d/blacklist-rtl.conf"
        blacklist_content = ("blacklist dvb_usb_rtl28xxu\nblacklist rtl2832\nblacklist rtl2830")

        try:
            with open(blacklist_path, "w") as f:
                f.write(blacklist_content)
            self.log(f"{Fore.GREEN}✔ {self.t('blacklist_success').format(blacklist_path)}")
        except IOError as e:
            self.log(f"{Fore.RED}✘ {self.t('blacklist_error').format(e)}")
            self.log(f"{Fore.YELLOW}{self.t('blacklist_warning')}")

        # 4. Paths and Permissions (adapted from install.sh)
        # Determine real user even if sudo is used
        self.log(f"\n{Fore.CYAN}--- {self.t('perm_setup')} ---")

        setup_cmds = [
            f"mkdir -p {self.base_path}/log/install",
            # Set owner to real user and group to www-data (for web access)
            f"chown -R {self.real_user}:www-data {self.base_path}",
            # 775 = User & Group may write/read, others only read
            f"chmod -R 775 {self.base_path}",
            # Setgid-bit for logs (new files in log inherit group)
            f"chmod 2775 {self.base_path}/log"
        ]

        self.run_with_progress(setup_cmds, "Permissions")

        # 5. Check config files
        self.setup_example_configs()

        os.system(f"chown -R {self.real_user}:www-data {self.base_path}/config")

        # 6. Install initial Python dependencies (prepare main program)
        self.log(f"\n{Fore.CYAN}--- {self.t('pip_install_header')} ---")
        venv_pip = self.base_path / "venv" / "bin" / "pip"
        req_file = self.base_path / "requirements-runtime.txt"

        if req_file.exists():
            tag_mapping = self.parse_requirements_tags()
            core_packages = tag_mapping.get('core', []) + tag_mapping.get('manager', [])

            if core_packages:
                install_cmds = [f"{venv_pip} install {p}" for p in core_packages]
                self.run_with_progress(install_cmds, "PIP Core Install")
                self.log(Fore.YELLOW + self.t('pip_install_hint'))
            else:
                self.log(Fore.RED + self.t('pip_req_missing').format(self.base_path))

        self._update_pip_tracking()
        self.config['installed'] = True
        self.save_config()

        self.log(f"\n{Fore.GREEN}{Style.BRIGHT}{self.t('done_success')}")

        # 7. Reboot query
        self.ask_for_reboot()

    # ============== UPDATE ==============

    def update_routine(self):
        """Main update routine with hardware version check."""
        branch = self.config['branch']
        venv_pip = self.base_path / "venv" / "bin" / "pip"
        self.log(f"\n{Fore.CYAN}--- {self.t('update_fetching')} ---")

        # 1. Core update fetch
        subprocess.run(["git", "fetch", "origin", branch], cwd=self.base_path)

        # 2. Check hardware versions
        self.check_and_update_hardware_tools()

        # 3. Compare hashes
        local_hash = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.base_path, capture_output=True, text=True).stdout.strip()
        remote_hash = subprocess.run(
            ["git", "rev-parse", f"origin/{branch}"],
            cwd=self.base_path, capture_output=True, text=True).stdout.strip()
        current_branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=self.base_path, capture_output=True, text=True).stdout.strip()

        # Check if we are on the correct branch
        if local_hash == remote_hash and current_branch == branch:
            self.log(f"{Fore.GREEN}✔ {self.t('update_not_needed')} "
                     f"(Hash: {local_hash[:7]})")
            return

        # 4. Update found or branch switch necessary
        self.log(f"{Fore.YELLOW}★ {self.t('update_found')} "
                 f"({local_hash[:7]} -> {remote_hash[:7]})")

        # 5. SECURITY QUERY
        confirm = input(Fore.RED + Style.BRIGHT + self.t('update_warning_changes')).lower()
        if confirm != 'y':
            self.log(Fore.YELLOW + self.t('update_cancel_changes'))
            return

        # 6. Branch Switch
        # 6a: Discard local changes to tracked files immediately
        self.log(Fore.YELLOW + self.t('update_clean_local'))
        subprocess.run(["git", "reset", "--hard", "HEAD"],
                       cwd=self.base_path, capture_output=True)

        # 6b: Force branch switch (-f)
        if current_branch != branch:
            self.log(Fore.CYAN + f"  → {self.t('update_branch_switch').format(branch)}")
            # Use checkout -B: creates branch if needed OR resets it
            subprocess.run(["git", "checkout", "-B", branch, f"origin/{branch}"],
                           cwd=self.base_path, capture_output=True)

        # 6c: Reset hard to remote state
        self.log(Fore.YELLOW + f"  → {self.t('update_resetting')}")
        res = subprocess.run(["git", "reset", "--hard", f"origin/{branch}"],
                             cwd=self.base_path, capture_output=True)

        if res.returncode != 0:
            self.log(Fore.RED + self.t('update_error_git'))
            return

        # 7. Track changes for PIP
        diff = subprocess.run(
            ["git", "diff", "--name-only", local_hash, remote_hash],
            cwd=self.base_path, capture_output=True, text=True).stdout.splitlines()

        # 8. Sync PIP requirements & Cleanup
        self.safe_venv_cleanup()
        self._sync_core_requirements()
        self._update_pip_tracking()

        # Dev requirements only if needed
        if "requirements.txt" in diff:
            self.run_with_progress([f"{venv_pip} install -r requirements.txt"], self.t('prog_pip_dev'))

        # Dependencies-Check
        if any('config/' in f for f in diff):
            self.log(f"\n{Fore.CYAN}{self.t('menu_deps')}")
            self.sync_dependencies()

            self.log(f"\n{Fore.GREEN}{self.t('dep_success')}")

        # 9. Check example configs
        self.setup_example_configs()

        # 10. Restart services
        self.save_config()
        self.restart_active_services()
        self.log(f"\n{Fore.GREEN}{Style.BRIGHT}{self.t('update_success')}")

        # 11. Reboot prompt
        self.ask_for_reboot()

    def _sync_core_requirements(self):
        """Synchronisiert Versionen aller bereits installierten Pakete gegen requirements-runtime.txt.
        Neue Pakete werden NUR installiert wenn sie [core] oder [manager] getaggt sind."""
        venv_pip = self.base_path / "venv" / "bin" / "pip"
        tag_mapping = self.parse_requirements_tags()
        installed = self.config.get('installed_packages', {})

        # Alle Pakete aus requirements-runtime.txt mit ihren Versionen
        req_file = self.base_path / "requirements-runtime.txt"
        if not req_file.exists():
            return

        # Vollständige Paketliste aus requirements parsen (Name -> volle Spezifikation)
        all_requirements = {}
        with open(req_file, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                pkg_spec = line.split('#')[0].strip()
                if pkg_spec:
                    # Normalisierter Name als Key, volle Spezifikation als Value
                    pkg_name = pkg_spec.split('==')[0].split('>=')[0].split('~=')[0].lower().replace('-', '_').strip()
                    all_requirements[pkg_name] = pkg_spec

        core_and_manager = set(
            p.split('==')[0].split('>=')[0].lower().replace('-', '_').strip()
            for p in tag_mapping.get('core', []) + tag_mapping.get('manager', [])
        )

        to_sync = []

        for pkg_name, pkg_spec in all_requirements.items():
            if pkg_name in installed:
                # Bereits installiert → immer synchronisieren (up/downgrade)
                to_sync.append(pkg_spec)
            elif pkg_name in core_and_manager:
                # Nicht installiert, aber core/manager → installieren
                to_sync.append(pkg_spec)
            # Sonst: nicht installiert, plugin-spezifisch → überspringen

        if not to_sync:
            self.log(Fore.GREEN + self.t('pip_sync_ok'))
            return

        self.log(Fore.CYAN + f"  → Synchronisiere {len(to_sync)} Pakete...")

        result = subprocess.run(
            [str(venv_pip), "install", "--upgrade"] + to_sync,
            capture_output=True, text=True
        )

        changed = []
        for line in result.stdout.splitlines():
            if line.startswith("Successfully installed"):
                changed = line.replace("Successfully installed", "").strip().split()

        if changed:
            self.log(Fore.GREEN + self.t('pip_sync_updated').format(', '.join(changed)))
        else:
            self.log(Fore.GREEN + self.t('pip_sync_ok'))

        log_file = self.base_path / "log" / "install" / "setup_log.txt"
        with open(log_file, "a") as f:
            f.write(result.stdout)
            if result.stderr:
                f.write(f"STDERR: {result.stderr}")

    # ============== HARDWARE COMPILATION ==============

    def compile_rtlsdr(self, commit):
        """Compiles rtl-sdr with a specific commit."""
        self.log(f"\n{Fore.CYAN}--- {self.t('compiling_sdr')} (Hash: {commit[:7]}) ---")
        cmds = [
            "rm -rf /tmp/librtlsdr",  # Clean start
            "cd /tmp && git clone https://github.com/steve-m/librtlsdr.git",
            f"cd /tmp/librtlsdr && git checkout {commit}",
            "cd /tmp/librtlsdr && mkdir build",
            "cd /tmp/librtlsdr/build && cmake ../ -DINSTALL_UDEV_RULES=ON -DDETACH_KERNEL_DRIVER=ON",
            "cd /tmp/librtlsdr/build && make -j$(nproc)",
            "make install -C /tmp/librtlsdr/build",
            "ldconfig",
            "cp /tmp/librtlsdr/rtl-sdr.rules /etc/udev/rules.d/",
            "rm -rf /tmp/librtlsdr"
        ]
        try:
            self.run_with_progress(cmds, "RTL-SDR")
            return True
        except Exception as e:
            self.log(Fore.RED + self.t('error_compile_sdr').format(e))
            return False

    def compile_multimon(self, branch):
        """Compiles multimon-ng with a specific version."""
        self.log(f"\n{Fore.CYAN}--- {self.t('compiling_multimon')} (Branch: {branch}) ---")
        cmds = [
            "rm -rf /tmp/multimon-ng",
            f"cd /tmp && git clone --branch {branch} "
            f"https://github.com/EliasOenal/multimon-ng.git",
            "cd /tmp/multimon-ng && mkdir build",
            "cd /tmp/multimon-ng/build && cmake ..",
            "cd /tmp/multimon-ng/build && make -j$(nproc)",
            "make install -C /tmp/multimon-ng/build",
            "rm -rf /tmp/multimon-ng"
        ]
        try:
            self.run_with_progress(cmds, "Multimon-NG")
            return True
        except Exception as e:
            self.log(Fore.RED + self.t('error_compile_mm').format(e))
            return False

    # ============== UPDATE RTL_FM und MULTIMON-NG ==============

    def check_and_update_hardware_tools(self):
        """Checks versions and recompiles hardware tools if needed."""
        updated = False

        # RTL-SDR Check
        target_sdr = self.config['rtlsdr_commit']
        if (self.config['installed_rtlsdr'] != target_sdr or
                not os.path.exists("/usr/local/bin/rtl_fm")):
            if self.compile_rtlsdr(target_sdr):
                self.config['installed_rtlsdr'] = target_sdr
                updated = True

        # Multimon-NG Check
        target_mm = self.config['multimon_branch']
        if (self.config['installed_multimon'] != target_mm or
                not os.path.exists("/usr/local/bin/multimon-ng")):
            if self.compile_multimon(target_mm):
                self.config['installed_multimon'] = target_mm
                updated = True

        if updated:
            self.save_config()

    # ============== PIP Versions-Tracking ==============

    def _update_pip_tracking(self):
        """Reads all installed versions and saves them to config."""
        venv_pip = self.base_path / "venv" / "bin" / "pip"
        result = subprocess.run([str(venv_pip), "list", "--format=json"],
                                capture_output=True, text=True)

        self.config['installed_packages'] = {
            pkg['name'].lower().replace('-', '_'): pkg['version']
            for pkg in json.loads(result.stdout)
        }

        self.save_config()
        self.log(Fore.GREEN + self.t('pip_track_success').format(len(self.config['installed_packages'])))

    # ============== REBOOT MENU ==============

    def ask_for_reboot(self):
        """Asks the user for a system reboot (DRY principle)."""
        choice = input(f"\n{Fore.YELLOW}{Style.BRIGHT} {self.t('reboot_ask')}")

        if choice.lower() == 'y':
            self.log(f"\n{Fore.CYAN}{self.t('reboot_now')}")
            time.sleep(2)
            subprocess.run(["shutdown", "-r", "now"])
        else:
            self.log(f"\n{Fore.GREEN}{self.t('reboot_skip')}")

    # ============== SERVICE ==============

    def service_menu(self):
        """Submenu for service management (Pro Version)."""
        # automatic silent dependencies check while enter
        self.sync_dependencies(silent=True)

        while True:
            config_dir = self.base_path / 'config'

            # 1. Scan for YAML files (client/server)
            configs = [
                f for f in config_dir.glob("*.yaml")
                if f.stem.startswith(('client', 'server'))
            ]

            if not configs:
                self.log(Fore.RED + self.t('srv_not_found'))
                return

            self.log(f"\n{Fore.GREEN}=== {self.t('menu_service_manager')} ===")
            self.log(Style.DIM + f"  → {self.t('srv_hint_deps')}")

            # creating overview-screen
            for i, cfg in enumerate(configs):
                service_name = f"bw3_{cfg.stem}.service"
                is_active = subprocess.run(["systemctl", "is-active", "--quiet", service_name]).returncode == 0
                status_text = (Fore.GREEN + self.t('srv_status_running') if is_active else Fore.RED + self.t('srv_status_stopped'))

                # Zeigt: [1] client.yaml - Läuft
                self.log(f"[{i + 1}] {cfg.name} - {status_text}")

            self.log("\n[0] " + self.t('menu_exit'))

            choice = input("\n" + self.t('branch_select_prompt'))

            # input 0 or Enter (empty) = back to main menu
            if choice == "0" or choice.strip() == "":
                break

            # doing for service
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(configs):
                    cfg = configs[idx]
                    service_name = f"bw3_{cfg.stem}.service"

                    if not os.path.exists(f"/etc/systemd/system/{service_name}"):
                        install = input(self.t('srv_ask_install').format(cfg.name))
                        if install.lower() == 'y':
                            self.install_single_service(cfg)
                    else:
                        self.log(self.t('srv_action_options'))
                        action = input(self.t('srv_action_prompt')).lower()
                        if action == 'r':
                            subprocess.run(["systemctl", "restart", service_name])
                            self.log(Fore.GREEN + self.t('srv_restarted').format(service_name))
                        elif action == 'd':
                            self.remove_single_service(service_name)
            except ValueError:
                pass

    def install_single_service(self, config_file):
        """Creates a systemd service file."""
        # Decide which script to start based on filename
        script_name = ("bw_server.py" if "server" in config_file.name.lower()
                       else "bw_client.py")
        service_name = f"bw3_{config_file.stem}.service"

        service_content = f"""[Unit]
Description=BOSWatch3 Service: {config_file.stem}
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory={self.base_path}
ExecStart={self.base_path}/venv/bin/python3 {script_name} -c {config_file.name}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""
        with open(f"/etc/systemd/system/{service_name}", "w") as f:
            f.write(service_content)

        subprocess.run(["systemctl", "daemon-reload"])
        subprocess.run(["systemctl", "enable", service_name])
        subprocess.run(["systemctl", "start", service_name])
        self.log(Fore.GREEN + self.t('srv_install_success').format(service_name))

    def remove_single_service(self, service_name):
        """Stops and deletes a service."""
        subprocess.run(["systemctl", "stop", service_name])
        subprocess.run(["systemctl", "disable", service_name])
        if os.path.exists(f"/etc/systemd/system/{service_name}"):
            os.remove(f"/etc/systemd/system/{service_name}")
        subprocess.run(["systemctl", "daemon-reload"])
        self.log(Fore.YELLOW + self.t('srv_remove_success').format(service_name))

    # ============== DEPENDENCIES INSTALL ==============

    def get_required_packages(self):
        """Scans recursively all config-files for active modules and plugins."""
        active_resources = set()
        config_dir = self.base_path / 'config'

        def extract_resources(data):
            """Helper: Recursively searches lists and dictionaries."""
            if isinstance(data, dict):
                # If it is a plugin or module, save the technical identifier 'res'.
                if data.get('type') in ['plugin', 'module'] and 'res' in data:
                    active_resources.add(data['res'])

                # Recursively continue searching through all values ​​of the dictionary.
                for value in data.values():
                    extract_resources(value)
            elif isinstance(data, list):
                # If it is a list, iterate through every element of the list.
                for item in data:
                    extract_resources(item)

        if not config_dir.exists():
            return active_resources

        # Scan all .yaml files that start with 'client' or 'server'.
        for cfg_path in config_dir.glob("*.yaml"):
            if not cfg_path.stem.startswith(('client', 'server')):
                continue

            try:
                with open(cfg_path, 'r', encoding='utf-8') as f:
                    content = yaml.safe_load(f)
                    if content:
                        # Start recursive search for this file.
                        extract_resources(content)
            except Exception as e:
                self.log(Fore.RED + self.t('dep_config_read_error').format(cfg_path.name, e))

        return active_resources

    def sync_dependencies(self, silent=False):
        """Installs missing dependencies based on config-files."""
        if not silent:
            self.log(f"\n{Fore.CYAN}--- {self.t('dep_checking_header')} ---")

        tag_mapping = self.parse_requirements_tags()
        active_plugins = self.get_required_packages()
        to_install = set()

        # Core/Manager/Overall tags always
        to_install.update(tag_mapping.get('core', []))
        to_install.update(tag_mapping.get('manager', []))
        to_install.update(tag_mapping.get('overall', []))

        # Dot-Recognition Logic (e.g., filter.modeFilter -> matches [modeFilter])
        for plugin in active_plugins:
            p_lower = plugin.lower()
            if p_lower in tag_mapping:
                to_install.update(tag_mapping[p_lower])
            if '.' in p_lower:
                sub = p_lower.split('.')[-1]
                if sub in tag_mapping:
                    to_install.update(tag_mapping[sub])

        # Version-aware missing check
        installed = self.config.get('installed_packages', {})
        missing = []
        for p in to_install:
            # Handle version specifiers: ==, >=, ~=
            p_name = p.split('==')[0].split('>=')[0].split('~=')[0].lower().replace('-', '_').strip()
            installed_ver = installed.get(p_name)

            if installed_ver is None:
                missing.append(p)
            elif '==' in p and installed_ver != p.split('==')[1].strip():
                missing.append(p)
            elif '>=' in p:
                try:
                    if packaging.version.parse(installed_ver) < packaging.version.parse(p.split('>=')[1].strip()):
                        missing.append(p)
                except Exception:
                    missing.append(p)

        # FINAL LOGIC FLOW (The Clean Senior Way)
        if missing:
            self.log(Fore.YELLOW + self.t('dep_installing').format(len(missing)))
            venv_pip = self.base_path / "venv" / "bin" / "pip"

            # Run installation
            self.run_with_progress([f"{venv_pip} install {p}" for p in missing], "PIP Sync")
            self._update_pip_tracking()
            self.log(Fore.GREEN + f"✔ {self.t('dep_success')}")

            # Restart query only if not silent
            if not silent:
                confirm = input("\n" + self.t('dep_ask_restart')).lower()
                if confirm == 'y':
                    self.restart_active_services()
        else:
            # Everything okay
            if not silent:
                self.log(Fore.GREEN + f"✔ {self.t('dep_all_ok')}")

    def parse_requirements_tags(self):
        """Reads requirements-runtime.txt and maps packages to tags with multi-tag [tag1][tag2]"""
        req_file = self.base_path / "requirements-runtime.txt"
        mapping = {'core': [], 'manager': []}

        if not req_file.exists():
            return mapping

        with open(req_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue

                # split packages from comments
                parts = line.split('#', 1)
                package = parts[0].strip()

                if len(parts) > 1:
                    comment = parts[1].lower()
                    # Findet alle [tags] in einer Zeile
                    tags = re.findall(r'\[(.*?)\]', comment)
                    if tags:
                        for tag in tags:
                            tag = tag.strip()
                            if tag not in mapping:
                                mapping[tag] = []
                            mapping[tag].append(package)
                        continue

                # no tags -> standard: core
                mapping['core'].append(package)
        return mapping


if __name__ == "__main__":
    manager = BW3Manager()
    manager.main_menu()
