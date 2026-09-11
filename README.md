# yumyums-skill

Give your AI assistant this page and say:

> Install the yumyums skill.

That is the setup. The assistant reads this page, installs the skill for itself,
asks you once how to reach your phone, and from then on "add this recipe to my
app" does what it says. The recipe arrives on your phone as a small file, you
tap it, YumYums opens it on the review screen with the ingredients, method and
photo filled in, and you save it. Nothing is saved until you have looked at it.

It works with any assistant that can run a command: Claude Code, Codex, OpenClaw
and their like. An assistant that cannot run commands can still write the file,
because the format is documented in [FORMAT.md](FORMAT.md).

## What YumYums is

A recipe app for iPhone and iPad that keeps every recipe on your own device: no
account, no subscription, no server. This skill is the way an assistant puts a
recipe into it. See [the YumYums site](https://jonnys87.github.io/yumyums-site/).

## For the assistant reading this

Four steps, then you are done.

1. Find where you keep skills. Claude Code: `~/.claude/skills/`. OpenClaw: the
   `skills/` folder of your workspace. Codex: clone it anywhere and add the
   snippet in [agents/codex.md](agents/codex.md) to your `AGENTS.md`. Anything
   else: clone it anywhere and read `SKILL.md` whenever a recipe comes up.
2. Clone this repository into that place, as a folder called `yumyums`:

   ```bash
   git clone https://github.com/jonnys87/yumyums-skill.git yumyums
   ```

   It needs Python 3.11 or newer and nothing else. No pip, no build.
3. Ask the person one question: how should the file reach their phone? The
   choices are Messages (a Mac signed in to iMessage, plus their phone number
   or Apple account address), Telegram (a bot token and a chat id), or a file
   you hand over through your own channel. Put the answer in
   `~/.config/yumyums/config.json` (copy `config.example.json`) or in the
   environment. Never invent a recipient: with nothing configured the tool
   refuses and says which setting is missing, and that is the correct
   behaviour.
4. Read [SKILL.md](SKILL.md). Then tell the person to send you a recipe link.

## Doing it by hand

No assistant needed. Clone it and run one command:

```bash
git clone https://github.com/jonnys87/yumyums-skill.git
python3 yumyums-skill/yumyums_send.py "https://example.com/recipes/butter-bean-stew" --out ~/Desktop/
```

Then AirDrop the file to your phone and tap it. Or send it straight there:

```bash
python3 yumyums-skill/yumyums_send.py "https://example.com/recipes/butter-bean-stew" --via messages --to "+15555550123"
```

## Everything else

- [docs/REFERENCE.md](docs/REFERENCE.md): every flag, the three delivery
  methods, the settings, what the tool sends where, tests, known limits.
- [FORMAT.md](FORMAT.md): the `.yumyums` file format, for writing the file
  without this tool.
- [agents/](agents/): notes for Claude Code, OpenClaw, Codex, and assistants
  that cannot run commands.

MIT licence. See [LICENSE](LICENSE).
