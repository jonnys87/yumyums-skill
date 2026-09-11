"""Tests for the recipe reading, for the file the app has to accept, and for
the promise that nothing is delivered unless a delivery was asked for.

Run them with: python3 -m unittest discover -s tests -v

Set YUMYUMS_APP_PATH to a checkout of the YumYums app and the fixture test
joins in, comparing what this writes against the app's own test file.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import normalizer  # noqa: E402
import recipe_file  # noqa: E402
import yumyums_send  # noqa: E402

APP_PATH = os.environ.get("YUMYUMS_APP_PATH", "")
APP_FIXTURE = (
    Path(APP_PATH) / "YumYumsUITests" / "Fixtures" / "postcard-shortbread.yumyums"
    if APP_PATH
    else None
)

@contextlib.contextmanager
def quiet():
    """Runs main() without its report landing in the middle of the test run."""
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        yield


JSON_LD_PAGE = """<!doctype html>
<html><head>
<title>Butter bean stew | Some Cooking Site</title>
<meta property="og:image" content="/images/stew-large.jpg">
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@graph": [
    {"@type": "WebSite", "name": "Some Cooking Site"},
    {
      "@type": ["Recipe", "NewsArticle"],
      "name": "Butter bean stew",
      "image": [{"url": "/images/stew.jpg"}],
      "recipeYield": "4 servings",
      "prepTime": "PT15M",
      "cookTime": "PT1H10M",
      "totalTime": "PT1H25M",
      "keywords": "vegetarian, one pot",
      "recipeCategory": "Dinner",
      "recipeIngredient": [
        "2 tbsp olive oil",
        "400g butter beans, drained",
        "\\u00bd tsp smoked paprika",
        "a pinch of saffron",
        "Salt and pepper"
      ],
      "recipeInstructions": [
        {"@type": "HowToStep", "text": "Warm the oil in a wide pan."},
        {"@type": "HowToStep", "text": "Add the beans and simmer for forty minutes."},
        {"@type": "HowToStep", "text": "Add the beans and simmer for forty minutes."}
      ]
    }
  ]
}
</script>
</head><body><h1>Butter bean stew</h1></body></html>
"""

PLAIN_PAGE = """<!doctype html>
<html><head><title>Grandma's crumble - The Blog</title></head>
<body><article><p>Apples, sugar, butter, flour. Bake it.</p></article>
<script>var tracking = "should not appear";</script></body></html>
"""

PASTED_TEXT = """Weeknight dal
Ingredients
200g red lentils
1 onion, sliced
2 tsp cumin seeds
a pinch of salt
Method
1. Soften the onion with the cumin.
2. Add the lentils and water and simmer for half an hour.
"""


class JsonLdExtractionTests(unittest.TestCase):
    def test_reads_the_recipe_out_of_a_json_ld_page(self):
        recipe, how = normalizer.recipe_from_html(
            JSON_LD_PAGE, "https://example.com/recipes/stew"
        )
        self.assertEqual(how, "json-ld")
        self.assertEqual(recipe["title"], "Butter bean stew")
        self.assertEqual(recipe["servings"], "4 servings")
        self.assertEqual(recipe["prep_time"], "15 min")
        self.assertEqual(recipe["cook_time"], "1 hr 10 min")
        self.assertEqual(recipe["total_time"], "1 hr 25 min")
        self.assertEqual(recipe["image_url"], "https://example.com/images/stew.jpg")
        self.assertEqual(recipe["tags"], ["vegetarian", "one pot", "Dinner"])

    def test_ingredients_and_steps_come_through_parsed_and_deduped(self):
        recipe, _ = normalizer.recipe_from_html(JSON_LD_PAGE, "https://example.com/recipes/stew")
        self.assertEqual(
            recipe["ingredients"][0], {"amount": "2", "unit": "tbsp", "item": "olive oil"}
        )
        self.assertEqual(
            recipe["ingredients"][1],
            {"amount": "400", "unit": "g", "item": "butter beans, drained"},
        )
        self.assertEqual(
            recipe["ingredients"][2], {"amount": "1/2", "unit": "tsp", "item": "smoked paprika"}
        )
        self.assertEqual(len(recipe["steps"]), 2)

    def test_a_json_ld_recipe_is_not_flagged_for_a_second_look(self):
        with mock.patch.object(normalizer, "fetch_page", return_value=JSON_LD_PAGE):
            recipe, how = yumyums_send.build("https://example.com/recipes/stew")
        self.assertEqual(how, "json-ld")
        self.assertNotIn(recipe_file.AI_READ_TAG, recipe["tags"])
        data = yumyums_send.write_file(recipe, how)
        with zipfile.ZipFile(BytesIO(data)) as archive:
            manifest = json.loads(archive.read("manifest.json"))
        self.assertIs(manifest["reviewed"], True)


class PageTextFallbackTests(unittest.TestCase):
    def test_a_page_with_no_structured_recipe_is_handed_over_as_text(self):
        recipe, how = normalizer.recipe_from_html(PLAIN_PAGE, "https://example.com/crumble")
        self.assertEqual(how, "page-text")
        self.assertEqual(recipe["title"], "Grandma's crumble")
        self.assertEqual(recipe["ingredients"], [])
        self.assertIn("Apples, sugar, butter, flour", recipe["notes"])
        self.assertNotIn("should not appear", recipe["notes"])

    def test_page_text_is_tagged_ai_read_and_marked_unreviewed(self):
        with mock.patch.object(normalizer, "fetch_page", return_value=PLAIN_PAGE):
            recipe, how = yumyums_send.build("https://example.com/crumble")
        self.assertEqual(how, "page-text")
        self.assertIn(recipe_file.AI_READ_TAG, recipe["tags"])
        data = yumyums_send.write_file(recipe, how)
        with zipfile.ZipFile(BytesIO(data)) as archive:
            manifest = json.loads(archive.read("manifest.json"))
        self.assertEqual(manifest["extraction"], "page-text")
        self.assertIs(manifest["reviewed"], False)


class IngredientNormalisationTests(unittest.TestCase):
    """The shapes this parser claims to handle, taken from the app's own
    normaliser tests."""

    def assertIngredient(self, text, amount, unit, item):
        self.assertEqual(
            normalizer.parse_ingredient_text(text),
            {"amount": amount, "unit": unit, "item": item},
            text,
        )

    def test_amount_attached_to_the_unit(self):
        self.assertIngredient("400g plain flour", "400", "g", "plain flour")
        self.assertIngredient("1.5kg beef shin", "1.5", "kg", "beef shin")

    def test_amount_then_unit(self):
        self.assertIngredient("2 tbsp olive oil", "2", "tbsp", "olive oil")
        self.assertIngredient("1 1/2 cups whole milk", "1 1/2", "cups", "whole milk")
        self.assertIngredient("½ tsp fine sea salt", "1/2", "tsp", "fine sea salt")

    def test_ranges(self):
        self.assertIngredient("2-3 tbsp olive oil", "2-3", "tbsp", "olive oil")
        self.assertIngredient("2 – 3 sprigs thyme", "2-3", "sprigs", "thyme")

    def test_no_unit_at_all(self):
        self.assertIngredient("2 onions, sliced", "2", "", "onions, sliced")

    def test_a_pinch_of_something(self):
        self.assertIngredient("a pinch of saffron", "a", "pinch", "saffron")
        self.assertIngredient("pinch of saffron", "", "pinch", "saffron")
        self.assertIngredient("handful of coriander", "", "handful", "coriander")

    def test_bullets_come_off(self):
        self.assertIngredient("• 1 onion", "1", "", "onion")
        self.assertIngredient("- 2 cloves garlic", "2", "cloves", "garlic")

    def test_nothing_to_parse(self):
        self.assertIngredient("Salt and pepper", "", "", "Salt and pepper")
        self.assertIngredient("", "", "", "")


class PastedTextTests(unittest.TestCase):
    def test_splits_ingredients_from_steps_at_the_method_heading(self):
        recipe = normalizer.recipe_from_text(PASTED_TEXT)
        self.assertEqual(recipe["title"], "Weeknight dal")
        self.assertEqual(
            recipe["ingredients"],
            [
                {"amount": "200", "unit": "g", "item": "red lentils"},
                {"amount": "1", "unit": "", "item": "onion, sliced"},
                {"amount": "2", "unit": "tsp", "item": "cumin seeds"},
                {"amount": "a", "unit": "pinch", "item": "salt"},
            ],
        )
        self.assertEqual(
            recipe["steps"],
            [
                "Soften the onion with the cumin.",
                "Add the lentils and water and simmer for half an hour.",
            ],
        )

    def test_with_no_headings_the_quantity_lines_are_the_ingredients(self):
        recipe = normalizer.recipe_from_text(
            "Cheese toastie\n2 slices bread\n50g cheddar\nGrill it until it bubbles."
        )
        self.assertEqual(len(recipe["ingredients"]), 2)
        self.assertEqual(recipe["steps"], ["Grill it until it bubbles."])

    def test_empty_text_is_refused(self):
        with self.assertRaises(ValueError):
            normalizer.recipe_from_text("   \n\n ")

    def test_pasted_text_is_flagged_for_the_review_screen(self):
        recipe, how = yumyums_send.build(PASTED_TEXT)
        self.assertEqual(how, "pasted-text")
        self.assertIn(recipe_file.AI_READ_TAG, recipe["tags"])
        data = yumyums_send.write_file(recipe, how)
        with zipfile.ZipFile(BytesIO(data)) as archive:
            manifest = json.loads(archive.read("manifest.json"))
        self.assertEqual(manifest["extraction"], "pasted-text")
        self.assertIs(manifest["reviewed"], False)

    def test_a_title_can_be_given_instead_of_the_one_found(self):
        recipe, _ = yumyums_send.build(PASTED_TEXT, title_override="Tarka dal")
        self.assertEqual(recipe["title"], "Tarka dal")


class RecipeFileStructureTests(unittest.TestCase):
    def sample(self):
        return {
            "title": "Postcard shortbread",
            "ingredients": [{"amount": "250", "unit": "g", "item": "plain flour"}],
            "steps": ["Rub the butter into the flour."],
            "tags": ["Baking"],
        }

    def test_the_zip_holds_the_two_entries_the_reader_looks_for(self):
        data = recipe_file.make(self.sample())
        with zipfile.ZipFile(BytesIO(data)) as archive:
            names = archive.namelist()
            self.assertEqual(names, ["manifest.json", "recipe.json"])
            for info in archive.infolist():
                self.assertEqual(info.compress_type, zipfile.ZIP_STORED)
                self.assertNotIn("/", info.filename)

    def test_the_manifest_says_what_the_reader_checks(self):
        stamp = datetime(2026, 9, 12, 9, 41, 0, tzinfo=timezone.utc)
        data = recipe_file.make(self.sample(), created_at=stamp, extras={"reviewed": False})
        with zipfile.ZipFile(BytesIO(data)) as archive:
            manifest = json.loads(archive.read("manifest.json"))
        self.assertEqual(manifest["format"], "yumyums-recipe")
        self.assertEqual(manifest["version"], 1)
        self.assertLessEqual(manifest["version"], recipe_file.CURRENT_VERSION)
        self.assertEqual(manifest["created_at"], "2026-09-12T09:41:00Z")
        self.assertEqual(manifest["title"], "Postcard shortbread")
        self.assertIs(manifest["reviewed"], False)

    def test_the_recipe_json_carries_every_field_the_app_reads_as_a_string(self):
        data = recipe_file.make(self.sample())
        with zipfile.ZipFile(BytesIO(data)) as archive:
            recipe = json.loads(archive.read("recipe.json"))
        self.assertEqual(
            sorted(recipe),
            sorted(
                [
                    "id", "title", "source_url", "image_url", "servings", "prep_time",
                    "cook_time", "total_time", "ingredients", "steps", "tags", "notes",
                    "created_at", "updated_at",
                ]
            ),
        )
        for field in (
            "id", "title", "source_url", "image_url", "servings", "prep_time",
            "cook_time", "total_time", "notes", "created_at", "updated_at",
        ):
            self.assertIsInstance(recipe[field], str, field)
        self.assertEqual(
            recipe["ingredients"], [{"amount": "250", "unit": "g", "item": "plain flour"}]
        )
        self.assertTrue(recipe["id"])

    def test_the_fields_that_belong_to_the_app_alone_are_not_written(self):
        """last_cooked_at and sample are the device's business. A file that
        arrives claiming a recipe was cooked last Tuesday, or that it is one of
        the app's own samples, is a file telling the app something it should
        have decided itself."""
        data = recipe_file.make(self.sample())
        with zipfile.ZipFile(BytesIO(data)) as archive:
            recipe = json.loads(archive.read("recipe.json"))
        self.assertNotIn("last_cooked_at", recipe)
        self.assertNotIn("sample", recipe)

    def test_an_empty_recipe_is_refused_the_way_the_reader_would_refuse_it(self):
        with self.assertRaises(recipe_file.RecipeFileError):
            recipe_file.make({"title": "  ", "ingredients": [], "steps": []})

    def test_a_photo_is_named_for_what_it_is(self):
        png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
        data = recipe_file.make(self.sample(), photo=png)
        with zipfile.ZipFile(BytesIO(data)) as archive:
            self.assertIn("photo.png", archive.namelist())
            manifest = json.loads(archive.read("manifest.json"))
        self.assertEqual(manifest["photo"], "photo.png")

    def test_a_photo_the_app_cannot_sniff_is_refused(self):
        with self.assertRaises(recipe_file.RecipeFileError):
            recipe_file.make(self.sample(), photo=b"not an image at all really")

    def test_filenames_follow_the_app_rules(self):
        self.assertEqual(recipe_file.filename("Butter bean stew"), "Butter bean stew.yumyums")
        self.assertEqual(recipe_file.filename("Pasta / sauce"), "Pasta sauce.yumyums")
        self.assertEqual(recipe_file.filename("Pasta: sauce?"), "Pasta sauce.yumyums")
        self.assertEqual(recipe_file.filename("Two\nlines"), "Two lines.yumyums")
        self.assertEqual(recipe_file.filename("   "), "Recipe.yumyums")
        self.assertEqual(recipe_file.filename(".hidden"), "hidden.yumyums")
        self.assertEqual(recipe_file.filename("../../etc/passwd"), "etc passwd.yumyums")
        stem = recipe_file.filename("x" * 200).removesuffix(".yumyums")
        self.assertLessEqual(len(stem), recipe_file.MAXIMUM_FILENAME_LENGTH)


@unittest.skipUnless(
    APP_FIXTURE is not None and APP_FIXTURE.exists(),
    "set YUMYUMS_APP_PATH to a checkout of the app to run this",
)
class AppFixtureTests(unittest.TestCase):
    """The app's own test fixture is the reference for what its reader accepts,
    so a file written here is diffed against it."""

    def test_the_layout_matches_the_fixture(self):
        with zipfile.ZipFile(APP_FIXTURE) as archive:
            fixture_names = archive.namelist()
            fixture_methods = {info.filename: info.compress_type for info in archive.infolist()}
            fixture_manifest = json.loads(archive.read("manifest.json"))
            fixture_recipe = json.loads(archive.read("recipe.json"))

        data = recipe_file.make({"title": "Postcard shortbread", "steps": ["Bake it."]})
        with zipfile.ZipFile(BytesIO(data)) as archive:
            names = archive.namelist()
            methods = {info.filename: info.compress_type for info in archive.infolist()}
            manifest = json.loads(archive.read("manifest.json"))
            recipe = json.loads(archive.read("recipe.json"))

        self.assertEqual(names, fixture_names)
        self.assertEqual(methods, fixture_methods)
        self.assertEqual(
            sorted(set(fixture_manifest) - set(manifest)),
            [],
            "the fixture has a manifest field this writer omits",
        )
        self.assertEqual(sorted(recipe), sorted(fixture_recipe))
        for field, value in fixture_recipe.items():
            self.assertEqual(type(recipe[field]), type(value), field)


class NothingIsSentWithoutADeliveryTests(unittest.TestCase):
    """The promise the tool makes: it has no idea where any phone is until it is
    told, and it never guesses."""

    def setUp(self):
        for name in list(os.environ):
            if name.startswith("YUMYUMS_"):
                self.enterContext(mock.patch.dict(os.environ, {name: ""}, clear=False))

    def test_no_via_and_no_out_is_refused_before_anything_is_built(self):
        with mock.patch.object(yumyums_send, "build") as build:
            with self.assertRaises(SystemExit) as raised, quiet():
                yumyums_send.main([PASTED_TEXT])
        self.assertEqual(raised.exception.code, 2)
        build.assert_not_called()

    def test_out_on_its_own_writes_the_file_and_delivers_nothing(self):
        with tempfile.TemporaryDirectory() as folder:
            with mock.patch.object(yumyums_send, "deliver") as deliver, quiet():
                code = yumyums_send.main([PASTED_TEXT, "--out", folder + os.sep])
            written = list(Path(folder).iterdir())
        self.assertEqual(code, 0)
        deliver.assert_not_called()
        self.assertEqual([path.name for path in written], ["Weeknight dal.yumyums"])

    def test_messages_without_a_recipient_is_refused(self):
        with mock.patch.object(sys, "platform", "darwin"):
            with self.assertRaises(yumyums_send.SendError) as raised:
                yumyums_send.send_via_messages(
                    Path("/tmp/nothing.yumyums"), {}, to="", dry_run=True
                )
        self.assertIn("messages_to", str(raised.exception))

    def test_messages_says_so_when_this_is_not_a_mac(self):
        with mock.patch.object(sys, "platform", "linux"):
            with self.assertRaises(yumyums_send.SendError) as raised:
                yumyums_send.send_via_messages(
                    Path("/tmp/nothing.yumyums"), {"messages_to": "friend"}, to="", dry_run=True
                )
        self.assertIn("not a Mac", str(raised.exception))

    def test_telegram_without_credentials_is_refused(self):
        with self.assertRaises(yumyums_send.SendError) as raised:
            yumyums_send.send_via_telegram(Path("/tmp/nothing.yumyums"), {}, "", dry_run=True)
        self.assertIn("telegram_token", str(raised.exception))

    def test_email_without_an_address_is_refused(self):
        with self.assertRaises(yumyums_send.SendError) as raised:
            yumyums_send.send_via_email(
                Path("/tmp/nothing.yumyums"), {}, to="", title="", dry_run=True
            )
        self.assertIn("email_to", str(raised.exception))

    def test_a_config_that_is_not_there_is_not_an_error(self):
        self.assertEqual(yumyums_send.load_config(Path("/tmp/no-such-yumyums-config.json")), {})

    def test_the_repository_carries_no_recipient_of_any_kind(self):
        """The tool this replaces had one phone number compiled into it. This
        test is the reason that cannot happen again."""
        root = Path(__file__).resolve().parent.parent
        for path in sorted(root.glob("*.py")):
            text = path.read_text(encoding="utf-8")
            self.assertNotRegex(text, r"\+\d{9,}", f"{path.name} carries a phone number")
            self.assertNotIn("@gmail.", text, f"{path.name} carries an email address")
            self.assertNotRegex(
                text, r"\b\d{6,}:[A-Za-z0-9_-]{30,}", f"{path.name} carries a bot token"
            )


class DeliveryMechanicsTests(unittest.TestCase):
    def test_the_applescript_compiles(self):
        script = yumyums_send.messages_script(Path("/tmp/A recipe.yumyums"), "+15555550123")
        self.assertIn("+15555550123", script)
        if sys.platform == "darwin":
            yumyums_send.check_script(script)

    def test_a_quote_in_the_path_cannot_end_the_applescript_string(self):
        script = yumyums_send.messages_script(Path('/tmp/say "hi".yumyums'), "friend")
        self.assertIn(r"\"hi\"", script)

    def test_telegram_request_is_a_multipart_post_to_send_document(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "Test.yumyums"
            path.write_bytes(recipe_file.make({"title": "Test", "steps": ["Do it."]}))
            request = yumyums_send.telegram_request("123:abc", "4242", path, "Test")
        self.assertTrue(request.full_url.endswith("/bot123:abc/sendDocument"))
        self.assertIn("multipart/form-data", request.headers["Content-type"])
        self.assertIn(b'name="chat_id"', request.data)
        self.assertIn(b'filename="Test.yumyums"', request.data)

    def test_the_email_carries_the_file_under_its_own_name(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "Butter bean stew.yumyums"
            path.write_bytes(recipe_file.make({"title": "Butter bean stew", "steps": ["Cook."]}))
            message = yumyums_send.email_message(
                path, "cook@example.com", "phone@example.com", "Butter bean stew"
            )
        self.assertEqual(message["Subject"], "Butter bean stew")
        attachments = list(message.iter_attachments())
        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0].get_filename(), "Butter bean stew.yumyums")
        self.assertEqual(attachments[0].get_content_type(), "application/octet-stream")

    def test_the_environment_beats_the_config_file(self):
        config = {"messages_to": "from-the-file"}
        with mock.patch.dict(os.environ, {"YUMYUMS_MESSAGES_TO": "from-the-environment"}):
            self.assertEqual(
                yumyums_send.setting("messages_to", config), "from-the-environment"
            )
        with mock.patch.dict(os.environ, {"YUMYUMS_MESSAGES_TO": ""}):
            self.assertEqual(yumyums_send.setting("messages_to", config), "from-the-file")


if __name__ == "__main__":
    unittest.main()
