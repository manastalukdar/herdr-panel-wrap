#!/usr/bin/env python3
"""Install files-wrap and changes-wrap and point the current layout's Files and
Changes panels at them.

  python3 scripts/install.py              install
  python3 scripts/install.py --update     copy the mods over an earlier install
  python3 scripts/install.py --uninstall  point layouts back at files/changes, remove the mods
  add --dry-run to any of them to see what would change

Herdr's own layouts (main, terminals, ...) are replaced on every start, so one of
those is cloned first as <name>-wrap (and switched to). A layout of your own is
edited in place, after a backup in data/panel-wrap/.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SWAP = {"files": "files-wrap", "changes": "changes-wrap"}
GENERATED = ("gpui-kit.d.ts", "herdr.d.ts", "jsconfig.json")


def herdr(*args):
    r = subprocess.run(["herdr-app", *args], capture_output=True, text=True, timeout=30)
    if r.returncode:
        sys.exit(f"herdr-app {' '.join(args)} failed:\n{r.stdout}{r.stderr}")
    return r.stdout


def blocks(node, names):
    """Every layout block whose content.mod is in names."""
    if isinstance(node, dict):
        if node.get("type") == "block" and node.get("content", {}).get("mod") in names:
            yield node
        for v in node.values():
            yield from blocks(v, names)
    elif isinstance(node, list):
        for v in node:
            yield from blocks(v, names)


def repoint(path, mapping, dry):
    tree = json.loads(path.read_text())
    hits = list(blocks(tree, set(mapping)))
    for b in hits:
        b["content"]["mod"] = mapping[b["content"]["mod"]]
    if hits and not dry:
        path.write_text(json.dumps(tree, indent=2) + "\n")
    return len(hits)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true")
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    home = Path(os.environ.get("HERDR_APP_HOME", Path.home() / ".config/herdr-app"))
    if not (home / "layouts").is_dir():
        sys.exit(f"No Herdr app home at {home}. Start Herdr app once, or set HERDR_APP_HOME.")
    shipped = set(json.loads((home / "installed.json").read_text())) if (home / "installed.json").exists() else set()
    dry = "(dry run) " if a.dry_run else ""

    if a.uninstall:
        back = {v: k for k, v in SWAP.items()}
        for f in sorted((home / "layouts").glob("*.json")):
            if f"layout:{f.stem}" not in shipped and (n := repoint(f, back, a.dry_run)):
                print(f"{dry}{f.name}: {n} panel(s) back on files/changes")
        for m in SWAP.values():
            if (home / "mods" / m).exists():
                print(f"{dry}remove mods/{m}")
                if not a.dry_run:
                    shutil.rmtree(home / "mods" / m)
        print("A layout the installer cloned (<name>-wrap) is left in place: delete it if you don't want it.")
        return

    for m in SWAP.values():
        dest = home / "mods" / m
        if dest.exists() and not a.update:
            sys.exit(f"mods/{m} already exists. Use --update to copy over it.")
        herdr("check", str(REPO / "mods" / m))
    for m in SWAP.values():
        dest = home / "mods" / m
        print(f"{dry}copy mods/{m}")
        if not a.dry_run:
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(REPO / "mods" / m, dest, ignore=shutil.ignore_patterns(*GENERATED))
            herdr("check", str(dest))
    if a.update:
        print("Updated.")
        return

    try:
        layout = json.loads((home / "shared.json").read_text()).get("layout") or "main"
    except (OSError, ValueError):
        layout = "main"
    path = home / "layouts" / f"{layout}.json"
    if not path.exists():
        sys.exit(f"Can't find the current layout ({path}). Point a block's \"mod\" at files-wrap or changes-wrap by hand.")
    if not any(blocks(json.loads(path.read_text()), set(SWAP))):
        print(f"Layout '{layout}' has no files or changes panel. Point a block's \"mod\" at files-wrap or changes-wrap by hand.")
        return
    if f"layout:{layout}" in shipped:
        clone = f"{layout}-wrap"
        if (home / "layouts" / f"{clone}.json").exists():
            sys.exit(f"layouts/{clone}.json already exists. Switch to it, or delete it and run again.")
        print(f"{dry}'{layout}' is Herdr's own: clone it as '{clone}' and switch to it")
        if a.dry_run:
            return
        herdr("do", "layout.clone", json.dumps({"name": layout, "as": clone}))
        path = home / "layouts" / f"{clone}.json"
    elif not a.dry_run:
        backup = home / "data/panel-wrap" / f"{layout}.{time.strftime('%Y%m%d-%H%M%S')}.json"
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup)
        print(f"backed up {path.name} to {backup}")
    n = repoint(path, SWAP, a.dry_run)
    print(f"{dry}{path.name}: {n} panel(s) now on files-wrap/changes-wrap")


if __name__ == "__main__":
    main()
