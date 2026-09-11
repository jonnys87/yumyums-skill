# The `.yumyums` file format

Version 1.

A `.yumyums` file is one recipe in one file. Tapping it on a phone that has
YumYums opens the app on its review screen, with the recipe filled in and
nothing saved until the person says so.

The format is a zip. Anything that can write a zip and some JSON can write one,
which is the point of this document: an agent that cannot run the Python tool in
this repository can still produce a file the app will open, in whatever language
it has to hand.

Everything below is what the app's reader actually does, not a wish list. Where
the reader is lenient, this says so, and where it refuses, it says what the
person sees.

## The zip

| | |
| --- | --- |
| Extension | `.yumyums` |
| Container | zip |
| Entries | `manifest.json` (required), `recipe.json` (required), `photo.<ext>` (optional) |
| Compression | stored or deflate |
| Maximum size | 12 MiB for the whole file |

The rules, in full:

- Entries sit at the root of the archive. A name with a `/` in it is not read.
- Compression method 0 (stored) and method 8 (deflate) are both read. Anything
  else fails with a message about a compression the app cannot read. Stored is
  what the app itself writes and what this tool writes.
- Zip64, spanned archives and encrypted entries are not supported.
- Entry order does not matter. The reader indexes the central directory and
  sorts by name.
- Directory entries (names ending in `/`) are skipped.
- 12 MiB is checked against the file on disk before anything is decompressed, so
  a small file that inflates to a large one is refused rather than read.
- Extra entries the app does not know about are ignored rather than rejected.

## manifest.json

```json
{
  "app_version": "yumyums-send 1.0.0",
  "created_at": "2026-09-12T09:41:00Z",
  "format": "yumyums-recipe",
  "photo": "photo.jpg",
  "title": "Butter bean stew",
  "version": 1
}
```

| Field | Type | Required | What it means |
| --- | --- | --- | --- |
| `format` | string | yes | Exactly `yumyums-recipe`. Anything else, and the file is not a recipe file as far as the app is concerned. |
| `version` | integer | yes in practice | The format version, currently `1`. A version higher than the app knows is refused with "update the app and open it again" rather than "damaged", because that is something the person can act on. A missing version is tolerated, but write it. |
| `app_version` | string | no | Whoever wrote the file, for a bug report. Put your own tool's name and version here. |
| `created_at` | string | no | ISO 8601, UTC, for example `2026-09-12T09:41:00Z`. Informational. |
| `title` | string | no | The recipe title again, so a reader can label the file without opening `recipe.json`. |
| `photo` | string | no | The name of the photo entry, when there is one. |

Two conventions this tool writes, which the app ignores and other tools are
welcome to copy:

| Field | Type | What it means |
| --- | --- | --- |
| `extraction` | string | How the recipe was read: `json-ld`, `page-text` or `pasted-text`. |
| `reviewed` | boolean | `false` when no person or structured source has vouched for the contents. |

Unknown manifest fields are ignored, so adding your own is safe.

One thing to know: the `photo` field is a label, not a lookup. The app finds the
image by scanning the archive for an entry whose name starts with `photo.`, so a
manifest that names a photo entry that is not there gets a recipe with no
picture rather than an error.

## recipe.json

```json
{
  "cook_time": "1 hr 10 min",
  "created_at": "2026-09-12T09:41:00Z",
  "id": "8B1E7A6C-1C1B-4F5E-9C3E-2D2E4A5B6C7D",
  "image_url": "https://example.com/images/stew.jpg",
  "ingredients": [
    { "amount": "2", "unit": "tbsp", "item": "olive oil" },
    { "amount": "400", "unit": "g", "item": "butter beans, drained" },
    { "amount": "", "unit": "pinch", "item": "saffron" }
  ],
  "notes": "",
  "prep_time": "15 min",
  "servings": "4",
  "source_url": "https://example.com/recipes/stew",
  "steps": [
    "Warm the oil in a wide pan.",
    "Add the beans and simmer for forty minutes."
  ],
  "tags": ["vegetarian", "one pot"],
  "title": "Butter bean stew",
  "total_time": "1 hr 25 min",
  "updated_at": "2026-09-12T09:41:00Z"
}
```

The keys are snake case. Every field is optional to the decoder, which fills in
an empty string or an empty list for anything missing, but write them all: a
file that carries every key is one you can read back and reason about.

| Field | Type | What it means |
| --- | --- | --- |
| `id` | string | A UUID string. Generate one per recipe. If it is missing the app makes one up, which is fine but makes the file harder to talk about. |
| `title` | string | The recipe name. |
| `source_url` | string | Where the recipe came from, as an http or https URL, or empty. |
| `image_url` | string | An absolute http or https URL to a photo, or empty. See the note below. |
| `servings` | string | Free text, for example `4` or `4 to 6` or `Makes 12`. A string, not a number. |
| `prep_time` | string | Free text, for example `15 min`. Not an ISO 8601 duration: convert `PT15M` into something a person reads. |
| `cook_time` | string | As above. |
| `total_time` | string | As above. |
| `ingredients` | array of objects | Each one `{"amount": "", "unit": "", "item": ""}`, all three strings, all three required in the object. Split what you can and leave the rest in `item`: `Salt and pepper` as an item with no amount and no unit is correct, not a failure. |
| `steps` | array of strings | One step per entry, in order, with no leading numbers. |
| `tags` | array of strings | Free text tags. |
| `notes` | string | Anything that is not a step. This is also where unparsed page text goes, see below. |
| `created_at` | string | ISO 8601, UTC. A string, and the app keeps it as one. |
| `updated_at` | string | As above. |

Two fields exist in the app's model and must not be written into a file:

- `last_cooked_at`: when the person last cooked it. That belongs to their
  device, and a file asserting it is a file telling them something about their
  own kitchen that it cannot know.
- `sample`: marks the recipes the app ships with. A file claiming to be one of
  those is lying.

The app reads both if they are there, which is exactly why a writer should leave
them out.

`image_url` has one trap in it. Inside the app the same field holds either an
absolute http or https URL, or a bare filename for a photo stored on that
device. A bare filename means nothing on anybody else's phone, so a file must
carry either an absolute URL or an empty string. If you have the actual image
bytes, embed them as the photo entry instead.

### What counts as a recipe

The file is refused as "there is no recipe inside it" unless at least one of
these is true:

- `title` is present in the JSON and is not blank once trimmed
- `ingredients` has at least one entry
- `steps` has at least one entry

The title half of that test is made against the JSON as written rather than
against the decoded recipe, because the decoder stands in `Untitled recipe` for
a missing title and an empty object should not arrive looking like a real
recipe with nothing in it.

### The "AI read" convention

A recipe that a model read off a page or a piece of pasted text, rather than one
lifted from a site's structured data, should carry the tag `AI read` in `tags`.
The app matches it without regard to case, shows it wherever tags are shown, and
uses it to mark the imports worth a second look. It is a tag rather than a field
so that it survives the format unchanged.

If you produce a recipe by reading prose, add the tag. It costs nothing and it
is honest.

## The photo entry

Optional. One entry, holding the image bytes.

- The name must start with `photo.` and be a single path component: no `/` and
  no `\`, not `.`, not `..`, and not starting with a dot. A name with a path in
  it is ignored, because an archive entry that writes itself somewhere other
  than where it was asked to is the oldest trick there is.
- The entry must not be empty.
- The bytes are sniffed and the extension is not trusted, so only these five
  types are worth embedding. At least 12 bytes are needed to sniff at all.

| Type | Name to use | How it is recognised |
| --- | --- | --- |
| JPEG | `photo.jpg` | first two bytes `FF D8` |
| PNG | `photo.png` | first four bytes `89 50 4E 47` |
| GIF | `photo.gif` | first three bytes `47 49 46` |
| WebP | `photo.webp` | bytes 0 to 4 are `RIFF` and bytes 8 to 12 are `WEBP` |
| HEIC | `photo.heic` | bytes 4 to 8 are `ftyp` |

Use the extension that matches the bytes anyway. Somebody will unzip the file
one day and should find a picture they can open.

Keep images to about 8 MB. That is the largest single image the app will store,
and the whole file still has to come in under 12 MiB. If the photo is already on
the web, leave it out and put the URL in `image_url`: the phone will fetch it,
and the file stays small enough to send over anything.

## The filename

The file should be named after the recipe. The app builds the name like this,
and a file that arrives named the same way looks like one the app sent:

1. Every run of whitespace, including newlines and tabs, becomes a single space.
2. Control characters are removed.
3. `/ \ : * ? " < > |` are replaced with spaces.
4. Runs of spaces collapse to one.
5. The result is cut to 60 characters, then trimmed.
6. Leading dots and spaces are removed, repeatedly, so a title that was a path
   cannot become a hidden file.
7. If nothing is left, the name is `Recipe`.
8. `.yumyums` goes on the end.

So `Butter bean stew` becomes `Butter bean stew.yumyums`, and `../../etc/passwd`
becomes `etc passwd.yumyums`.

## Versioning

Version 1 is the only version. The rules a future version will keep:

- A reader refuses a file whose `version` is higher than it knows, and says so
  in a way that points at updating the app.
- Unknown fields, in the manifest and in the recipe, are ignored rather than
  rejected. Additive change is the safe kind.
- `format` stays `yumyums-recipe`.

Write `"version": 1` and do not invent a higher one to signal a feature. A file
that claims version 2 is refused by every app in the field today.

## Building one without this tool

Two JSON files and a zip. Here it is as shell, using nothing but `zip`:

```bash
mkdir -p /tmp/stew && cd /tmp/stew

cat > manifest.json <<'JSON'
{
  "app_version": "my-agent 1.0",
  "created_at": "2026-09-12T09:41:00Z",
  "format": "yumyums-recipe",
  "title": "Butter bean stew",
  "version": 1
}
JSON

cat > recipe.json <<'JSON'
{
  "id": "8B1E7A6C-1C1B-4F5E-9C3E-2D2E4A5B6C7D",
  "title": "Butter bean stew",
  "source_url": "https://example.com/recipes/stew",
  "image_url": "",
  "servings": "4",
  "prep_time": "15 min",
  "cook_time": "1 hr 10 min",
  "total_time": "1 hr 25 min",
  "ingredients": [
    { "amount": "2", "unit": "tbsp", "item": "olive oil" },
    { "amount": "400", "unit": "g", "item": "butter beans, drained" }
  ],
  "steps": [
    "Warm the oil in a wide pan.",
    "Add the beans and simmer for forty minutes."
  ],
  "tags": ["AI read"],
  "notes": "",
  "created_at": "2026-09-12T09:41:00Z",
  "updated_at": "2026-09-12T09:41:00Z"
}
JSON

zip -q -X -0 "Butter bean stew.yumyums" manifest.json recipe.json
```

`-X` leaves out the extra attributes that only mean something on the machine
that wrote them, and `-0` stores rather than deflates. Neither is required, both
are tidy. Add the photo by putting `photo.jpg` in the folder and naming it in
the `zip` line and in the manifest.

The same thing in Node, standard library only, is not short: Node has no zip
writer built in. With a zip library (`archiver`, `jszip`, `yazl`, any of them):

```js
const JSZip = require("jszip");
const fs = require("fs");

const zip = new JSZip();
zip.file("manifest.json", JSON.stringify(manifest, null, 2));
zip.file("recipe.json", JSON.stringify(recipe, null, 2));
// zip.file("photo.jpg", photoBytes);

zip.generateNodeStream({ type: "nodebuffer", compression: "STORE" })
   .pipe(fs.createWriteStream("Butter bean stew.yumyums"));
```

## Checking one

Unzip it and look. `manifest.json` and `recipe.json` should be at the root, the
manifest should say `yumyums-recipe` and `1`, and the recipe should have a title
or an ingredient or a step in it.

```bash
unzip -l "Butter bean stew.yumyums"
unzip -p "Butter bean stew.yumyums" manifest.json
unzip -p "Butter bean stew.yumyums" recipe.json | python3 -m json.tool
```

The real test is the phone: send the file to it and tap it. A file the app will
not open says so on screen, in a sentence that tells you which of the rules
above it broke.
