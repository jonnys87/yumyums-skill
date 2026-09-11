"""Recipe reading and normalising, standard library only.

The normalising and JSON-LD reading here follow what YumYums does on the device,
so a recipe read on this side arrives in the shape the app would have given it
anyway. The code is copied rather than shared, which is what keeps this tool a
single folder with nothing to install.

A page with no JSON-LD on it is handed over as page text, ingredients and steps
left to the app's own on-device import, rather than guessed at with CSS
selectors that rot within a season.
"""

from __future__ import annotations

import gzip
import io
import json
import re
import ssl
import subprocess
import urllib.error
import urllib.request
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123 Safari/537.36"
)

UNIT_WORDS = {
    "cup", "cups", "tbsp", "tablespoon", "tablespoons", "tsp", "teaspoon",
    "teaspoons", "g", "kg", "mg", "ml", "l", "oz", "lb", "lbs", "pound",
    "pounds", "pinch", "pinches", "dash", "dashes", "handful", "handfuls",
    "sprig", "sprigs", "clove", "cloves", "tin", "tins", "can", "cans",
    "packet", "packets", "jar", "jars", "slice", "slices", "bunch", "bunches",
    "piece", "pieces", "stalk", "stalks", "head", "heads", "fillet", "fillets",
}

UNICODE_FRACTIONS = {
    "¼": "1/4", "½": "1/2", "¾": "3/4", "⅐": "1/7",
    "⅑": "1/9", "⅒": "1/10", "⅓": "1/3", "⅔": "2/3",
    "⅕": "1/5", "⅖": "2/5", "⅗": "3/5", "⅘": "4/5",
    "⅙": "1/6", "⅚": "5/6", "⅛": "1/8", "⅜": "3/8",
    "⅝": "5/8", "⅞": "7/8",
}

METHOD_HEADINGS = re.compile(
    r"^(method|instructions?|steps?|directions?|preparation|to cook|how to make.*)\s*:?\s*$",
    re.IGNORECASE,
)
INGREDIENT_HEADINGS = re.compile(
    r"^(ingredients?|you will need|shopping list)\s*:?\s*$", re.IGNORECASE
)


# --- vendored normalising ---------------------------------------------------

def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    for char, replacement in UNICODE_FRACTIONS.items():
        text = text.replace(char, replacement)
    text = text.replace("\u00a0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_tags(raw_tags: list[str] | str | None) -> list[str]:
    if raw_tags is None:
        return []
    if isinstance(raw_tags, str):
        pieces = re.split(r",|\n", raw_tags)
    else:
        pieces = []
        for tag in raw_tags:
            if isinstance(tag, str):
                pieces.extend(re.split(r",|\n", tag))
    cleaned: list[str] = []
    seen: set[str] = set()
    for piece in pieces:
        tag = normalize_text(piece)
        if not tag:
            continue
        key = tag.lower()
        if key not in seen:
            seen.add(key)
            cleaned.append(tag)
    return cleaned


def parse_ingredient_text(text: str) -> dict[str, str]:
    raw = normalize_text(text)
    raw = re.sub(r"^[•\-*]\s*", "", raw)
    if not raw:
        return {"amount": "", "unit": "", "item": ""}

    attached = re.match(
        r"^(?P<amount>\d+(?:\.\d+)?)(?P<unit>g|kg|mg|ml|l|oz|lb|lbs|tsp|tbsp)\s+(?P<item>.+)$",
        raw,
        re.IGNORECASE,
    )
    if attached:
        return {
            "amount": normalize_text(attached.group("amount")),
            "unit": normalize_text(attached.group("unit")),
            "item": normalize_text(attached.group("item")),
        }

    quantity_match = re.match(
        r"^(?P<amount>(?:\d+\s+\d/\d|\d+/\d|\d+(?:\.\d+)?|a|an))"
        r"(?:\s*[-–]\s*(?P<range_end>\d+(?:\.\d+)?))?\s+(?P<rest>.+)$",
        raw,
        re.IGNORECASE,
    )
    if quantity_match:
        amount = normalize_text(quantity_match.group("amount"))
        if quantity_match.group("range_end"):
            amount = f"{amount}-{normalize_text(quantity_match.group('range_end'))}"
        rest = normalize_text(quantity_match.group("rest"))
        parts = rest.split(" ")
        unit = ""
        item = rest
        if parts:
            candidate = parts[0].lower().rstrip(".,")
            if candidate in UNIT_WORDS:
                unit = normalize_text(parts[0]).rstrip(".,")
                item = " ".join(parts[1:])
        item = re.sub(r"^of\s+", "", item, flags=re.IGNORECASE)
        return {"amount": amount, "unit": unit, "item": normalize_text(item)}

    special_unit = re.match(
        r"^(?P<unit>pinch|dash|handful|sprig|sprigs)\s+of\s+(?P<item>.+)$", raw, re.IGNORECASE
    )
    if special_unit:
        return {
            "amount": "",
            "unit": normalize_text(special_unit.group("unit")),
            "item": normalize_text(special_unit.group("item")),
        }

    return {"amount": "", "unit": "", "item": raw}


def normalize_ingredient(payload: dict[str, Any] | str) -> dict[str, str]:
    if isinstance(payload, str):
        return parse_ingredient_text(payload)

    amount = normalize_text(payload.get("amount", ""))
    unit = normalize_text(payload.get("unit", ""))
    item = normalize_text(payload.get("item", ""))

    if item and not amount and not unit:
        return parse_ingredient_text(item)

    return {"amount": amount, "unit": unit, "item": item}


def parse_iso_duration(value: Any) -> str:
    text = normalize_text(value)
    if not text or not text.startswith("P"):
        return text
    match = re.fullmatch(
        r"P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?",
        text,
    )
    if not match:
        return text
    days = int(match.group("days") or 0)
    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes") or 0)
    parts: list[str] = []
    if days:
        parts.append(f"{days} day" + ("s" if days != 1 else ""))
    if hours:
        parts.append(f"{hours} hr")
    if minutes:
        parts.append(f"{minutes} min")
    if not parts:
        seconds = int(match.group("seconds") or 0)
        if seconds:
            parts.append(f"{seconds} sec")
    return " ".join(parts)


def extract_image(value: Any) -> str:
    if isinstance(value, str):
        return normalize_text(value)
    if isinstance(value, list):
        for item in value:
            image = extract_image(item)
            if image:
                return image
        return ""
    if isinstance(value, dict):
        for key in ("url", "contentUrl", "thumbnailUrl"):
            if value.get(key):
                return normalize_text(value.get(key))
    return ""


def extract_instructions(value: Any) -> list[str]:
    instructions: list[str] = []
    if isinstance(value, str):
        instructions.extend(
            [normalize_text(part) for part in re.split(r"\n+", value) if normalize_text(part)]
        )
    elif isinstance(value, list):
        for item in value:
            instructions.extend(extract_instructions(item))
    elif isinstance(value, dict):
        if value.get("text"):
            instructions.append(normalize_text(value.get("text")))
        elif value.get("itemListElement"):
            instructions.extend(extract_instructions(value.get("itemListElement")))
    deduped: list[str] = []
    seen: set[str] = set()
    for step in instructions:
        key = step.lower()
        if step and key not in seen:
            seen.add(key)
            deduped.append(step)
    return deduped


def extract_recipe_node(data: Any) -> dict[str, Any] | None:
    if isinstance(data, dict):
        node_type = data.get("@type")
        if isinstance(node_type, list):
            if any(str(item).lower() == "recipe" for item in node_type):
                return data
        elif isinstance(node_type, str) and node_type.lower() == "recipe":
            return data
        for key in ("@graph", "mainEntity", "itemListElement"):
            if key in data:
                found = extract_recipe_node(data[key])
                if found:
                    return found
        for value in data.values():
            found = extract_recipe_node(value)
            if found:
                return found
    elif isinstance(data, list):
        for item in data:
            found = extract_recipe_node(item)
            if found:
                return found
    return None


def extract_tags_from_recipe_node(node: dict[str, Any]) -> list[str]:
    tags: list[str] = []
    for key in ("keywords", "recipeCategory", "recipeCuisine"):
        value = node.get(key)
        if isinstance(value, str):
            tags.extend(re.split(r",", value))
        elif isinstance(value, list):
            for entry in value:
                if isinstance(entry, str):
                    tags.append(entry)
    return normalize_tags(tags)


def recipe_from_json_ld(node: dict[str, Any], source_url: str) -> dict[str, Any]:
    ingredients = [
        parse_ingredient_text(item)
        for item in node.get("recipeIngredient", [])
        if normalize_text(item)
    ]
    instructions = extract_instructions(node.get("recipeInstructions", []))
    image = extract_image(node.get("image", ""))
    return {
        "title": normalize_text(node.get("name", "")),
        "source_url": source_url,
        "image_url": urljoin(source_url, image) if image else "",
        "servings": normalize_text(node.get("recipeYield", "")),
        "prep_time": parse_iso_duration(node.get("prepTime", "")),
        "cook_time": parse_iso_duration(node.get("cookTime", "")),
        "total_time": parse_iso_duration(node.get("totalTime", "")),
        "ingredients": ingredients,
        "steps": instructions,
        "tags": extract_tags_from_recipe_node(node),
        "notes": "",
    }


# --- page reading -----------------------------------------------------------

class _PageReader(HTMLParser):
    """Pulls the JSON-LD blocks and the readable text out of a page.

    Enough HTML for the job and no more. Script, style and template contents are
    dropped, block level tags become line breaks, and everything else is text.
    """

    _SKIP = {"script", "style", "noscript", "template", "svg"}
    _BREAK = {
        "p", "div", "li", "br", "tr", "section", "article", "h1", "h2", "h3",
        "h4", "h5", "h6", "ul", "ol", "table", "header", "footer",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.json_ld: list[str] = []
        self.title = ""
        self.og_image = ""
        self._chunks: list[str] = []
        self._skip_depth = 0
        self._in_json_ld = False
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name.lower(): (value or "") for name, value in attrs}
        if tag == "script" and attributes.get("type", "").lower() == "application/ld+json":
            self._in_json_ld = True
            self.json_ld.append("")
            return
        if tag == "title":
            self._in_title = True
        if tag == "meta":
            key = (attributes.get("property") or attributes.get("name") or "").lower()
            if key in {"og:image", "twitter:image"} and not self.og_image:
                self.og_image = attributes.get("content", "")
        if tag in self._SKIP:
            self._skip_depth += 1
        if tag in self._BREAK:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._in_json_ld:
            self._in_json_ld = False
        if tag == "title":
            self._in_title = False
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1
        if tag in self._BREAK:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_json_ld:
            self.json_ld[-1] += data
            return
        if self._in_title and not self.title:
            self.title = data.strip()
        if self._skip_depth == 0:
            self._chunks.append(data)

    def text(self) -> str:
        joined = "".join(self._chunks)
        lines = [re.sub(r"[ \t]+", " ", line).strip() for line in joined.split("\n")]
        return "\n".join(line for line in lines if line)


SYSTEM_ROOTS = "/System/Library/Keychains/SystemRootCertificates.keychain"
_ssl_context: ssl.SSLContext | None = None


def ssl_context() -> ssl.SSLContext:
    """A verifying context, with the Mac's own roots when Python has none.

    A python.org install ships no certificates until somebody runs Install
    Certificates.command, and on a machine where nobody has, every recipe site
    fails to fetch. The roots the Mac already trusts are read out of the system
    keychain instead. Certificates are still verified: this fills an empty trust
    store rather than turning verification off.
    """
    global _ssl_context
    if _ssl_context is not None:
        return _ssl_context
    context = ssl.create_default_context()
    if context.cert_store_stats().get("x509_ca", 0) == 0:
        try:
            roots = subprocess.run(
                ["/usr/bin/security", "find-certificate", "-a", "-p", SYSTEM_ROOTS],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
            if "BEGIN CERTIFICATE" in roots:
                context.load_verify_locations(cadata=roots)
        except (OSError, subprocess.SubprocessError, ssl.SSLError):
            pass
    _ssl_context = context
    return context


def fetch_page(url: str, timeout: float = 20.0) -> str:
    """The page as text. Raises urllib errors for the caller to report."""
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept-Language": "en-GB,en;q=0.9",
            "Accept-Encoding": "gzip",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout, context=ssl_context()) as response:
        raw = response.read()
        if response.headers.get("Content-Encoding", "").lower() == "gzip":
            raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
        charset = response.headers.get_content_charset() or "utf-8"
    return raw.decode(charset, errors="replace")


def recipe_from_html(html: str, source_url: str) -> tuple[dict[str, Any], str]:
    """A recipe and how it was found: json-ld, or page-text when there is none.

    The page-text answer carries the readable page in the notes and no parsed
    ingredients or steps, because a guess at those is worse than nothing: the
    app's own import can read the text, and the review screen is where a person
    sees what it made of it.
    """
    reader = _PageReader()
    reader.feed(html)

    for block in reader.json_ld:
        block = block.strip()
        if not block:
            continue
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        node = extract_recipe_node(data)
        if not node:
            continue
        recipe = recipe_from_json_ld(node, source_url)
        if recipe.get("title") and (recipe.get("ingredients") or recipe.get("steps")):
            return recipe, "json-ld"

    text = reader.text()
    title = normalize_text(reader.title) or "Imported recipe"
    title = re.split(r"\s+[|–-]\s+", title)[0].strip() or title
    return (
        {
            "title": title,
            "source_url": source_url,
            "image_url": urljoin(source_url, normalize_text(reader.og_image))
            if reader.og_image
            else "",
            "servings": "",
            "prep_time": "",
            "cook_time": "",
            "total_time": "",
            "ingredients": [],
            "steps": [],
            "tags": [],
            "notes": text[:8000],
        },
        "page-text",
    )


def recipe_from_url(url: str, timeout: float = 20.0) -> tuple[dict[str, Any], str]:
    source_url = normalize_text(url)
    if not re.match(r"^https?://", source_url, re.IGNORECASE):
        raise ValueError("A recipe link has to be an http or https URL")
    html = fetch_page(source_url, timeout=timeout)
    return recipe_from_html(html, source_url)


# --- pasted text ------------------------------------------------------------

def looks_like_ingredient(line: str) -> bool:
    text = normalize_text(line)
    text = re.sub(r"^[•\-*]\s*", "", text)
    if not text:
        return False
    if re.match(r"^\d", text):
        return True
    words = [word.lower().strip(".,()") for word in text.split(" ")]
    if any(word in UNIT_WORDS for word in words[:3]):
        return True
    return False


def recipe_from_text(text: str, source_url: str = "") -> dict[str, Any]:
    """A recipe out of pasted text, by the plainest rules that work.

    The first line is the title. A Method or Instructions heading splits the
    rest, and where there is no heading the ingredient looking lines are the
    ones with a quantity in them. It is a first draft rather than an answer,
    which is why everything built this way is tagged for a second look.
    """
    lines = [normalize_text(line) for line in text.splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        raise ValueError("There is no text there to read")

    title = lines[0].rstrip(":")
    body = lines[1:]

    split_at = None
    for index, line in enumerate(body):
        if METHOD_HEADINGS.match(line):
            split_at = index
            break

    if split_at is None:
        ingredient_lines = [line for line in body if looks_like_ingredient(line)]
        step_lines = [
            line
            for line in body
            if not looks_like_ingredient(line) and not INGREDIENT_HEADINGS.match(line)
        ]
    else:
        before = [line for line in body[:split_at] if not INGREDIENT_HEADINGS.match(line)]
        after = body[split_at + 1:]
        ingredient_lines = [line for line in before if looks_like_ingredient(line)]
        leftovers = [line for line in before if not looks_like_ingredient(line)]
        step_lines = leftovers + after

    steps = [re.sub(r"^\s*\d+[.)]\s*", "", line) for line in step_lines]
    steps = [normalize_text(step) for step in steps if normalize_text(step)]

    return {
        "title": title,
        "source_url": normalize_text(source_url),
        "image_url": "",
        "servings": "",
        "prep_time": "",
        "cook_time": "",
        "total_time": "",
        "ingredients": [parse_ingredient_text(line) for line in ingredient_lines],
        "steps": steps,
        "tags": [],
        "notes": "",
    }
