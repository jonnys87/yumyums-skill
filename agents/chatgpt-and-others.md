# ChatGPT, and any assistant that cannot run a command

An assistant with no shell cannot run this tool. It can still get a recipe into
the app, two ways.

## Build the file itself

[FORMAT.md](../FORMAT.md) is the whole specification: a zip holding
`manifest.json` and `recipe.json`, with an optional photo. Any assistant that
can produce a file for you to download can produce a `.yumyums` file, and the
worked example in FORMAT.md is short enough to paste into a prompt.

Something like this works as an instruction:

> Read https://github.com/jonnys87/yumyums-skill/blob/master/FORMAT.md and give
> me this recipe as a .yumyums file I can download.

Then get the file to your phone however you already move files, and tap it. If
the assistant read the recipe off a page or out of prose rather than from a
site's structured data, ask it to put `AI read` in the recipe's tags. That is
the convention, and the app uses it to mark the imports worth a second look.

## Ask for the one command

If you have a terminal, the shortest path is to have the assistant write the
command and run it yourself:

```bash
yumyums-send "<the recipe link>" --via messages --to "<your number>"
```

or, with nothing configured at all:

```bash
yumyums-send "<the recipe link>" --out ~/Desktop/
```

and then send yourself the file from the desktop.

## What not to accept

An assistant that offers to email the recipe to you, or to post it to a YumYums
account, is making something up. There is no account and no server: the app
holds everything on your phone. A file is the only way in, which is why the
format is documented rather than hidden.
