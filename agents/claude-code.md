# Claude Code

Claude Code reads skills from `~/.claude/skills/<name>/SKILL.md` for every
project, or from `.claude/skills/<name>/SKILL.md` inside one project.

`SKILL.md` sits at the root of this repository with the scripts beside it, so
the whole folder is the skill. Copy it:

```bash
git clone https://github.com/jonnys87/yumyums-skill.git
cp -R yumyums-skill ~/.claude/skills/yumyums
```

Or symlink it, so a `git pull` updates the skill:

```bash
git clone https://github.com/jonnys87/yumyums-skill.git ~/code/yumyums-skill
ln -s ~/code/yumyums-skill ~/.claude/skills/yumyums
```

Restart Claude Code, or start a new session, and ask it to add a recipe to your
app. It will find the skill from the description and run the script in place.

Two notes:

- The skill runs `python3 .../yumyums_send.py`. If you also ran `pipx install .`
  the shorter `yumyums-send` works, but neither is required by the other.
- Configure a delivery method first, as the README describes, or the first run
  will tell you which setting is missing. That is the tool working correctly,
  not failing.
