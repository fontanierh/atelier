"""Run the cooked WebGPU scene in an owned Chrome session under normal guards."""

import argparse
import os
from pathlib import Path
import queue
import shutil
import signal
import subprocess
import sys
import threading
import time

from atelier.build import Context
from atelier.harness.safety import guarded
from atelier.harness.safety.process import spawn


def chrome_binary():
    explicit = os.environ.get("CHROME")
    if explicit:
        return Path(explicit)
    app = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    if app.is_file():
        return app
    found = shutil.which("google-chrome") or shutil.which("chromium")
    if found:
        return Path(found)
    raise RuntimeError("Install Chrome or set CHROME to its executable")


def package_page(root):
    pages = list(root.glob("*/Binaries/HTML5/Yorimichi.html"))
    if len(pages) != 1 or not (root / "HTML5Content.txt").is_file():
        raise RuntimeError(
            "Build the complete browser archive: atelier build yorimichi browser.package"
        )
    if (
        not pages[0].with_suffix(".wasm").is_file()
        or not pages[0].with_suffix(".js").is_file()
    ):
        raise RuntimeError(
            "The browser archive lacks its Wasm module or loader; rebuild browser.package"
        )
    return pages[0].relative_to(root).as_posix()


def stop(child, *, interrupt=False):
    if child is None or child.poll() is not None:
        return
    child.send_signal(signal.SIGINT if interrupt else signal.SIGTERM)
    try:
        child.wait(10)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait(5)


def owned(options):
    root = options.package.resolve()
    page = package_page(root)
    ready = queue.Queue()
    gateway = browser = None
    with (
        (options.run / "gateway.log").open("w") as gateway_log,
        (options.run / "chrome.log").open("w") as chrome_log,
    ):
        try:
            gateway = spawn(
                [
                    str(root / "html5-gateway"),
                    "--directory",
                    str(root),
                    "--bind",
                    "127.0.0.1",
                    "--port",
                    str(options.port),
                    "--no-open",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )

            def read_gateway():
                for line in gateway.stdout:
                    gateway_log.write(line)
                    gateway_log.flush()
                    if line.startswith("HTML5_HOST_URL="):
                        ready.put(line.strip().split("=", 1)[1])

            threading.Thread(target=read_gateway, daemon=True).start()
            try:
                url = ready.get(timeout=10) + page
            except queue.Empty:
                raise RuntimeError(
                    "Browser asset host did not become ready within 10 seconds"
                )
            print("Yorimichi WebGPU: " + url, flush=True)
            command = [
                str(chrome_binary()),
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-background-mode",
                "--user-data-dir=" + str(options.profile.resolve()),
                "--app=" + url,
            ]
            if options.headless:
                command += ["--headless=new", "--window-size=1280,720"]
            browser = spawn(
                command, kind="game", stdout=chrome_log, stderr=subprocess.STDOUT
            )
            started = last = time.monotonic()
            while (
                browser.poll() is None and time.monotonic() - started < options.seconds
            ):
                if gateway.poll() is not None:
                    raise RuntimeError(
                        "The browser asset host stopped; see gateway.log"
                    )
                if time.monotonic() - last >= 25:
                    print(
                        f"Browser session active, {time.monotonic() - started:.0f}s; "
                        "asset host running. Gameplay progress is not measured by this heartbeat.",
                        flush=True,
                    )
                    last = time.monotonic()
                time.sleep(0.5)
            if browser.poll() is not None:
                if time.monotonic() - started < 2:
                    raise RuntimeError(
                        "Chrome exited during startup; close another preview using this profile and inspect chrome.log"
                    )
                return browser.returncode
            print(
                "Browser session reached its duration; closing owned Chrome and asset host.",
                flush=True,
            )
            return 0
        finally:
            stop(browser)
            stop(gateway, interrupt=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--package", type=Path)
    parser.add_argument("--profile", type=Path)
    parser.add_argument(
        "--port",
        type=int,
        default=8840,
        help="Stable loopback origin for saved settings; 0 is temporary",
    )
    parser.add_argument("--seconds", type=float, default=3 * 3600)
    parser.add_argument("--memory-gib", type=float, default=10)
    parser.add_argument(
        "--headless", action="store_true", help="Explicit browser smoke diagnostic"
    )
    parser.add_argument("--owned", action="store_true", help=argparse.SUPPRESS)
    options = parser.parse_args()
    if not 0 <= options.port <= 65535:
        parser.error("--port must be from 0 to 65535")
    if not 1 <= options.seconds <= 6 * 3600:
        parser.error("--seconds must be from 1 to 21600")
    ctx = Context("yorimichi")
    options.run = options.run.resolve()
    options.run.mkdir(parents=True, exist_ok=True)
    options.package = options.package or ctx.out / "browser/package/HTML5"
    options.profile = options.profile or ctx.out / "browser/chrome-profile"
    package_page(options.package)
    if options.owned:
        return owned(options)
    # A separate Chrome profile keeps the actual browser process in this job's
    # owned tree; ordinary browser windows are not controlled or terminated.
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--owned",
        "--run",
        str(options.run),
        "--package",
        str(options.package),
        "--profile",
        str(options.profile),
        "--port",
        str(options.port),
        "--seconds",
        str(options.seconds),
    ]
    if options.headless:
        command.append("--headless")
    return guarded.run(
        command,
        options.run / "guard",
        purpose="yorimichi WebGPU browser",
        kind="game",
        env=ctx.env(),
        limit_gib=options.memory_gib,
        aggregate_tree=True,
        track_tree=True,
        timeout=options.seconds + 45,
        progress=25,
    )


if __name__ == "__main__":
    raise SystemExit(main())
