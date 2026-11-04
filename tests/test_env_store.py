#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""⚙️ Environment store — regression test for `/admin` → Environment.

Stdlib-only; MongoDB / Telegram ki zaroorat nahi (DB fake hai):

    python3 -m unittest discover -s tests -v

Guards
------
* `env_store.SPECS` = **single source**: har boolean switch jo `info.py` me
  `is_enabled(...)` se aata hai, spec me bhi hai (warna panel se wo switch nahi dikhega).
* Badle gaye values live hain (`info` patch + `env_manager.get`), aur reset
  host env / code default par wapas jaata hai.
* `.env` mirror likhta hai, override DB me save hota hai, history banti hai.
* Secrets masked hain; deployment vars (`ADMINS`, `BOT_TOKEN` …) settable nahi hain.
"""
import asyncio
import os
import re
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# `info.py` import hone se pehle zaroori env (asli deployment values nahi)
os.environ.setdefault("API_ID", "11111")
os.environ.setdefault("API_HASH", "testhash")
os.environ.setdefault("BOT_TOKEN", "11111:testtoken")
os.environ.setdefault("ADMINS", "42")
os.environ.setdefault("LOG_CHANNEL", "-1001")
os.environ.setdefault("BIN_CHANNEL", "-1002")
os.environ.setdefault("DATA_DATABASE_URL", "mongodb://localhost:27017")
os.environ.setdefault("URL", "https://example.com")

INFO = ROOT / "info.py"


class FakeDB:
    """`database.users_chats_db.db` ka sirf wo hissa jo env_store use karta hai."""

    def __init__(self):
        self.docs = {}

    async def get_env_overrides(self):
        return [dict(v, _id=k) for k, v in self.docs.items()]

    async def set_env_override(self, name, value, by=0, old=""):
        doc = self.docs.setdefault(name, {"value": value, "history": []})
        history = doc.setdefault("history", [])
        history.append({"value": value, "by": by, "old": old})
        doc.update({"value": value, "by": by})
        return True

    async def delete_env_override(self, name):
        return self.docs.pop(name, None) is not None


def install_fake_db():
    """env_store `from database.users_chats_db import db` karta hai — fake lagao."""
    fake_db = FakeDB()
    dbs = types.ModuleType("database")
    dbs.__path__ = []                                    # package bana do
    users = types.ModuleType("database.users_chats_db")
    users.db = fake_db
    sys.modules["database"] = dbs
    sys.modules["database.users_chats_db"] = users
    return fake_db


FAKE = install_fake_db()

import info                                            # noqa: E402
import env_store                                       # noqa: E402
from env_store import (                                 # noqa: E402
    SPECS, SPEC_MAP, EnvError, env_manager, env_text, mask_secret,
    parse_input,
)


class TestSpecs(unittest.TestCase):

    def test_01_is_enabled_switches_are_all_in_specs(self):
        """`info.py` me jo bhi `is_enabled(...)` se aata hai, panel me hona chahiye."""
        src = INFO.read_text(encoding="utf-8")
        switches = set(re.findall(r"is_enabled\(['\"](\w+)['\"]", src))
        self.assertTrue(switches, "info.py me koi is_enabled switch nahi mila")
        missing = switches - set(SPEC_MAP)
        self.assertFalse(missing, f"panel me missing boolean switches: {sorted(missing)}")
        for name in switches:
            self.assertEqual(SPEC_MAP[name].kind, "bool", f"{name} bool hona chahiye")

    def test_02_names_are_unique_and_uppercase(self):
        names = [s.name for s in SPECS]
        self.assertEqual(len(names), len(set(names)), "duplicate spec names")
        bad = [n for n in names if not re.fullmatch(r"[A-Z][A-Z0-9_]*", n)]
        self.assertFalse(bad, f"spec names uppercase hone chahiye: {bad}")
        self.assertEqual(len(SPEC_MAP), len(SPECS))

    def test_03_defaults_build_a_valid_env(self):
        """Har spec ka default parse ho sake (typo / galat type pakda jaaye)."""
        for spec in SPECS:
            if not spec.settable:
                continue
            parse_input(spec, env_text(spec, spec.default))

    def test_04_deployment_vars_are_read_only_and_secrets_masked(self):
        for name in ("ADMINS", "BOT_TOKEN", "API_ID", "API_HASH",
                     "DATA_DATABASE_URL", "URL", "BIN_CHANNEL", "LOG_CHANNEL"):
            self.assertIn(name, SPEC_MAP, f"{name} spec me nahi hai")
            self.assertFalse(SPEC_MAP[name].settable, f"{name} read-only hona chahiye")
        for name in ("BOT_TOKEN", "API_HASH", "DATA_DATABASE_URL"):
            self.assertTrue(SPEC_MAP[name].secret, f"{name} secret hona chahiye")

    def test_05_secret_masking_never_leaks_the_value(self):
        out = mask_secret("BOT_TOKEN", "123456:AAH-supersecrettoken")
        self.assertNotIn("supersecret", out)
        self.assertIn("1234", out)
        url = mask_secret("DATA_DATABASE_URL", "mongodb+srv://user:pw@db.example.net/x")
        self.assertNotIn("pw@", url)
        self.assertIn("db.example.net", url)
        self.assertEqual(mask_secret("STREAM_SECRET", ""), "— (khaali)")


class TestParsing(unittest.TestCase):

    def test_01_bool_words(self):
        spec = SPEC_MAP["IS_STREAM"]
        for raw in ("true", "TRUE", "on", "1", "yes", "enable", "haan"):
            self.assertIs(parse_input(spec, raw), True, raw)
        for raw in ("false", "OFF", "0", "no", "disable", "nahi"):
            self.assertIs(parse_input(spec, raw), False, raw)
        with self.assertRaises(EnvError):
            parse_input(spec, "maybe")

    def test_02_numbers_and_limits(self):
        spec = SPEC_MAP["MAX_WEB_RESULTS"]                 # 1 … 100
        self.assertEqual(parse_input(spec, " 30 "), 30)
        self.assertEqual(parse_input(spec, "1_0"), 10)
        for bad in ("0", "101", "abc", ""):
            with self.assertRaises(EnvError, msg=bad):
                parse_input(spec, bad)
        gap = SPEC_MAP["THUMB_PROBE_GAP_MIN"]              # float
        self.assertEqual(parse_input(gap, "2.5"), 2.5)

    def test_03_keep_only_for_secrets(self):
        self.assertEqual(parse_input(SPEC_MAP["STREAM_SECRET"], "KEEP"),
                         env_store.BOOT_VALUES["STREAM_SECRET"])
        with self.assertRaises(EnvError):
            parse_input(SPEC_MAP["MAX_BTN"], "KEEP")

    def test_04_long_text_is_rejected(self):
        with self.assertRaises(EnvError):
            parse_input(SPEC_MAP["UPI_ID"], "x" * 400)


class TestLiveOverride(unittest.TestCase):

    def setUp(self):
        env_manager._override.clear()
        env_manager._meta.clear()
        FAKE.docs.clear()
        self.tmp = tempfile.TemporaryDirectory()
        self._env_file = env_store.ENV_FILE
        env_store.ENV_FILE = os.path.join(self.tmp.name, ".env")

    def tearDown(self):
        env_store.ENV_FILE = self._env_file
        self.tmp.cleanup()
        env_manager._override.clear()
        # info ko wapas boot value par le aao
        for spec in SPECS:
            setattr(info, spec.name, env_store.BOOT_VALUES[spec.name])

    def test_01_bool_flip_is_live_and_persisted(self):
        ok, msg = asyncio.run(env_manager.set("IS_STREAM", "false", by=42))
        self.assertTrue(ok, msg)
        self.assertIs(info.IS_STREAM, False)               # live module value
        self.assertIs(env_manager.get("IS_STREAM"), False)
        self.assertEqual(env_manager.source("IS_STREAM"), "panel")
        self.assertEqual(FAKE.docs["IS_STREAM"]["value"], "False")
        self.assertEqual(FAKE.docs["IS_STREAM"]["by"], 42)

        text = Path(env_store.ENV_FILE).read_text(encoding="utf-8")
        self.assertIn("IS_STREAM=False", text)             # `.env` mirror
        self.assertIn("last write", text)

    def test_02_reset_returns_to_host_env_value(self):
        original = env_store.BOOT_VALUES["IS_STREAM"]
        asyncio.run(env_manager.set("IS_STREAM", "false", by=1))
        ok, _ = asyncio.run(env_manager.reset("IS_STREAM"))
        self.assertTrue(ok)
        self.assertIs(info.IS_STREAM, original)
        self.assertIs(env_manager.get("IS_STREAM"), original)
        self.assertEqual(env_manager.source("IS_STREAM"), "default")
        self.assertNotIn("IS_STREAM", FAKE.docs)
        self.assertNotIn("IS_STREAM", Path(env_store.ENV_FILE).read_text())

    def test_03_boot_values_survive_a_restart(self):
        """DB me override hai ⇒ naye process me bhi wahi value load hoti hai."""
        asyncio.run(env_manager.set("MAX_WEB_RESULTS", "60", by=7))
        # restart simulate: naya manager, same DB
        fresh = env_store.EnvManager()
        asyncio.run(fresh.ensure_loaded())
        self.assertEqual(fresh.get("MAX_WEB_RESULTS"), 60)
        self.assertEqual(info.MAX_WEB_RESULTS, 60)
        self.assertEqual(fresh.meta("MAX_WEB_RESULTS")["by"], 7)

    def test_04_invalid_value_changes_nothing(self):
        before = env_manager.get("IS_PREMIUM")
        ok, msg = asyncio.run(env_manager.set("IS_PREMIUM", "haan ji", by=1))
        self.assertFalse(ok)
        self.assertIn("true", msg)
        self.assertEqual(env_manager.get("IS_PREMIUM"), before)
        self.assertEqual(FAKE.docs, {})

    def test_05_read_only_and_unknown_vars_are_rejected(self):
        for name in ("ADMINS", "BOT_TOKEN", "NOPE_VAR"):
            ok, msg = asyncio.run(env_manager.set(name, "1", by=1))
            self.assertFalse(ok, name)
        self.assertEqual(FAKE.docs, {})

    def test_06_premium_switch_clears_the_premium_cache(self):
        try:
            from utils import temp                        # asli utils (DB fake)
        except ModuleNotFoundError:
            # stdlib-only environment (hydrogram nahi) → stub, contract wahi hai
            stub = types.ModuleType("utils")
            stub.temp = types.SimpleNamespace(PREMIUM={})
            sys.modules.setdefault("utils", stub)
            temp = stub.temp
        temp.PREMIUM[99] = {"expire": None, "checked_at": 1}
        asyncio.run(env_manager.set("IS_PREMIUM", "false", by=1))
        self.assertEqual(temp.PREMIUM, {}, "premium cache saaf honi chahiye")
        self.assertIs(env_manager.get("IS_PREMIUM"), False)


class TestLiveReads(unittest.TestCase):
    """Code `env_manager.get()` padhta hai — kahin `from info import IS_PREMIUM` na rahe."""

    LIVE = ("IS_PREMIUM", "IS_STREAM", "PROTECT_CONTENT", "USE_CAPTION_FILTER",
            "ALLOW_UNSIGNED_LINKS", "MAX_WEB_RESULTS", "WEB_STREAM_TTL",
            "THUMB_BROWSER_CACHE", "PM_FILE_DELETE_TIME", "MAX_BTN",
            "PRE_DAY_AMOUNT", "UPI_ID", "UPI_NAME", "RECEIPT_SEND_USERNAME")

    def test_01_no_module_freezes_a_live_value_at_import(self):
        offenders = []
        for folder in ("plugins", "web", "database"):
            for path in (ROOT / folder).rglob("*.py"):
                src = path.read_text(encoding="utf-8")
                for m in re.finditer(r"from info import ([^\n]+(?:\n[^\n)]+)*)", src):
                    imported = m.group(1)
                    for name in self.LIVE:
                        if re.search(rf"\b{name}\b", imported):
                            offenders.append(f"{path.relative_to(ROOT)} → {name}")
        for path in (ROOT / "utils.py", ROOT / "bot.py"):
            src = path.read_text(encoding="utf-8")
            for m in re.finditer(r"from info import ([^\n]+)", src):
                for name in self.LIVE:
                    if re.search(rf"\b{name}\b", m.group(1)):
                        offenders.append(f"{path.name} → {name}")
        self.assertFalse(offenders, "ye values panel se live badalti hain: " + str(offenders))

    def test_02_info_exposes_every_spec(self):
        for spec in SPECS:
            self.assertTrue(hasattr(info, spec.name) or not spec.settable,
                            f"info.{spec.name} missing (default {spec.default!r})")

    def test_03_stream_secret_refresh_keeps_models_in_sync(self):
        import stream_security
        before = stream_security._SECRET
        asyncio.run(env_manager.set("STREAM_SECRET", "brand-new-secret", by=1))
        self.assertNotEqual(stream_security._SECRET, before)
        self.assertGreaterEqual(stream_security.STREAM_TTL, int(info.WEB_STREAM_TTL))
        ok, _ = asyncio.run(env_manager.reset("STREAM_SECRET"))
        self.assertTrue(ok)
        self.assertEqual(stream_security._SECRET, before)


if __name__ == "__main__":
    unittest.main()
