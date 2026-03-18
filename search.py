import json
import sys


def alfred_json(items):
    print(json.dumps({"items": items}))


def make_item(uid, title, subtitle, arg, variables=None, mods=None):
    item = {"uid": uid, "title": title, "subtitle": subtitle, "arg": arg}
    if variables:
        item["variables"] = variables
    if mods:
        item["mods"] = mods
    return item


LOGIN_ITEM = make_item(
    "unlock", "Log in to Proton Pass",
    "Press Enter to log in via browser", "__unlock__",
    variables={"action": "__unlock__"},
)

try:
    from pass_core import validate, is_logged_in, search, icon_path, fetch_missing_icons
    validate()
except RuntimeError:
    import traceback
    _err = traceback.format_exc().splitlines()[-1]
    alfred_json([make_item("error", "Setup required", _err, "")])
    sys.exit(0)


def run():
    query = sys.argv[1].strip() if len(sys.argv) > 1 else ""

    if not query:
        if not is_logged_in():
            alfred_json([LOGIN_ITEM])
        else:
            alfred_json([
                make_item("placeholder", "Search your vault...",
                          "Type to search", ""),
                make_item("lock", "Log out",
                          "Log out from Proton Pass", "__lock__",
                          variables={"action": "lock"}),
            ])
        return

    entries = search(query)

    if not entries:
        alfred_json([make_item("empty", "No results",
                               f"No items matching '{query[:100]}'", "")])
        return

    items = []
    domains = []
    for entry in entries:
        uid = entry["id"]
        name = entry["name"]
        username = entry["username"]
        url = entry.get("url", "")
        domain = entry.get("domain")
        vault = entry.get("vault", "")

        sub = username or "(no username)"
        if domain:
            sub = f"{sub} – {domain}"
        if vault:
            sub = f"{sub} [{vault}]"

        base_vars = {"item_id": uid, "item_user": username}
        mods = {
            "cmd": {
                "subtitle": f"Copy username: {username}" if username else "No username",
                "variables": {**base_vars, "action": "username"},
            },
            "alt": {
                "subtitle": "Copy TOTP code",
                "variables": {**base_vars, "action": "totp"},
            },
            "ctrl": {
                "subtitle": "Show password (Large Type)",
                "variables": {**base_vars, "action": "largetype"},
            },
        }
        if url:
            mods["shift"] = {
                "subtitle": f"Open {url}",
                "variables": {**base_vars, "action": "open_url", "item_url": url},
            }
        else:
            mods["shift"] = {"subtitle": "No URL available", "valid": False}

        item = make_item(
            uid, name, sub, uid,
            variables={**base_vars, "action": "password"},
            mods=mods,
        )

        cached = icon_path(domain)
        if cached:
            item["icon"] = {"type": "", "path": cached}

        items.append(item)
        if domain:
            domains.append(domain)

    alfred_json(items)
    fetch_missing_icons(domains)


if __name__ == "__main__":
    run()
