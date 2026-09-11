#!/usr/bin/env python3
"""Turn a recipe link or a lump of pasted recipe text into a `.yumyums` file,
and put it somewhere the phone can reach.

    yumyums-send <url-or-text> [--via messages|telegram|email] [--out path]

Tapping the file on the phone opens YumYums on its review screen, where the
person checks the recipe and saves it.

Standard library only, nothing to install. No recipient, address, number, token
or chat id is built in: delivery is whatever the person running it configured,
and with nothing configured the tool writes a file and sends nothing.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import smtplib
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import normalizer
import recipe_file

CONFIG_PATH = Path.home() / ".config" / "yumyums" / "config.json"
TELEGRAM_API = "https://api.telegram.org"
SENDMAIL_CANDIDATES = ("/usr/sbin/sendmail", "/usr/lib/sendmail")

# A .yumyums file is a zip, but the phone works out what it is from the
# extension, and a generic type is what stops a mail client or a bot from
# helpfully renaming it to .zip on the way through.
ATTACHMENT_TYPE = "application/octet-stream"


class SendError(Exception):
    pass


# --- configuration ----------------------------------------------------------

def load_config(path: Path | None = None) -> dict[str, Any]:
    """Whatever is in the config file, or nothing. A missing file is normal."""
    config_path = path or CONFIG_PATH
    try:
        with config_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as error:
        raise SendError(f"The config at {config_path} could not be read: {error}") from error
    return data if isinstance(data, dict) else {}


def setting(name: str, config: dict[str, Any], default: str = "") -> str:
    """The environment wins over the config file, and both over the default."""
    return os.environ.get(f"YUMYUMS_{name.upper()}", "").strip() or str(
        config.get(name.lower(), "") or ""
    ).strip() or default


def missing(what: str, env_names: list[str], config_names: list[str]) -> SendError:
    """One shape of error for every credential that is not there, because the
    answer is always the same: put it in the environment or in the config."""
    return SendError(
        f"{what} is not set. Put it in "
        + " and ".join(f"YUMYUMS_{name.upper()}" for name in env_names)
        + f", or in {CONFIG_PATH} as "
        + " and ".join(config_names)
        + "."
    )


# --- building the recipe ----------------------------------------------------

def is_url(value: str) -> bool:
    return bool(re.match(r"^https?://\S+$", value.strip(), re.IGNORECASE))


def build(source: str, title_override: str = "", timeout: float = 20.0) -> tuple[dict, str]:
    """The recipe and how it was got: json-ld, page-text or pasted-text."""
    if is_url(source):
        try:
            recipe, how = normalizer.recipe_from_url(source.strip(), timeout=timeout)
        except urllib.error.URLError as error:
            raise SendError(f"That page could not be fetched: {error}") from error
    else:
        recipe = normalizer.recipe_from_text(source)
        how = "pasted-text"

    if title_override:
        recipe["title"] = normalizer.normalize_text(title_override)

    # A recipe nobody has read is one the review screen has to be trusted with,
    # so it carries the app's own flag for exactly that, which shows up in the
    # library beside the AI imports it belongs with.
    if how != "json-ld":
        tags = list(recipe.get("tags") or [])
        if not any(tag.lower() == recipe_file.AI_READ_TAG.lower() for tag in tags):
            tags.append(recipe_file.AI_READ_TAG)
        recipe["tags"] = tags

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    recipe.setdefault("id", str(uuid.uuid4()))
    recipe["created_at"] = stamp
    recipe["updated_at"] = stamp
    return recipe, how


def write_file(recipe: dict, how: str, photo: bytes | None = None) -> bytes:
    return recipe_file.make(
        recipe,
        photo=photo,
        extras={"extraction": how, "reviewed": how == "json-ld"},
    )


# --- delivery: Messages -----------------------------------------------------

def messages_script(path: Path, to: str) -> str:
    """The AppleScript that hands the file to Messages.

    Sent to a person rather than to a conversation, because a conversation may
    not exist yet and a phone number or Apple account always does.
    """
    quoted_path = str(path).replace("\\", "\\\\").replace('"', '\\"')
    quoted_to = to.replace("\\", "\\\\").replace('"', '\\"')
    # Messages answers to both "service" and "account" for the same thing
    # depending on the version, and the wrong one is a runtime error rather than
    # a compile one, so it asks for each in turn.
    return (
        'tell application "Messages"\n'
        "    set targetService to missing value\n"
        "    try\n"
        "        set targetService to 1st service whose service type = iMessage\n"
        "    end try\n"
        "    if targetService is missing value then\n"
        "        set targetService to 1st account whose service type = iMessage\n"
        "    end if\n"
        f'    set targetBuddy to participant "{quoted_to}" of targetService\n'
        f'    send POSIX file "{quoted_path}" to targetBuddy\n'
        "end tell\n"
    )


def check_script(script: str) -> None:
    """Compiles the AppleScript without running it, so a typo fails here."""
    with tempfile.TemporaryDirectory() as folder:
        compiled = Path(folder) / "check.scpt"
        result = subprocess.run(
            ["osacompile", "-o", str(compiled), "-e", script],
            capture_output=True,
            text=True,
        )
    if result.returncode != 0:
        raise SendError(f"The AppleScript would not compile: {result.stderr.strip()}")


def send_via_messages(path: Path, config: dict[str, Any], to: str, dry_run: bool) -> str:
    recipient = to or setting("messages_to", config)
    if not recipient:
        raise missing(
            "A Messages recipient (a phone number or an Apple account address)",
            ["messages_to"],
            ["messages_to"],
        )
    if sys.platform != "darwin":
        raise SendError(
            "Messages delivery is a Mac talking to the Messages app, and this is "
            "not a Mac. Use --via telegram, --via email, or --out."
        )
    script = messages_script(path, recipient)
    check_script(script)
    if dry_run:
        return f"would send {path.name} to {recipient} through Messages"
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if result.returncode != 0:
        raise SendError(f"Messages refused it: {result.stderr.strip()}")
    return f"sent {path.name} to {recipient} through Messages"


# --- delivery: Telegram -----------------------------------------------------

def telegram_request(token: str, chat_id: str, path: Path, caption: str) -> urllib.request.Request:
    boundary = "----yumyums" + uuid.uuid4().hex
    mime = mimetypes.guess_type(path.name)[0] or ATTACHMENT_TYPE
    body = bytearray()

    def field(name: str, value: str) -> None:
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        body.extend(f"{value}\r\n".encode())

    field("chat_id", chat_id)
    if caption:
        field("caption", caption)
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(
        f'Content-Disposition: form-data; name="document"; filename="{path.name}"\r\n'.encode()
    )
    body.extend(f"Content-Type: {mime}\r\n\r\n".encode())
    body.extend(path.read_bytes())
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())

    return urllib.request.Request(
        f"{TELEGRAM_API}/bot{token}/sendDocument",
        data=bytes(body),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )


def send_via_telegram(path: Path, config: dict[str, Any], caption: str, dry_run: bool) -> str:
    token = setting("telegram_token", config)
    chat_id = setting("telegram_chat_id", config)
    if not token or not chat_id:
        raise missing(
            "Telegram needs a bot token and a chat id, and at least one of them",
            ["telegram_token", "telegram_chat_id"],
            ["telegram_token", "telegram_chat_id"],
        )
    request = telegram_request(token, chat_id, path, caption)
    if dry_run:
        return (
            f"would POST {path.name} ({path.stat().st_size} bytes) to "
            f"{TELEGRAM_API}/bot<token>/sendDocument for chat {chat_id}"
        )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            answer = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:400]
        raise SendError(f"Telegram refused it ({error.code}): {detail}") from error
    except urllib.error.URLError as error:
        raise SendError(f"Telegram could not be reached: {error}") from error
    if not answer.get("ok"):
        raise SendError(f"Telegram refused it: {answer}")
    return f"sent {path.name} to Telegram chat {chat_id}"


# --- delivery: email --------------------------------------------------------

def email_message(path: Path, sender: str, recipient: str, title: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = title or "A recipe for YumYums"
    message.set_content(
        f"{title or 'A recipe'} for YumYums.\n\n"
        "Open the attachment on the phone and the app's review screen opens with "
        "it, where it can be checked and saved.\n"
    )
    maintype, _, subtype = ATTACHMENT_TYPE.partition("/")
    message.add_attachment(
        path.read_bytes(), maintype=maintype, subtype=subtype, filename=path.name
    )
    return message


def sendmail_binary(config: dict[str, Any]) -> str:
    configured = setting("email_sendmail", config)
    if configured:
        return configured
    for candidate in SENDMAIL_CANDIDATES:
        if os.path.exists(candidate):
            return candidate
    return ""


def send_via_smtp(message: EmailMessage, config: dict[str, Any], host: str) -> None:
    port = int(setting("email_smtp_port", config, "0") or 0)
    security = setting("email_smtp_security", config, "starttls").lower()
    user = setting("email_smtp_user", config)
    password = setting("email_smtp_password", config)
    if security not in {"starttls", "ssl", "none"}:
        raise SendError("email_smtp_security has to be starttls, ssl or none")
    try:
        if security == "ssl":
            server = smtplib.SMTP_SSL(host, port or 465, timeout=30)
        else:
            server = smtplib.SMTP(host, port or 587, timeout=30)
        with server:
            if security == "starttls":
                server.starttls()
            if user:
                server.login(user, password)
            server.send_message(message)
    except (smtplib.SMTPException, OSError) as error:
        raise SendError(f"The mail server refused it: {error}") from error


def send_via_email(path: Path, config: dict[str, Any], to: str, title: str, dry_run: bool) -> str:
    recipient = to or setting("email_to", config)
    if not recipient:
        raise missing("An email recipient", ["email_to"], ["email_to"])
    sender = setting("email_from", config)
    if not sender:
        raise missing("An email sender address", ["email_from"], ["email_from"])

    host = setting("email_smtp_host", config)
    binary = "" if host else sendmail_binary(config)
    if not host and not binary:
        raise SendError(
            "Email needs either a mail server or a local sendmail. Set "
            f"YUMYUMS_EMAIL_SMTP_HOST, or email_smtp_host in {CONFIG_PATH}, or "
            "point email_sendmail at a sendmail binary."
        )

    how = f"the mail server at {host}" if host else binary
    if dry_run:
        return f"would email {path.name} from {sender} to {recipient} through {how}"

    message = email_message(path, sender, recipient, title)
    if host:
        send_via_smtp(message, config, host)
    else:
        result = subprocess.run(
            [binary, "-i", "-f", sender, recipient],
            input=message.as_bytes(),
            capture_output=True,
        )
        if result.returncode != 0:
            raise SendError(
                f"{binary} refused it: {result.stderr.decode('utf-8', errors='replace').strip()}"
            )
    return f"emailed {path.name} to {recipient} through {how}"


# --- command line -----------------------------------------------------------

def read_source(value: str) -> str:
    if value == "-":
        return sys.stdin.read()
    return value


def summary(recipe: dict, how: str, path: Path) -> str:
    lines = [
        f"title: {recipe['title']}",
        f"read as: {how}",
        f"ingredients: {len(recipe.get('ingredients') or [])}",
        f"steps: {len(recipe.get('steps') or [])}",
        f"file: {path}",
    ]
    if how == "page-text":
        lines.append(
            "note: that page had no structured recipe on it, so the readable page "
            "text is in the notes for the app's own import to read"
        )
    return "\n".join(lines)


def place(data: bytes, out: str | None, title: str) -> tuple[Path, bool]:
    """Where the file goes: the asked-for path, or a temporary folder.

    A path ending in a separator, or one that is already a folder, means a
    folder to put it in, with the file named the way the app names it, rather
    than a file called "out".
    """
    if out:
        wants_folder = out.endswith(("/", os.sep))
        path = Path(out).expanduser()
        if wants_folder or path.is_dir():
            path.mkdir(parents=True, exist_ok=True)
            path = path / recipe_file.filename(title)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path, False

    folder = Path(tempfile.mkdtemp(prefix="yumyums-send-"))
    path = folder / recipe_file.filename(title)
    path.write_bytes(data)
    return path, True


def deliver(
    via: str, path: Path, config: dict[str, Any], to: str, title: str, dry_run: bool
) -> str:
    if via == "messages":
        return send_via_messages(path, config, to, dry_run)
    if via == "telegram":
        return send_via_telegram(path, config, title, dry_run)
    if via == "email":
        return send_via_email(path, config, to, title, dry_run)
    raise SendError(f"There is no delivery called {via}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="yumyums-send",
        description="Turn a recipe link or pasted recipe text into a .yumyums file "
        "the YumYums app can open.",
    )
    parser.add_argument("source", help="a recipe URL, the recipe text itself, or - for stdin")
    parser.add_argument(
        "--via", choices=["messages", "telegram", "email"], help="how to deliver it"
    )
    parser.add_argument("--out", help="where to write the file, instead of or as well as sending")
    parser.add_argument("--photo", help="a picture to put inside the file")
    parser.add_argument("--title", default="", help="a title to use instead of the one found")
    parser.add_argument(
        "--to", default="", help="who to send it to, for Messages and for email"
    )
    parser.add_argument("--dry-run", action="store_true", help="say what would happen, do nothing")
    parser.add_argument("--json", action="store_true", help="report as JSON, for another program")
    arguments = parser.parse_args(argv)

    # Nothing is ever sent by accident, and nothing is ever sent anywhere this
    # machine was not told about: without --via or --out there is no destination
    # and no default to fall back on.
    if not arguments.via and not arguments.out:
        parser.error(
            "give it --out to write the file, or --via messages, --via telegram or "
            "--via email to deliver it"
        )

    try:
        config = load_config()
        recipe, how = build(read_source(arguments.source), title_override=arguments.title)

        photo = None
        if arguments.photo:
            photo = Path(arguments.photo).expanduser().read_bytes()

        data = write_file(recipe, how, photo=photo)
        path, temporary = place(data, arguments.out, recipe["title"])

        report = []
        if arguments.via:
            report.append(
                deliver(
                    arguments.via, path, config, arguments.to, recipe["title"], arguments.dry_run
                )
            )

        if arguments.json:
            print(
                json.dumps(
                    {
                        "title": recipe["title"],
                        "extraction": how,
                        "reviewed": how == "json-ld",
                        "ingredients": len(recipe.get("ingredients") or []),
                        "steps": len(recipe.get("steps") or []),
                        "file": str(path),
                        "temporary": temporary,
                        "delivery": arguments.via or "none",
                        "dry_run": arguments.dry_run,
                        "report": report,
                    },
                    indent=2,
                )
            )
        else:
            print(summary(recipe, how, path))
            for line in report:
                print(line)
    except (SendError, recipe_file.RecipeFileError, ValueError, OSError) as error:
        print(f"yumyums-send: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
