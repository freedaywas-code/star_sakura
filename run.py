#!/usr/bin/env python
import argparse
import os
import subprocess
import sys
import time
import webbrowser
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from threading import Thread


ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
VENV = ROOT / ".venv"


def venv_python():
    if os.name == "nt":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def run_command(command, cwd=None, env=None):
    print("+ " + " ".join(str(part) for part in command))
    subprocess.check_call([str(part) for part in command], cwd=cwd, env=env)


def load_env_file(path):
    env = os.environ.copy()
    if not path.exists():
        return env
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    return env


def ensure_venv(skip_install):
    if not venv_python().exists():
        run_command([sys.executable, "-m", "venv", VENV])
    if not skip_install:
        run_command([venv_python(), "-m", "pip", "install", "--upgrade", "pip"])
        run_command([venv_python(), "-m", "pip", "install", "-r", BACKEND / "requirements.txt"])


def prepare_database(env):
    run_command([venv_python(), "manage.py", "makemigrations"], cwd=BACKEND, env=env)
    run_command([venv_python(), "manage.py", "migrate"], cwd=BACKEND, env=env)
    run_command([venv_python(), "manage.py", "ensure_default_admin"], cwd=BACKEND, env=env)


def serve_frontend(host, port):
    class FrontendHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(FRONTEND), **kwargs)

    server = ThreadingHTTPServer((host, port), FrontendHandler)
    print(f"Frontend: http://{host}:{port}")
    server.serve_forever()


def open_browser(url):
    def _open():
        time.sleep(1.2)
        try:
            webbrowser.open(url)
        except Exception as exc:
            print(f"Could not open browser automatically: {exc}")

    Thread(target=_open, daemon=True).start()


def main():
    parser = argparse.ArgumentParser(description="Run Star Sakura in a portable local environment.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--backend-port", type=int, default=8000)
    parser.add_argument("--frontend-port", type=int, default=5173)
    parser.add_argument("--skip-install", action="store_true", help="Skip pip install when dependencies are ready.")
    parser.add_argument("--no-frontend", action="store_true", help="Run backend only.")
    parser.add_argument("--no-browser", action="store_true", help="Do not open the frontend page automatically.")
    args = parser.parse_args()

    if sys.version_info < (3, 10):
        raise SystemExit("Python 3.10 or newer is required.")

    ensure_venv(args.skip_install)
    env = load_env_file(BACKEND / ".env")
    env.setdefault("DJANGO_SETTINGS_MODULE", "configs.settings.dev")

    prepare_database(env)

    if not args.no_frontend:
        thread = Thread(target=serve_frontend, args=(args.host, args.frontend_port), daemon=True)
        thread.start()
        if not args.no_browser:
            open_browser(f"http://{args.host}:{args.frontend_port}")

    print(f"Backend:  http://{args.host}:{args.backend_port}")
    run_command(
        [venv_python(), "manage.py", "runserver", f"{args.host}:{args.backend_port}"],
        cwd=BACKEND,
        env=env,
    )


if __name__ == "__main__":
    main()
