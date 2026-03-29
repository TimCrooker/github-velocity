#!/usr/bin/env python3
"""
GitHub Delivery Velocity Report — Single-command runner.

Collects GitHub data, computes metrics, assembles the report,
and opens it in a browser. Just run it.

Usage:
    python3 run.py                        # full report for authenticated user
    python3 run.py --fast                 # skip repo stats (2-3 min instead of 5-10)
    python3 run.py --username octocat     # report for a different user
    python3 run.py --output ./my-report   # custom output directory
    python3 run.py --no-open              # don't auto-open browser
    python3 run.py --collect-only         # just collect data, don't analyze or serve
"""

import argparse
import http.server
import json
import os
import shutil
import socketserver
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent / "scripts"
TEMPLATE_DIR = Path(__file__).parent / "template"


def run_step(description, cmd, timeout=600):
    """Run a subprocess step with error handling."""
    print(f"\n{'='*60}")
    print(f"  {description}")
    print(f"{'='*60}\n")
    result = subprocess.run(cmd, timeout=timeout)
    if result.returncode != 0:
        print(f"\nERROR: {description} failed (exit code {result.returncode})", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Generate a GitHub Delivery Velocity Report",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Run with no arguments for a full report of the authenticated GitHub user.",
    )
    parser.add_argument("--username", help="GitHub username (default: auto-detect from gh auth)")
    parser.add_argument("--fast", action="store_true", help="Skip repo stats for faster collection")
    parser.add_argument("--output", default=os.path.expanduser("~/Desktop/velocity-report"),
                        help="Report output directory (default: ~/Desktop/velocity-report)")
    parser.add_argument("--port", type=int, default=8080, help="HTTP server port (default: 8080)")
    parser.add_argument("--no-open", action="store_true", help="Don't auto-open browser")
    parser.add_argument("--collect-only", action="store_true", help="Only collect data, skip analysis and report")
    parser.add_argument("--data-dir", default="./gh_dump", help="Data directory (default: ./gh_dump)")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    output_dir = Path(args.output)

    # ── Step 1: Collect data ──────────────────────────────────
    collect_cmd = [sys.executable, str(SCRIPT_DIR / "01_collect_data.py"), "--output", str(data_dir)]
    if args.username:
        collect_cmd += ["--username", args.username]
    if args.fast:
        collect_cmd.append("--fast")

    run_step("Collecting GitHub data", collect_cmd)

    if args.collect_only:
        print(f"\nData collected to {data_dir}/")
        return

    # ── Step 2: Analyze ───────────────────────────────────────
    insights_path = data_dir / "insights.json"
    run_step(
        "Computing metrics",
        [sys.executable, str(SCRIPT_DIR / "02_analyze.py"),
         "--input", str(data_dir), "--output", str(insights_path)]
    )

    # ── Step 3: Check for narratives ──────────────────────────
    narratives_path = data_dir / "narratives.json"
    if not narratives_path.exists():
        # Create minimal narratives so the report renders
        print("\nNote: No narratives.json found. The report will use auto-generated fallback text.")
        print("For richer storytelling, generate narratives.json with an LLM (see SKILL.md).\n")
        with open(narratives_path, "w") as f:
            json.dump({}, f)

    # ── Step 4: Assemble report ───────────────────────────────
    print(f"\n{'='*60}")
    print(f"  Assembling report")
    print(f"{'='*60}\n")

    output_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(TEMPLATE_DIR / "velocity.html", output_dir / "index.html")
    shutil.copy2(insights_path, output_dir / "insights.json")
    shutil.copy2(narratives_path, output_dir / "narratives.json")
    print(f"  Report assembled in {output_dir}/")

    # ── Step 5: Serve ─────────────────────────────────────────
    os.chdir(output_dir)

    # Check if port is available
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    port_available = sock.connect_ex(("localhost", args.port)) != 0
    sock.close()

    if not port_available:
        print(f"\n  Port {args.port} is in use. Trying {args.port + 1}...")
        args.port += 1

    handler = http.server.SimpleHTTPRequestHandler
    handler.log_message = lambda *a: None  # Suppress request logging

    httpd = socketserver.TCPServer(("", args.port), handler)
    url = f"http://localhost:{args.port}"

    print(f"\n{'='*60}")
    print(f"  Report ready at {url}")
    print(f"  Press Ctrl+C to stop the server")
    print(f"{'='*60}\n")

    if not args.no_open:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        httpd.shutdown()


if __name__ == "__main__":
    main()
