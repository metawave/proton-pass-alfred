import os

from pass_core import (
    clipboard_set, get_password, get_totp, lock, notify, open_url, unlock,
)


def run():
    action = os.environ.get("action", "")
    item_id = os.environ.get("item_id", "")
    item_user = os.environ.get("item_user", "")

    if action == "__unlock__":
        notify("Logged in" if unlock() else "Login failed")
        return

    if action == "lock":
        lock()
        notify("Logged out")
        return

    if not item_id:
        notify("No item selected")
        return

    if action == "password":
        pw = get_password(item_id)
        if pw:
            clipboard_set(pw, clear_after=30)
            notify("Password copied (clears in 30s)")
        else:
            notify("Could not get password")

    elif action == "username":
        if item_user:
            clipboard_set(item_user)
            notify("Username copied")
        else:
            notify("No username available")

    elif action == "totp":
        code = get_totp(item_id)
        if code:
            clipboard_set(code, clear_after=30)
            notify("TOTP copied (clears in 30s)")
        else:
            notify("Could not get TOTP")

    elif action == "open_url":
        url = os.environ.get("item_url", "")
        if not open_url(url):
            notify("Blocked: only http/https URLs" if url else "No URL available")

    elif action == "largetype":
        pw = get_password(item_id)
        if pw:
            print(pw)
        else:
            notify("Could not get password")

    else:
        notify(f"Unknown action: {action}")


if __name__ == "__main__":
    run()
