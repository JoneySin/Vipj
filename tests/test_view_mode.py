#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""🖼️📄 Poster/Text mode — "एक जगह बदले तो सभी जगह" का regression test.

Stdlib-only, बिना MongoDB / Telegram / aiohttp के चलता है:

    python3 -m unittest discover -s tests -v

पूरा Poster/Text व्यवहार `web/mode_assets.py` में रहना चाहिए। बाकी फाइलें
सिर्फ़ semantic `vm-*` classes लगाती हैं और `window.ViewMode` इस्तेमाल करती हैं;
किसी दूसरी फाइल में `.mode-text` CSS, अपना mode state, अलग storage key या
Text mode के लिए अलग HTML branch आते ही ये test टूट जाएगा — यानी future में
दोबारा तीन जगह code बँटने से बचाता है।
"""
import re
import unittest
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "web"
FILES = {
    name: (WEB / name).read_text(encoding="utf-8")
    for name in (
        "mode_assets.py",
        "web_assets.py",
        "group_assets.py",
        "catalog.py",
    )
}
OTHER_FILES = {k: v for k, v in FILES.items() if k != "mode_assets.py"}


def mode_src():
    return FILES["mode_assets.py"]


def css_block():
    m = re.search(r'^MODE_CSS\s*=\s*r?"""(.*?)"""', mode_src(), re.S | re.M)
    assert m, "MODE_CSS पढ़ा नहीं गया"
    return m.group(1)


def js_block():
    m = re.search(r'^MODE_JS\s*=\s*r?"""(.*?)"""', mode_src(), re.S | re.M)
    assert m, "MODE_JS पढ़ा नहीं गया"
    return m.group(1)


class TestSingleSource(unittest.TestCase):

    def test_01_module_defines_everything(self):
        src = mode_src()
        for symbol in ("VIEW_MODE_OPTIONS", "MODE_CSS", "MODE_JS"):
            self.assertTrue(
                re.search(rf"^{symbol}\s*=", src, re.M),
                f"{symbol} मॉड्यूल में नहीं",
            )
        self.assertIn("window.ViewMode=", src, "engine उसी मॉड्यूल में होना चाहिए")
        self.assertIn("function imgAttrs(url)", src, "src ⇄ data-src एक ही जगह")
        self.assertIn("data-vm-select", src, "select auto-bind एक ही जगह")

    def test_02_options_defined_exactly_once_in_all_web_files(self):
        """Label बदलना हो तो mode_assets.py की एक लाइन बदलो — बाकी सब उसे import करें."""
        occurrences = sum(src.count("🖼️ Poster") for src in FILES.values())
        self.assertEqual(occurrences, 1, "Poster label एक से ज़्यादा जगह लिखा है")
        self.assertIn("🖼️ Poster", mode_src())
        self.assertEqual(
            len(re.findall(r"^VIEW_MODE_OPTIONS\s*=", mode_src(), re.M)), 1
        )

    def test_03_shared_module_is_imported_and_appended_last(self):
        wa = FILES["web_assets.py"]
        self.assertRegex(
            wa, r"from web\.mode_assets import VIEW_MODE_OPTIONS, MODE_CSS, MODE_JS"
        )
        self.assertIn("SITE_CSS += MODE_CSS", wa, "MODE_CSS हर page पर जाना चाहिए")
        self.assertIn("SITE_JS += MODE_JS", wa, "MODE_JS हर page पर जाना चाहिए")
        # cascade: MODE_CSS सबसे आख़िर में append हो
        css_tail = wa[wa.index("SITE_CSS +="):]
        self.assertIn("GROUP_CSS", css_tail)
        self.assertGreater(
            css_tail.index("SITE_CSS += MODE_CSS"), css_tail.rindex("GROUP_CSS")
        )
        self.assertIn("SITE_JS += MODE_JS", wa[wa.index("SITE_JS += GROUP_JS"):])
        # dropdown options का इकलौता source VIEW_MODE_OPTIONS
        self.assertRegex(wa, r'"view":\s*VIEW_MODE_OPTIONS')

    def test_04_no_split_mode_logic_anywhere_else(self):
        """पहले /search, group cards और catalog में अलग-अलग mode code था — वापस न आए।"""
        forbidden = {
            ".mode-text{": "mode-text CSS बँट गया",
            "mode-text .": "mode-text CSS बँट गया",
            "state.mode": "catalog में अलग mode state",
            "viewMode": "page-specific mode variable",
            "applyMode(": "page-specific apply function",
            "ff_view_mode'": "storage key hardcoded",
            "ff_cat_mode_": "storage key hardcoded",
        }
        for name, src in OTHER_FILES.items():
            for token, why in forbidden.items():
                self.assertNotIn(token, src, f"{name}: {why}")

    def test_05_no_text_only_markup_branch(self):
        """catalog का cardHTML() दोनों modes को एक ही markup देता है।"""
        cat = FILES["catalog.py"]
        self.assertNotIn("if(state.mode", cat, "Text mode का अलग HTML branch बचा है")
        fn = re.search(r"function cardHTML\(it\)[\s\S]*?\n\}", cat)
        self.assertIsNotNone(fn, "cardHTML मिला नहीं")
        self.assertEqual(
            fn.group(0).count("return `"), 1,
            "cardHTML में एक से ज़्यादा markup branches हैं",
        )
        for call in ("ViewMode.imgAttrs(", "ViewMode.init(", "ViewMode.apply()"):
            self.assertIn(call, cat, f"catalog का {call} अलग है")
        self.assertRegex(FILES["web_assets.py"], r"ViewMode\.init\(")

    def test_06_every_surface_opts_in_via_vm_classes(self):
        """/search, group/variant cards, /posts, /actors — सब उसी contract से।"""
        wa, gr, cat = (FILES[k] for k in ("web_assets.py", "group_assets.py", "catalog.py"))
        self.assertIn('class="vgrid vm-grid" id="grid"', wa)
        self.assertIn('vm-grid', cat)
        self.assertIn('vm-grid', gr + wa + cat)
        for name, src, required in (
            ("web_assets.py", wa,
             ("vm-card", "vm-poster", "vm-img", "vm-details", "vm-size",
              "vm-actions", "vm-body", "vm-title")),
            ("group_assets.py", gr,
             ("vm-card", "vm-master", "vm-poster", "vm-img", "vm-details",
              "vm-actions", "vm-body", "vm-title")),
            ("catalog.py", cat,
             ("vm-card", "vm-poster", "vm-img", "vm-chip", "vm-actions",
              "vm-always", "vm-body", "vm-title")),
        ):
            for cls in required:
                self.assertIn(cls, src, f"{name}: {cls} contract missing")
        # दोनों mode selects auto-bound हैं — किसी का अपना onchange handler नहीं
        self.assertEqual(wa.count('"vm": True'), 2)
        self.assertEqual(wa.count('data-vm-select="1"'), 1)
        mode_spec = re.search(r'\{"id": "modeSel"[^\n]*', wa).group(0)
        self.assertNotIn("onchange", mode_spec)
        cat_spec = re.search(r'\{"id": "catMode"[^\n]*', wa).group(0)
        self.assertNotIn("onchange", cat_spec)
        self.assertNotIn('onchange="setMode', wa)

    def test_07_text_mode_hides_only_the_photo(self):
        """CSS सिर्फ़ image/placeholder/play-overlay छिपाता है, details नहीं।"""
        block = css_block()
        for cls in (".vm-img", ".vm-ph", ".vm-overlay"):
            self.assertIn(cls, block, f"{cls} hide rule missing")
        for cls in (".vm-details", ".vm-size", ".vm-chip", ".vm-actions", ".vm-body"):
            self.assertIn(cls, block, f"{cls} को text mode में बनाए रखना ज़रूरी है")
        hide = re.search(
            r"\.vm-grid\.mode-text\s+\.vm-img,[^{]*\{([^}]*)\}", block, re.S
        )
        self.assertIsNotNone(hide, "image hide rule नहीं मिला")
        self.assertIn("display:none", hide.group(1))
        # image/placeholder/overlay और image-only pseudo decoration के अलावा
        # किसी element को display:none न मिले
        for m in re.finditer(r"([^{}]*)\{([^}]*display:none[^}]*)\}", block):
            selector = m.group(1)
            if any(c in selector for c in (".vm-img", ".vm-ph", ".vm-overlay", "::after", "::before")):
                continue
            self.fail("image के अलावा कुछ और छिपाया जा रहा है: " + selector.strip()[:80])

    def test_08_poster_mode_restores_src_without_network_in_text(self):
        js = js_block()
        for token in ("data-src", "data-thumb", "data-retry",
                      "function storageFor(kind)", "window.setMode=",
                      "window.ddSet", "img.dataset.src"):
            self.assertIn(token, js, f"MODE_JS में {token} missing")
        self.assertIn("'ff_cat_mode_'", js)
        self.assertIn("'ff_view_mode'", js)


if __name__ == "__main__":
    unittest.main(verbosity=2)
