"""🖼️ `/warmup_thumbs` — JoneySin/v5 के `plugins/warmup.py` जैसा sequential engine.

पहली बार web खोलने पर 21 नई फाइलों के thumbnail एक साथ निकालने से Telegram
FLOOD_WAIT लग सकता है। v5 का warmup इसलिए **एक-एक करके** `send_cached_media`
चलाता है, हर file के बीच 1.2–3.0s का random gap रखता है, FloodWait पर
`e.value + 10` सोता है और बिना thumbnail वाली फाइल को `NO_THUMB` mark करता है।

fsv1 में यही सब `web/thumb_engine.py` के `probe_file()` + `_probe_lock` में है
(web requests भी उसी single lock/queue से गुजरती हैं) — यह command बस उन
सब files पर वही loop चलाता है जिनमें अभी `TG_ID:` ID locked नहीं है।
"""

import asyncio
import logging
import re
import time

from hydrogram import Client, filters, enums
from hydrogram.errors import MessageNotModified

from info import ADMINS
from database.ia_filterdb import collection

logger = logging.getLogger(__name__)

# v5 की स्मार्ट फ़िल्टर: सिर्फ़ वही docs जिनमें permanent TG_ID या NO_THUMB नहीं है
_PENDING_QUERY = {
    "thumb_url": {"$not": re.compile(r"^TG_ID:"), "$ne": "NO_THUMB"},
}


def _progress(col_name, done, total, ok, elapsed):
    pct = int((done / max(total, 1)) * 100)
    speed = (done / max(elapsed, 1)) * 60
    eta = int((total - done) / max(speed / 60, 0.001))
    dot = "🔴" if pct < 30 else "🟡" if pct < 70 else "🟢"
    return (
        "<b>🎬 THUMBNAIL WARMUP</b>\n"
        "────────────────────\n"
        f"📁 Collection: <code>{col_name}</code>\n"
        f"📈 Progress: <code>{done:,} / {total:,}</code> ({pct}%)\n"
        f"🖼️ Posters locked: <code>{ok:,}</code>\n"
        f"⚡ Speed: <code>{speed:.1f} files/min</code> · ETA <code>~{eta}s</code>\n"
        "────────────────────\n"
        f"{dot} <i>एक-एक करके, anti-flood gap के साथ — कोई parallel burst नहीं।</i>"
    )


@Client.on_message(filters.command("warmup_thumbs") & filters.user(ADMINS))
async def warmup_thumbs_cmd(client, message):
    # Lazy import: `web` package bot.py में पहले से load है; cycle से बचाव।
    from web.thumb_engine import probe_file, thumb_queue_state

    status = await message.reply(
        "⚙️ <b>Thumbnail Warmup</b>\n\nPending files गिनी जा रही हैं…",
        parse_mode=enums.ParseMode.HTML,
    )

    docs = await asyncio.to_thread(
        lambda: list(collection.find(_PENDING_QUERY, {"_id": 1, "file_name": 1}))
    )
    total = len(docs)
    if not total:
        return await status.edit_text(
            "✨ <b>सब कुछ up-to-date है!</b>\n\n"
            "सभी files के पास पहले से verified <code>TG_ID:</code> thumbnail lock "
            "या <code>NO_THUMB</code> mark है।",
            parse_mode=enums.ParseMode.HTML,
        )

    ok, skipped = 0, 0
    start = time.time()
    for i, doc in enumerate(docs, 1):
        fid = str(doc.get("_id") or "")
        if not fid:
            skipped += 1
            continue
        try:
            # ⚠️ यहीं serial है: global _probe_lock + 1.2–3.0s gap + FloodWait retry
            data = await probe_file(fid)
            if data:
                ok += 1
        except Exception as e:
            logger.warning(f"[warmup] {fid[:16]} skipped: {e}")
            skipped += 1

        # v5 की तरह हर 10 files पर UI update
        if i % 10 == 0 or i == total:
            try:
                await status.edit_text(
                    _progress("files", i, total, ok, time.time() - start),
                    parse_mode=enums.ParseMode.HTML,
                )
            except MessageNotModified:
                pass
            except Exception:
                pass

    q = thumb_queue_state()
    await status.edit_text(
        "🎉 <b>WARMUP COMPLETE</b>\n"
        "────────────────────\n"
        f"🎯 Scanned: <code>{total:,}</code>\n"
        f"🖼️ Posters locked: <code>{ok:,}</code>\n"
        f"🚫 No poster: <code>{total - ok - skipped:,}</code> · Skipped: <code>{skipped}</code>\n"
        f"⏳ Queue में बाकी: <code>{q['queued']}</code>\n"
        f"🕐 Time: <code>{int(time.time() - start)}s</code>\n\n"
        "<i>Ab web पर posters बिना extra probe के सीधे <code>TG_ID:</code> से लोड होंगे।</i>",
        parse_mode=enums.ParseMode.HTML,
    )
