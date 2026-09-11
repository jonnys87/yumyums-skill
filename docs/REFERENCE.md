# yumyums-send, the reference

Everything the tool does, flag by flag. The short version is the [README](../README.md).

## Use

```
yumyums-send <url-or-text> [--via messages|telegram|email] [--out path]
```

A recipe link:

```bash
yumyums-send "https://example.com/recipes/butter-bean-stew" --via messages
```

Pasted text, as an argument or on standard input. Use standard input for
anything longer than a line or two:

```bash
pbpaste | yumyums-send - --via telegram
```

Just the file, to deliver however you like:

```bash
yumyums-send "https://example.com/recipes/stew" --out ~/Desktop/
```

A path ending in a slash, or one that is already a folder, means a folder to put
the file in, named the way the app names it, for example
`Butter bean stew.yumyums`.

The rest of the flags:

```
--dry-run    say exactly what would happen, do nothing
--json       report as JSON, for a program reading the output
--title      use this title instead of the one found
--photo      put a local image inside the file
--to         who to send it to, for Messages and for email
```

## The three ways to deliver

Nothing is sent unless you ask for it. With neither `--via` nor `--out` the tool
refuses to run, and there is no built-in recipient of any kind: no number, no
address, no token. Everything comes from your own configuration.

### A file (`--out`)

Always available, nothing to configure. Write the file and AirDrop it, attach
it, drop it in iCloud Drive, whatever suits.

### Messages (`--via messages --to <recipient>`)

A Mac talking to the Messages app over AppleScript, which sends the file to your
phone as an iMessage. Needs macOS, a Mac signed in to iMessage, and a recipient:
a phone number or an Apple account address, either on the command line as `--to`
or in your config as `messages_to`. The first run asks for permission to control
Messages.

### Telegram (`--via telegram`)

Uploads the file to a chat through a bot you made with
[@BotFather](https://t.me/botfather). Needs a bot token and a chat id. Works on
any machine with a network connection, which is the reason it exists.

### Email (`--via email`)

Attaches the file to a mail and sends it, either through an SMTP server you name
or through the machine's own `sendmail` if it has one. Needs a from address and
a to address. Whether the attachment survives to be tappable depends on the mail
client at the other end, so if you have a choice, Messages or Telegram is the
surer route.

## Configuration

Settings come from the environment first, then from
`~/.config/yumyums/config.json`, and there are no defaults. Every setting is
`YUMYUMS_<NAME>` in the environment and `<name>` in the file.

Copy [`config.example.json`](../config.example.json) and keep only the lines you
need:

```bash
mkdir -p ~/.config/yumyums
cp config.example.json ~/.config/yumyums/config.json
chmod 600 ~/.config/yumyums/config.json
```

| Setting | Used by | What it is |
| --- | --- | --- |
| `messages_to` | Messages | Phone number or Apple account address to send to |
| `telegram_token` | Telegram | Bot token from BotFather |
| `telegram_chat_id` | Telegram | The chat to put the file in |
| `email_to` | email | Address to send to |
| `email_from` | email | Address to send from |
| `email_smtp_host` | email | Mail server. Leave it out to use local `sendmail` |
| `email_smtp_port` | email | Defaults to 587, or 465 with `ssl` |
| `email_smtp_security` | email | `starttls` (default), `ssl` or `none` |
| `email_smtp_user` | email | Username, if the server wants one |
| `email_smtp_password` | email | Password or app password |
| `email_sendmail` | email | Path to a `sendmail` binary, if it is somewhere unusual |

`config.json` is in `.gitignore`. Keep it that way. If you can use an app
password rather than your real one, use the app password.

## Privacy

Nothing about a recipe leaves your machine except the two things you asked for:

- The page you gave it is fetched, over HTTPS, by this tool on your machine. The
  site sees a request for the page, which is what happens when you open a link.
- The file goes wherever you pointed it. Messages sends it through Apple, as any
  iMessage goes. Telegram uploads it to Telegram's API. Email hands it to your
  mail server. `--out` sends it nowhere at all.

There is no analytics, no telemetry, no third-party service in the middle, and
no model call. Recipe reading is structured data and plain string handling, done
here. Your configuration is read from your own machine and nothing writes to it.

## How a page is read

If the page carries JSON-LD, which most recipe sites do, the recipe comes out
structured: title, ingredients split into amount, unit and item, steps, times,
servings, tags and the photo link.

If it does not, the tool does not guess. The readable page text goes into the
recipe's notes, the recipe is tagged `AI read`, and the app's own on-device
import reads it, which it is better at than a pile of CSS selectors would be.
Pasted text gets a plain heuristic: first line is the title, a Method or
Instructions heading splits ingredients from steps, and lines with a quantity in
them are the ingredients.

Both of those are marked `"reviewed": false` in the file, and the app's review
screen is where anything wrong gets fixed before it is saved.

## Tests

```bash
python3 -m unittest
```

They cover the JSON-LD path, the page-text fallback, the pasted-text heuristic,
the manifest and recipe keys exactly as the app reads them, the filename rules,
and the promise that nothing is delivered without a delivery method. Set
`YUMYUMS_APP_PATH` to a checkout of the app and one more test joins in,
comparing what this writes against the app's own test fixture.

## Known limits

- Some sites answer a plain HTTP client with a block page rather than the
  recipe. There is no browser here to get past that. Copy the recipe text and
  paste it in instead.
- A page with no JSON-LD arrives as text for the app to read, not as parsed
  ingredients. That is deliberate.
- The photo is normally left as a link for the phone to fetch. `--photo` embeds
  a local image when there is a reason to.
- Messages delivery is macOS only, and needs the Mac awake and signed in.

## Licence

MIT. See [LICENSE](../LICENSE).
