"""All supported locales must cover every integration-owned UI string."""
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]/"custom_components/nova_poshta_account"


def keys(value, prefix=""):
    result = set()
    for key, item in value.items():
        name = f"{prefix}.{key}" if prefix else key
        result.update(keys(item, name) if isinstance(item, dict) else {name})
    return result


class TranslationTests(unittest.TestCase):
    def test_all_languages_cover_the_same_ui_keys(self):
        base = json.loads((ROOT/"strings.json").read_text(encoding="utf8"))
        for language in ("en", "uk", "ru"):
            localized = json.loads((ROOT/f"translations/{language}.json").read_text(encoding="utf8"))
            self.assertEqual(keys(base), keys(localized), language)
        for key in ("entity.button.refresh.name", "entity.sensor.active.name", "entity.sensor.pickup.name", "device.account.name", "exceptions.cannot_update.message"):
            self.assertIn(key, keys(base))

    def test_default_english_strings_do_not_contain_cyrillic(self):
        text = (ROOT/"strings.json").read_text(encoding="utf8")
        self.assertIsNone(re.search(r"[\u0400-\u04ff]", text))
        self.assertEqual(json.loads(text), json.loads((ROOT/"translations/en.json").read_text(encoding="utf8")))


if __name__ == "__main__":
    unittest.main()
