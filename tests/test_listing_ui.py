#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""🧭 Listing UI guards — group name label + New Post/Profile button placement.

Stdlib-only:

    python3 -m unittest discover -s tests -v

1. Group card के नाम के सामने "▾ Files" लिखा हुआ label नहीं रहना चाहिए;
   expand/collapse toggle (`.gopenbtn`) बना रहना चाहिए।
2. `/posts` / `/actors` का ✨ New Post / ✨ New Profile button `.cat-head` से
   हटाकर `.cat-toolbar` में, filters के बाद रखा गया है — 🖥️ desktop पर search
   वाली लाइन में (`flex-wrap:nowrap`), 📱 mobile पर filters वाली row के नीचे
   पूरी चौड़ाई का (`flex:1 1 100%`)।
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
GROUP = (WEB / "group_assets.py").read_text(encoding="utf-8")
CATALOG = (WEB / "catalog.py").read_text(encoding="utf-8")
WEB_ASSETS = (WEB / "web_assets.py").read_text(encoding="utf-8")


class TestGroupNameLabel(unittest.TestCase):

    def test_01_no_files_label_next_to_group_name(self):
        tpl = re.search(
            r"^GROUP_CARD_TEMPLATE\s*=\s*\((.*?)\n\)", GROUP, re.S | re.M)
        self.assertIsNotNone(tpl, "GROUP_CARD_TEMPLATE नहीं मिला")
        self.assertNotIn("Files", tpl.group(1),
                         "नाम के सामने 'Files' label वापस आ गया")
        self.assertNotIn(">▾ Files<", GROUP)

    def test_02_expand_toggle_still_works(self):
        self.assertIn('class="gopenbtn"', GROUP)
        self.assertIn("gToggle(this)", GROUP)
        self.assertIn(">▾</button>", GROUP, "chevron toggle हट गया")
        self.assertIn('aria-label="Expand / collapse"', GROUP)
        self.assertIn(".gcard.open .gopenbtn{transform:rotate(180deg)", GROUP)


class TestCreateButtonPlacement(unittest.TestCase):

    def test_03_button_is_in_the_single_box(self):
        body = re.search(r"def _listing_body\([\s\S]*?\n\"\"\"", CATALOG)
        self.assertIsNotNone(body)
        html = body.group(0)
        self.assertIn('class="cat-btn cat-create"', html)
        self.assertIn("openEditor(", html)
        self.assertIn("✨ New ", html)
        self.assertNotIn('<div class="cat-head">', html,
                         "page-heading वापस आ गया")
        self.assertIn('<div class="cat-toolbar cat-box"', html)
        toolbar = html.split('<div class="cat-toolbar cat-box"')[1].split(
            "\n  </div>")[0]
        for token in ("cat-search", "{filters_html}", "{create_btn}", 'id="catCount"'):
            self.assertIn(token, toolbar, f"box में {token} नहीं है")
        # DOM order: search → filters → create → count
        self.assertLess(toolbar.index("{filters_html}"), toolbar.index("{create_btn}"))
        self.assertLess(toolbar.index("{create_btn}"), toolbar.index('id="catCount"'))

    def test_06_no_page_heading_one_search_box(self):
        """v5 `.search-box` जैसा: कोई title नहीं, सब कुछ एक card-box में।"""
        self.assertNotIn(".cat-head{", CATALOG)
        self.assertNotIn(".cat-title{", CATALOG)
        self.assertNotIn('"page": "Content Posts"', CATALOG)
        self.assertNotIn('"page": "Directory Profiles"', CATALOG)
        self.assertIn(".cat-toolbar.cat-box{", CATALOG)
        self.assertIn("background:var(--card)", CATALOG)
        self.assertIn("box-shadow:0 4px 15px rgba(0,0,0,.10)", CATALOG)
        self.assertIn("padding:16px;margin-bottom:25px", CATALOG)
        # mobile वाला पुराना "chrome हटाओ" override अब नहीं होना चाहिए
        self.assertNotIn("background:transparent;border:0;border-radius:0;padding:0",
                         WEB_ASSETS, "mobile पर box फिर से गायब हो गया")
        self.assertIn(".cat-toolbar.cat-toolbar .cat-count{", WEB_ASSETS,
                      "count उसी box के अंदर रहना चाहिए")

    def test_04_desktop_same_line_as_search(self):
        self.assertIn(".cat-toolbar .cat-create{flex:0 0 auto;white-space:nowrap}", CATALOG)
        self.assertIn(
            "@media(min-width:761px){.cat-toolbar.cat-toolbar{flex-wrap:nowrap}}", CATALOG)
        self.assertIn(".cat-search{position:relative;flex:1 1 240px;min-width:0}", CATALOG,
                      "search को shrink होने देना ज़रूरी है (overflow न हो)")

    def test_05_mobile_below_filter_buttons(self):
        mobile = re.search(
            r"@media\(max-width:760px\)\{(.*?)\n\}", WEB_ASSETS, re.S)
        self.assertIsNotNone(mobile, "shared mobile filter-row block नहीं मिला")
        block = mobile.group(1)
        self.assertIn(".filters{flex:1 1 100%}", block)
        self.assertIn(".qwrap,.cat-toolbar .cat-search{flex:1 1 100%}", block)
        self.assertIn(
            ".cat-toolbar.cat-toolbar .cat-create{flex:1 1 100%;width:100%}", block,
            "create button mobile पर filters के नीचे पूरी लाइन नहीं लेता")
        # (0,3,0) specificity — CATALOG_CSS body में बाद में आकर इसे हरा न पाए
        self.assertIn(".cat-toolbar.cat-toolbar", block)


if __name__ == "__main__":
    unittest.main(verbosity=2)
