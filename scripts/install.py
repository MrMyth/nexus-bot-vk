# scripts/install.py
# Dependency installer for Nexus Bot

import subprocess
import sys
import os
import time

def run_command(command, description):
    """Executes command and streams output in real-time."""
    print(f"\n[WAIT] {description}...")
    try:
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace'
        )

        while True:
            line = process.stdout.readline()
            if not line and process.poll() is not None:
                break
            if line:
                stripped = line.strip()
                if "Requirement already satisfied" in stripped:
                    continue
                print(f"  {stripped}")

        return_code = process.poll()
        if return_code == 0:
            print(f"[OK] Success: {description}")
            return True
        else:
            print(f"[ERROR] Failed (code {return_code}): {description}")
            return False
    except Exception as e:
        print(f"[CRITICAL] Execution error for '{command}': {e}")
        return False

def main():
    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(scripts_dir)
    os.chdir(project_root)

    os.system('cls' if os.name == 'nt' else 'clear')

    print("=" * 60)
    print("Installing dependencies for Nexus Bot")
    print("=" * 60)

    # 1. Check Python version
    print(f"Python version: {sys.version.split()[0]}")
    if sys.version_info < (3, 8):
        print("[ERROR] Python 3.8 or higher is required!")
        input("\nPress Enter to exit...")
        sys.exit(1)

    # 2. Check and install/update pip
    pip_ok = False
    try:
        import pip
        pip_ok = True
    except ImportError:
        pass

    if not pip_ok:
        print("\n[INFO] pip not found. Attempting automatic pip installation...")
        import urllib.request
        get_pip_url = "https://bootstrap.pypa.io/get-pip.py"
        get_pip_path = os.path.join(project_root, "get-pip.py")
        try:
            urllib.request.urlretrieve(get_pip_url, get_pip_path)
            cmd = f"{sys.executable} {get_pip_path} --break-system-packages"
            res = run_command(cmd, "Installing pip via get-pip.py (--break-system-packages)")
            if not res:
                cmd_no_break = f"{sys.executable} {get_pip_path}"
                run_command(cmd_no_break, "Installing pip via get-pip.py")
            if os.path.exists(get_pip_path):
                os.remove(get_pip_path)
        except Exception as e:
            print(f"[ERROR] Failed to install pip: {e}")

    cmd_upgrade_break = f"{sys.executable} -m pip install -q --upgrade pip --break-system-packages"
    if not run_command(cmd_upgrade_break, "Upgrading pip (--break-system-packages)"):
        cmd_upgrade = f"{sys.executable} -m pip install -q --upgrade pip"
        run_command(cmd_upgrade, "Upgrading pip")

    # 3. Create folders
    print("\n[INFO] Checking required directories...")
    folders_to_create = [
        "data",
        os.path.join("data", "json"),
        os.path.join("data", "json", "caches"),
        os.path.join("data", "json", "system_configs"),
        os.path.join("data", "logs"),
        os.path.join("data", "temp"),
        os.path.join("data", "downloads"),
    ]
    for folder in folders_to_create:
        folder_path = os.path.join(project_root, folder)
        if not os.path.exists(folder_path):
            os.makedirs(folder_path, exist_ok=True)
            print(f"  + Created directory: {folder}")
        else:
            print(f"  . Directory already exists: {folder}")

    # 4. Check .env
    env_file = os.path.join(project_root, ".env")
    env_example = os.path.join(project_root, ".env.example")
    if not os.path.exists(env_file):
        print("\n[WARNING] .env file not found!")
        if os.path.exists(env_example):
            try:
                import shutil
                shutil.copyfile(env_example, env_file)
                print("[OK] Created .env from .env.example. PLEASE CONFIGURE IT!")
            except Exception as e:
                print(f"[ERROR] Failed to copy .env.example: {e}")
        else:
            print("[INFO] .env.example not found, cannot create .env automatically.")

    # 5. Install requirements.txt
    req_file = os.path.join(project_root, "requirements.txt")
    if os.path.exists(req_file):
        cmd_req_break = f"{sys.executable} -m pip install -r {req_file} --break-system-packages"
        if not run_command(cmd_req_break, "Installing packages from requirements.txt (--break-system-packages)"):
            cmd_req = f"{sys.executable} -m pip install -r {req_file}"
            run_command(cmd_req, "Installing packages from requirements.txt")
    else:
        print(f"[WARNING] File {req_file} not found! Skipping.")

    print("\n" + "=" * 60)
    print("INSTALLATION COMPLETED SUCCESSFULLY!")
    print("You can now configure .env and launch the bot via start.py")
    print("=" * 60)

    try:
        choice = input("\nWould you like to start the bot (start.py) now? (y/n) [n]: ").strip().lower()
        if choice in ['y', 'yes']:
            print("\n[INFO] Starting bot (start.py)...")
            start_script = os.path.join(project_root, "start.py")
            if os.path.exists(start_script):
                if os.name == 'nt':
                    subprocess.Popen([sys.executable, start_script], creationflags=subprocess.CREATE_NEW_CONSOLE)
                else:
                    subprocess.Popen([sys.executable, start_script])
                time.sleep(1)
            else:
                print(f"[ERROR] File {start_script} not found!")
                input("\nPress Enter to exit...")
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"[ERROR] Failed to launch start.py: {e}")
        input("\nPress Enter to exit...")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[STOP] Installation cancelled by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\n\n[FATAL] Unexpected error: {e}")
        input("\nPress Enter to exit...")
        sys.exit(1)
