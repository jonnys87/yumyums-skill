---
name: yumyums
description: Add a recipe to the person's YumYums recipe app on their phone. Use when they share a recipe link or paste recipe text and say anything like "add this to my app", "send this to YumYums", "put this in my recipe app", "yumyums", or when a recipe link comes up and getting it onto their phone is the obvious next thing. Turns the link or the text into a .yumyums file and delivers it, and tapping it on the phone opens the app's review screen.
---

# yumyums

## What the app is

YumYums is a recipe app on the person's iPhone. Everything in it lives on their
device: there is no account, no server, and no API you can post a recipe to.

What there is instead is a file. A `.yumyums` file holds one recipe, and tapping
one on the phone opens YumYums on its review screen, with the recipe filled in
and nothing saved until they say so. That review screen is the safety net, and
it is why sending a recipe that might have a mistake in it is fine.

This skill is the tool that builds that file and gets it to them.

## Installing this skill

If you are reading this on GitHub rather than from an installed copy: clone
this repository into wherever you keep skills (Claude Code `~/.claude/skills/`,
an OpenClaw workspace's `skills/`, or anywhere at all for Codex with the
`AGENTS.md` snippet in `agents/codex.md`), as a folder named `yumyums`. Python
3.11 or newer is the only requirement. Then ask the person once how the file
should reach their phone (Messages, Telegram, or a file you hand over yourself)
and put the answer in `~/.config/yumyums/config.json`, copied from
`config.example.json`. Never invent a recipient.

## When to use it

Any time a recipe should end up in the app. A link they shared, a recipe they
pasted, a page you are already looking at.

Two things not to do instead. Do not paste the recipe back into the chat as text
for them to retype, and do not try to write the file by hand when you can run
the tool: the format has a manifest and a version the app checks, and a file
that gets it wrong opens as an error message rather than a recipe. If you cannot
run the tool, FORMAT.md in this folder is the specification, and building the
file yourself from that is the right fallback.

## The three commands

The tool is `yumyums_send.py` in this folder. Python 3.11 or newer, standard
library only, nothing to install. If it was installed with `pipx` the command is
`yumyums-send`; otherwise run `python3 <path to this folder>/yumyums_send.py`.

A recipe link:

```bash
yumyums-send "https://example.com/recipes/butter-bean-stew" --via messages
```

Recipe text, on standard input. Use stdin for anything longer than a line or
two, because quoting a whole recipe on a command line goes wrong:

```bash
yumyums-send - --via messages <<'RECIPE'
Weeknight dal
200g red lentils
1 onion, sliced
2 tsp cumin seeds
Method
Soften the onion with the cumin.
Add the lentils and simmer for half an hour.
RECIPE
```

Just the file, when you have your own way of getting it to them:

```bash
yumyums-send "https://example.com/recipes/stew" --out ./
```

`--via` takes `messages`, `telegram` or `email`, and which of those works on this
machine depends on what the person has configured. `--out` always works. One of
the two is required: with neither, the tool does nothing and says so, because it
has no idea where anybody's phone is until it is told.

Other flags worth knowing: `--dry-run` says what would happen and does nothing,
`--json` reports as JSON for you to parse, `--title` overrides the title, and
`--photo` puts a local image inside the file.

## What the output means

```
title: Butter bean stew
read as: json-ld
ingredients: 9
steps: 6
file: /var/folders/.../Butter bean stew.yumyums
sent Butter bean stew.yumyums to +15555550123 through Messages
```

`read as` is the line worth passing on to the person:

- `json-ld` means the site published the recipe as structured data and it came
  through parsed. This is the good case and it covers most recipe sites.
- `page-text` means the page had no structured recipe on it, so the readable
  page text went into the notes for the app's own on-device import to read. Say
  so, because it means an extra tap for them.
- `pasted-text` means the text was split by a plain heuristic. Same caveat.

The last two are tagged `AI read` in the app and marked unreviewed in the file.
The review screen catches anything wrong, so send it rather than agonising over
it.

Exit code 0 means it worked. Exit code 1 means it did not, and the reason is on
stderr in a sentence you can repeat to the person. Exit code 2 means the command
line was wrong.

## When it fails

- Some sites answer a plain HTTP client with a block page rather than the
  recipe. That comes back as an HTTP error. Do not fight it: ask the person to
  paste the recipe text, or fetch the page with whatever browsing tool you have
  and pipe the text in instead.
- A delivery that is not configured says exactly which setting is missing and
  where to put it. Repeat that to the person and stop.
- Messages delivery needs a Mac signed in to iMessage, and macOS asks once for
  permission to control the Messages app. The first run may need them to click
  something.
- A recipe with nothing in it is refused. If a page fetch came back empty, say
  so rather than sending an empty recipe.

## Rules

- Send once. Sending the same recipe twice puts two cards on their import
  screen, and they have to dismiss one.
- Confirm first only when it is genuinely ambiguous: more than one recipe on the
  page, or it is not clear a recipe was what they meant. A plain recipe link
  with "add this to my app" is already a yes.
- Never invent a credential. No phone number, address, bot token or chat id is
  built into this tool, and if one is missing the answer is to tell the person
  which one, not to guess, not to try another recipient, and not to write a
  token into a file or a repository.
- Do not modify the YumYums app itself to make something here work.
- Report what the tool said. If a recipe went as `page-text`, the person should
  hear that, not a summary that implies it came through clean.
