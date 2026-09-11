# OpenClaw

OpenClaw keeps skills in its workspace, one folder per skill, each with a
`SKILL.md` at its root and its scripts alongside:

```
<workspace>/skills/<name>/SKILL.md
<workspace>/skills/<name>/scripts/...
```

This repository is already that shape, with the scripts at the top level rather
than in `scripts/`, so it can be dropped in whole:

```bash
git clone https://github.com/jonnys87/yumyums-skill.git
cp -R yumyums-skill <workspace>/skills/yumyums
```

The agent picks it up from the frontmatter description the next time it looks at
its skills.

Two things worth setting up while you are there:

- Give the agent a delivery method once, in the environment it runs in or in
  `~/.config/yumyums/config.json` for the user it runs as. Telegram is usually
  the right one for an agent on a machine that is not the Mac you are sitting
  at.
- If the agent already talks to you over a channel of its own, `--out` and its
  own channel is simpler than configuring a second one. The file is the same
  either way.
