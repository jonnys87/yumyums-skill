# Codex

Codex reads `AGENTS.md` from the repository you are working in, and from
`~/.codex/AGENTS.md` for everything. Point it at the skill rather than
duplicating it, so there is one copy to keep current.

Clone the repository somewhere it will stay:

```bash
git clone https://github.com/jonnys87/yumyums-skill.git ~/code/yumyums-skill
```

Then add this to your `AGENTS.md`:

```markdown
## Recipes

When I share a recipe link or paste recipe text and ask for it in my app,
in YumYums, or on my phone, read ~/code/yumyums-skill/SKILL.md and follow it.
The tool is ~/code/yumyums-skill/yumyums_send.py, Python 3.11 or newer,
standard library only. Do not write the .yumyums file by hand while the
tool is available. Never invent a phone number, address or token: if a
delivery method is not configured, tell me which setting is missing.
```

Adjust the path if you cloned it elsewhere. If you ran `pipx install .` you can
say the command is `yumyums-send` instead of naming the script.
