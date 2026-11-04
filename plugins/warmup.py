"""🖼️ `/warmup_thumbs` — thumbnail + **असली metadata** का sequential engine.

JoneySin/v5 के `plugins/warmup.py` से सीखा: एक-एक करके `send_cached_media`,
हर file के बीच 1.2–3.0s random anti-flood gap, FloodWait पर `e.value + 10`
sleep, strict thumb validation और बिना थंबनेल वाली file को `NO_THUMB` mark।

fsv1 में यही सब `web/thumb_engine.py::probe_file()` + `_probe_lock` में है (web
requests भी उसी single lock/queue से गुजरती हैं)। इस command की खासियत अब:

  * **सिर्फ़ thumbnail नहीं, पूरा important data DB में**: duration, quality,
    width/height, mime, size, type — `media_probe.py` file के असली bytes से
    सच्ची dimensions/duration निकालता है (Telegram का default 1280×720 झूठा
    हो सकता है)।
  * **fake "NO IMAGE" poster कभी save नहीं**: candidate bytes validate होते हैं,
    सच्ची image ही `TG_ID:` में जाती है; fake/blank हो तो `NO_THUMB` mark। v5
    की तरह validate हुई image को storage channel पर permanent re-upload किया
    जाता है।
  * Query सिर्फ़ उन्हीं docs की है जिनका thumbnail अभी **verified** नहीं है या
    जिनका metadata probe (`meta_v`) बाकी है — यानी पहले index हुई files की
    बिना-जाँचे `TG_ID:` ID भी इसी run में validate हो जाती है।
"""

import asyncio
import logging
import re
import time

from hydrogram import Client, filters, enums
from hydrogram.errors import MessageNotModified

from info import ADMINS
from database.ia_filterdb import collection
from media_probe import META_V

logger = logging.getLogger(__name__)

# v5 की स्मार्ट फ़िल्टर + fsv1 का verification/meta gate:
#   * NO_THUMB = पहले ही confirm हो चुका "कोई असली poster नहीं" ⇒ दोबारा न उठाएँ
#   * बाकी: ID missing / unverified / metadata probe बाकी
_PENDING_QUERY = {
    "thumb_url": {"$ne": "NO_THUMB"},
    "$or": [
        {"thumb_url": {"$not": re.compile(r"^TG_ID:")}},
        {"thumb_verified": {"$ne": True}},
        {"meta_v": {"$ne": META_V}},
    ],
}


def _progress(col_name, done, total, ok, meta, fake, elapsed):
    pct = int((done / max(total, 1)) * 100)
    speed = (done / max(elapsed, 1)) * 60
    eta = int((total - done) / max(speed / 60, 0.001))
    dot = "🔴" if pct < 30 else "🟡" if pct < 70 else "🟢"
    return (
        "<b>🎬 THUMBNAIL + META WARMUP</b>\n"
        "────────────────────\n"
        f"📁 Collection: <code>{col_name}</code>\n"
        f"📈 Progress: <code>{done:,} / {total:,}</code> ({pct}%)\n"
        f"🖼️ Real posters: <code>{ok:,}</code> · 🚫 Fake rejected: <code>{fake:,}</code>\n"
        f"💾 Meta saved: <code>{meta:,}</code>\n"
        f"⚡ Speed: <code>{speed:.1f} files/min</code> · ETA <code>~{eta}s</code>\n"
        "────────────────────\n"
        f"{dot} <i>एक-एक करके, anti-flood gap के साथ — कोई parallel burst नहीं।</i>"
    )


@Client.on_message(filters.command("warmup_thumbs") & filters.user(ADMINS))
async def warmup_thumbs_cmd(client, message):
    # Lazy import: `web` package bot.py में पहले से load है; cycle से बचाव।
    from web.thumb_engine import probe_file, thumb_queue_state

    status = await message.reply(
        "⚙️ <b>Thumbnail + Metadata Warmup</b>\n\nPending files गिनी जा रही हैं…",
        parse_mode=enums.ParseMode.HTML,
    )

    docs = await asyncio.to_thread(
        lambda: list(collection.find(_PENDING_QUERY, {"_id": 1, "file_name": 1}))
    )
    total = len(docs)
    if not total:
        return await status.edit_text(
            "✨ <b>सब कुछ up-to-date है!</b>\n\n"
            "सभी files के पास <b>verified</b> <code>TG_ID:</code> thumbnail lock, "
            "सच्चा <code>meta_v</code> metadata या <code>NO_THUMB</code> mark है।",
            parse_mode=enums.ParseMode.HTML,
        )

    skipped = 0
    start = time.time()
    base = thumb_queue_state()
    for i, doc in enumerate(docs, 1):
        fid = str(doc.get("_id") or "")
        if not fid:
            skipped += 1
            continue
        try:
            # ⚠️ यहीं serial है: global _probe_lock + 1.2–3.0s gap + FloodWait retry
            #    उसी probe में true metadata + verified real thumbnail DB में जाते हैं।
            await probe_file(fid)
        except Exception as e:
            logger.warning(f"[warmup] {fid[:16]} skipped: {e}")
            skipped += 1

        # v5 की तरह हर 10 files पर UI update
        if i % 10 == 0 or i == total:
            q = thumb_queue_state()
            try:
                await status.edit_text(
                    _progress("files", i, total,
                              q["ok"] - base["ok"], q["meta"] - base["meta"],
                              q["rejected"] - base["rejected"], time.time() - start),
                    parse_mode=enums.ParseMode.HTML,
                )
            except MessageNotModified:
                pass
            except Exception:
                pass

    q = thumb_queue_state()
    ok = q["ok"] - base["ok"]
    meta = q["meta"] - base["meta"]
    fake = q["rejected"] - base["rejected"]
    no_thumb = q["no_thumb"] - base["no_thumb"]
    failed = q["failed"] - base["failed"]
    await status.edit_text(
        "🎉 <b>WARMUP COMPLETE</b>\n"
        "────────────────────\n"
        f"🎯 Scanned: <code>{total:,}</code>\n"
        f"🖼️ Real posters saved: <code>{ok:,}</code>\n"
        f"💾 Duration/quality/meta saved: <code>{meta:,}</code>\n"
        f"🚫 Fake \"NO IMAGE\" rejected: <code>{fake:,}</code>\n"
        f"⚪ No real poster (NO_THUMB): <code>{no_thumb:,}</code>\n"
        f"⏳ Queue में बाकी: <code>{q['queued']}</code> · Errors: <code>{failed + skipped}</code>\n"
        f"🕐 Time: <code>{int(time.time() - start)}s</code>\n\n"
        "<i>Ab web पर सिर्फ़ verified posters + सच्ची duration/quality दिखेंगी, "
        "बिना extra probe के।</i>",
        parse_mode=enums.ParseMode.HTML,
    )
