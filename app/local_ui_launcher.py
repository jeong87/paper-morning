import argparse
import logging
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

import web_app


def is_port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


def pick_port(host: str, requested_port: int, max_tries: int = 20) -> int:
    for port in range(requested_port, requested_port + max_tries):
        if is_port_available(host, port):
            return port
    raise RuntimeError(
        f"Could not find an available port in range {requested_port}-{requested_port + max_tries - 1}."
    )


def wait_until_port_ready(host: str, port: int, timeout_seconds: float) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def open_browser_when_ready(host: str, port: int, delay_seconds: float = 15.0) -> None:
    if wait_until_port_ready(host, port, delay_seconds):
        url = f"http://{host}:{port}"
        webbrowser.open(url, new=2)
    else:
        logging.warning("Server did not open in time. Open browser manually.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="One-click local launcher for Paper Digest web console."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5050)
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not auto-open browser.",
    )
    return parser.parse_args()


def switch_workdir_to_executable_dir() -> None:
    if getattr(sys, "frozen", False):
        base_dir = Path(sys.executable).resolve().parent
    else:
        # Source-tree run: use repository root, not app/ subdir.
        base_dir = Path(__file__).resolve().parent.parent
    os.chdir(base_dir)


def main() -> int:
    switch_workdir_to_executable_dir()
    web_app.setup_logging()
    web_app.ensure_bootstrap_files()
    args = parse_args()
    try:
        web_app.ensure_host_security(args.host, web_app.read_env_map())
    except Exception as exc:
        logging.error(str(exc))
        return 1
    selected_port = pick_port(args.host, args.port)
    if selected_port != args.port:
        logging.warning(
            "Requested port %d is already in use. Using port %d instead.",
            args.port,
            selected_port,
        )

    try:
        info = web_app.refresh_scheduler()
        logging.info(info)
    except Exception as exc:
        logging.warning("Scheduler initialization skipped: %s", exc)

    if not args.no_browser:
        threading.Thread(
            target=open_browser_when_ready,
            args=(args.host, selected_port),
            daemon=True,
        ).start()

    logging.info("Launching local UI at http://%s:%d", args.host, selected_port)
    web_app.app.run(host=args.host, port=selected_port, debug=False, use_reloader=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
