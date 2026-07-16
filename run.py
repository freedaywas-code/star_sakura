#!/usr/bin/env python
import argparse
import os
import subprocess
import sys
import time
import webbrowser
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib import error, request
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


def start_process(command, cwd=None, env=None):
    print("+ " + " ".join(str(part) for part in command))
    return subprocess.Popen([str(part) for part in command], cwd=cwd, env=env)


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
    run_command([venv_python(), "manage.py", "seed_initial_artworks"], cwd=BACKEND, env=env)
    run_command([venv_python(), "manage.py", "seed_initial_inspirations"], cwd=BACKEND, env=env)
    run_command([venv_python(), "manage.py", "seed_commission_options"], cwd=BACKEND, env=env)


def serve_frontend(host, port, backend_port):
    class FrontendHandler(SimpleHTTPRequestHandler):
        def proxy_backend(self):
            target = f"http://127.0.0.1:{backend_port}{self.path}"
            body = None
            if self.command in {"POST", "PUT", "PATCH"}:
                length = int(self.headers.get("Content-Length", "0") or "0")
                body = self.rfile.read(length) if length else None
            headers = {
                key: value
                for key, value in self.headers.items()
                if key.lower() not in {"host", "content-length", "connection", "accept-encoding"}
            }
            backend_request = request.Request(target, data=body, headers=headers, method=self.command)
            try:
                with request.urlopen(backend_request, timeout=30) as response:
                    payload = response.read()
                    self.send_response(response.status)
                    for key, value in response.headers.items():
                        if key.lower() not in {"transfer-encoding", "connection", "content-encoding"}:
                            self.send_header(key, value)
                    self.end_headers()
                    self.wfile.write(payload)
            except error.HTTPError as exc:
                payload = exc.read()
                self.send_response(exc.code)
                for key, value in exc.headers.items():
                    if key.lower() not in {"transfer-encoding", "connection", "content-encoding"}:
                        self.send_header(key, value)
                self.end_headers()
                self.wfile.write(payload)
            except Exception as exc:
                payload = f'{{"code":502,"message":"Backend proxy failed: {exc}","data":null}}'.encode("utf-8")
                self.send_response(502)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        def do_GET(self):
            if self.path.startswith(("/api/", "/media/")):
                return self.proxy_backend()
            return super().do_GET()

        def do_POST(self):
            if self.path.startswith(("/api/", "/media/")):
                return self.proxy_backend()
            return self.send_error(405)

        def do_PUT(self):
            if self.path.startswith(("/api/", "/media/")):
                return self.proxy_backend()
            return self.send_error(405)

        def do_PATCH(self):
            if self.path.startswith(("/api/", "/media/")):
                return self.proxy_backend()
            return self.send_error(405)

        def do_DELETE(self):
            if self.path.startswith(("/api/", "/media/")):
                return self.proxy_backend()
            return self.send_error(405)

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


def backend_health_url(port):
    return f"http://127.0.0.1:{port}/api/health/"


def wait_for_backend(port, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with request.urlopen(backend_health_url(port), timeout=2) as response:
                if response.status == 200:
                    print(f"Backend health: ok ({backend_health_url(port)})")
                    return True
        except Exception:
            time.sleep(1)
    print(f"Backend health: not ready after {timeout}s ({backend_health_url(port)})")
    return False


def stop_process(process):
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def supervise_backend(command, cwd, env, max_restarts):
    restarts = 0
    while True:
        process = start_process(command, cwd=cwd, env=env)
        try:
            exit_code = process.wait()
        except KeyboardInterrupt:
            stop_process(process)
            raise
        if exit_code == 0:
            return 0
        if restarts >= max_restarts:
            print(f"Backend stopped with code {exit_code}; restart limit reached.")
            return exit_code
        restarts += 1
        delay = min(2 * restarts, 10)
        print(f"Backend stopped with code {exit_code}; restarting in {delay}s ({restarts}/{max_restarts})...")
        time.sleep(delay)


def main():
    parser = argparse.ArgumentParser(description="Run Star Sakura in a portable local environment.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--backend-port", type=int, default=8000)
    parser.add_argument("--frontend-port", type=int, default=5173)
    parser.add_argument("--skip-install", action="store_true", help="Skip pip install when dependencies are ready.")
    parser.add_argument("--no-frontend", action="store_true", help="Run backend only.")
    parser.add_argument("--no-browser", action="store_true", help="Do not open the frontend page automatically.")
    parser.add_argument("--backend-restarts", type=int, default=3, help="Restart backend this many times if it exits unexpectedly.")
    args = parser.parse_args()

    if sys.version_info < (3, 10):
        raise SystemExit("Python 3.10 or newer is required.")

    ensure_venv(args.skip_install)
    env = load_env_file(BACKEND / ".env")
    env.setdefault("DJANGO_SETTINGS_MODULE", "configs.settings.dev")

    prepare_database(env)

    backend_command = [venv_python(), "manage.py", "runserver", f"{args.host}:{args.backend_port}"]
    backend_process = start_process(backend_command, cwd=BACKEND, env=env)
    wait_for_backend(args.backend_port)

    if not args.no_frontend:
        thread = Thread(target=serve_frontend, args=(args.host, args.frontend_port, args.backend_port), daemon=True)
        thread.start()
        if not args.no_browser:
            open_browser(f"http://{args.host}:{args.frontend_port}")

    print(f"Backend:  http://{args.host}:{args.backend_port}")
    try:
        exit_code = backend_process.wait()
        if exit_code != 0:
            print(f"Backend stopped with code {exit_code}; entering supervised restart mode.")
            exit_code = supervise_backend(backend_command, BACKEND, env, args.backend_restarts)
        raise SystemExit(exit_code)
    except KeyboardInterrupt:
        stop_process(backend_process)
        raise SystemExit(0)


if __name__ == "__main__":
    main()
