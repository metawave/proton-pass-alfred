import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

_CLI_TIMEOUT = 15
_CACHE_DIR = os.path.expanduser("~/.cache/proton-pass-alfred")
ICON_CACHE = os.path.join(_CACHE_DIR, "icons")
_VAULT_CACHE = os.path.join(_CACHE_DIR, "vaults.json")
_VAULT_CACHE_TTL = 300
_SAFE_DOMAIN = re.compile(r'^[a-zA-Z0-9]([a-zA-Z0-9\-.]{0,251}[a-zA-Z0-9])?$')
_WORKFLOW_DIR = os.path.dirname(os.path.abspath(__file__))
_NOTIFIER = shutil.which("terminal-notifier")
_CLI = None


def validate():
    global _CLI
    if _CLI is None:
        _CLI = shutil.which("pass-cli")
        if not _CLI:
            p = os.path.expanduser("~/.local/bin/pass-cli")
            if os.path.isfile(p) and os.access(p, os.X_OK):
                _CLI = p
        if not _CLI:
            raise RuntimeError("pass-cli not found. Install via: brew install protonpass/tap/pass-cli")


def _cli_run(*args):
    try:
        return subprocess.run(
            [_CLI] + list(args),
            capture_output=True, text=True, timeout=_CLI_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, returncode=1, stdout="", stderr="timeout")


def _cli_secret(composite_id, *args):
    share_id, _, item_id = composite_id.partition(":")
    if not share_id or not item_id:
        return None
    r = _cli_run(*args, "--share-id", share_id, "--item-id", item_id)
    return r.stdout.strip() if r.returncode == 0 else None


def unlock():
    return _cli_run("login").returncode == 0


def lock():
    try:
        os.remove(_VAULT_CACHE)
    except OSError:
        pass
    _cli_run("logout")


def is_logged_in():
    return _list_vaults() is not None


def _list_vaults():
    os.makedirs(_CACHE_DIR, exist_ok=True)
    try:
        if time.time() - os.stat(_VAULT_CACHE).st_mtime < _VAULT_CACHE_TTL:
            with open(_VAULT_CACHE) as f:
                return json.load(f)
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    r = _cli_run("vault", "list", "--output", "json")
    if r.returncode != 0:
        return None
    try:
        vaults = json.loads(r.stdout).get("vaults", [])
    except (json.JSONDecodeError, ValueError):
        return None
    try:
        with open(_VAULT_CACHE, "w") as f:
            json.dump(vaults, f)
    except OSError:
        pass
    return vaults


def _extract_domain(uris):
    for uri in (uris or []):
        try:
            host = urlparse(uri).hostname
            if host and _SAFE_DOMAIN.match(host):
                return host
        except Exception:
            continue
    return None


def _parse_entry(entry, vault_name):
    content = entry.get("content", {})
    login = content.get("content", {}).get("Login", {})
    item_id = entry.get("id")
    share_id = entry.get("share_id")
    if not item_id or not share_id:
        return None
    urls = login.get("urls") or []
    return {
        "id": f"{share_id}:{item_id}",
        "name": content.get("title") or "",
        "username": login.get("username") or login.get("email") or "",
        "url": urls[0] if urls else "",
        "domain": _extract_domain(urls),
        "vault": vault_name,
    }


def _fetch_vault_items(vault_name):
    r = _cli_run("item", "list", vault_name, "--filter-type", "login", "--output", "json")
    if r.returncode != 0:
        return []
    try:
        return json.loads(r.stdout).get("items", [])
    except (json.JSONDecodeError, ValueError):
        return []


def search(query):
    vaults = _list_vaults()
    if not vaults:
        return None
    vault_names = [v["name"] for v in vaults if v.get("name")]
    if not vault_names:
        return []
    q = query.lower()
    results = []
    with ThreadPoolExecutor(max_workers=min(len(vault_names), 8)) as pool:
        for vault_name, raw_items in zip(vault_names, pool.map(_fetch_vault_items, vault_names)):
            for entry in raw_items:
                parsed = _parse_entry(entry, vault_name)
                if not parsed:
                    continue
                if q and not any(q in parsed[k].lower() for k in ("name", "username", "url", "vault")):
                    continue
                results.append(parsed)
    return results


def get_password(composite_id):
    return _cli_secret(composite_id, "item", "view", "--field", "password")


def get_totp(composite_id):
    return _cli_secret(composite_id, "item", "totp")


def open_url(url):
    if url and urlparse(url).scheme in {"http", "https"}:
        subprocess.run(["open", url], check=False)
        return True
    return False


def icon_path(domain):
    if not domain:
        return None
    p = os.path.join(ICON_CACHE, f"{domain}.png")
    return p if os.path.isfile(p) else None


def fetch_missing_icons(domains):
    missing = [
        d for d in set(domains)
        if d and not os.path.isfile(os.path.join(ICON_CACHE, f"{d}.png"))
    ]
    if not missing:
        return
    os.makedirs(ICON_CACHE, exist_ok=True)
    script = (
        "import os, sys, urllib.request\n"
        "cache = sys.argv[1]\n"
        "for d in sys.argv[2:]:\n"
        "    p = os.path.join(cache, d + '.png')\n"
        "    if os.path.exists(p):\n"
        "        continue\n"
        "    try:\n"
        "        req = urllib.request.Request(f'https://icons.bitwarden.net/{d}/icon.png',\n"
        "            headers={'User-Agent': 'proton-pass-alfred/1.0'})\n"
        "        resp = urllib.request.urlopen(req, timeout=5)\n"
        "        data = resp.read(262145)\n"
        "        if 501 <= len(data) <= 262144:\n"
        "            with open(p, 'wb') as f:\n"
        "                f.write(data)\n"
        "    except Exception:\n"
        "        pass\n"
    )
    subprocess.Popen(
        [sys.executable, "-c", script, ICON_CACHE] + missing,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, start_new_session=True,
    )


def clipboard_set(text, clear_after=0):
    subprocess.run(["pbcopy"], input=text, text=True, check=True)
    if clear_after > 0:
        digest = hashlib.sha256(text.encode()).hexdigest()
        script = (
            "import subprocess, time, sys, hashlib, os\n"
            "time.sleep(int(sys.argv[1]))\n"
            "digest = sys.stdin.read().strip()\n"
            "r = subprocess.run(['pbpaste'], capture_output=True, text=True)\n"
            "if hashlib.sha256(r.stdout.encode()).hexdigest() == digest:\n"
            "    subprocess.run(['pbcopy'], input='', text=True)\n"
            "    notifier = sys.argv[2] if len(sys.argv) > 2 else ''\n"
            "    msg = 'Clipboard cleared'\n"
            "    title = 'Proton Pass'\n"
            "    if notifier:\n"
            "        icon = sys.argv[3] if len(sys.argv) > 3 else ''\n"
            "        subprocess.run([notifier, '-title', title, '-message', msg,\n"
            "            '-contentImage', icon, '-group', 'proton-pass-alfred',\n"
            "            '-sender', 'com.runningwithcrayons.Alfred'], capture_output=True)\n"
            "    else:\n"
            "        subprocess.run(['osascript', '-e',\n"
            "            'on run argv\\n  display notification (item 1 of argv) with title (item 2 of argv)\\nend run',\n"
            "            msg, title], capture_output=True)\n"
        )
        args = [sys.executable, "-c", script, str(clear_after)]
        if _NOTIFIER:
            args += [_NOTIFIER, os.path.join(_WORKFLOW_DIR, "icon.png")]
        proc = subprocess.Popen(
            args,
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True, text=True,
        )
        proc.stdin.write(digest)
        proc.stdin.close()


def notify(message, title="Proton Pass"):
    if _NOTIFIER:
        icon = os.path.join(_WORKFLOW_DIR, "icon.png")
        subprocess.run(
            [_NOTIFIER, "-title", title, "-message", message,
             "-contentImage", icon, "-group", "proton-pass-alfred",
             "-sender", "com.runningwithcrayons.Alfred"],
            capture_output=True,
        )
    else:
        script = (
            "on run argv\n"
            "  display notification (item 1 of argv) with title (item 2 of argv)\n"
            "end run"
        )
        subprocess.run(["osascript", "-e", script, message, title], capture_output=True)
