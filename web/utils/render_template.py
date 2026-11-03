from info import BIN_CHANNEL, URL
from utils import temp
import urllib.parse, html

# ======================================================
# ⚡ ULTRA FAST WATCH TEMPLATE (MINIMAL)
# ======================================================

WATCH_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>

<link rel="stylesheet" href="https://cdn.plyr.io/3.7.8/plyr.css">

<style>
:root {{
  --primary: #e53935;
  --bg: #ffffff;
  --card: #f5f5f5;
  --text: #111111;
}}

body {{
  margin: 0;
  font-family: system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
  background: var(--bg);
  color: var(--text);
}}

header {{
  padding: 12px 16px;
  font-weight: 700;
  font-size: 18px;
  color: var(--primary);
}}

.container {{
  padding: 12px;
  max-width: 900px;
  margin: auto;
}}

.player-box {{
  background: #000;
  border-radius: 12px;
  overflow: hidden;
}}

video {{
  width: 100%;
  height: auto;
}}

.file-name {{
  font-size: 16px;
  font-weight: 600;
  margin: 12px 0;
}}

.tags {{
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}}

.tag {{
  font-size: 12px;
  padding: 4px 8px;
  border-radius: 6px;
  background: #ffecec;
  color: #c62828;
}}

.download-btn {{
  display: block;
  width: 100%;
  text-align: center;
  padding: 12px;
  background: var(--primary);
  color: #fff;
  font-weight: 600;
  border-radius: 10px;
  text-decoration: none;
}}

footer {{
  margin-top: 24px;
  padding: 12px;
  text-align: center;
  font-size: 13px;
  color: #777;
}}
</style>
</head>

<body>

<header>FAST FINDER</header>

<div class="container">

  <div class="player-box">
    <video class="player" controls playsinline src="{src}"></video>
  </div>

  <div class="file-name">{file_name}</div>

  <div class="tags">
    <div class="tag">STREAM</div>
    <div class="tag">FAST</div>
    <div class="tag">NO ADS</div>
  </div>

  <a class="download-btn" href="{src}" download>⬇ Direct Download</a>

</div>

<footer>© 2025 Fast Finder Bot</footer>

<script src="https://cdn.plyr.io/3.7.8/plyr.js"></script>

<script>
/* ---- Ultra light Telegram theme sync (ONE TIME) ---- */
(function () {{
  if (!window.Telegram || !Telegram.WebApp) return;
  const t = Telegram.WebApp.themeParams;
  const r = document.documentElement;
  if (t.button_color) r.style.setProperty('--primary', t.button_color);
  if (t.bg_color) r.style.setProperty('--bg', t.bg_color);
  if (t.text_color) r.style.setProperty('--text', t.text_color);
}})();

/* ---- Plyr init (minimal controls) ---- */
new Plyr('.player', {{
  controls: ['play','progress','current-time','fullscreen']
}});
</script>

</body>
</html>
"""


# ======================================================
# 🎬 WATCH HANDLER
# ======================================================

async def media_watch(message_id: int):
    msg = await temp.BOT.get_messages(BIN_CHANNEL, message_id)
    media = getattr(msg, msg.media.value, None)

    if not media:
        return "<h3>File not found</h3>"

    src = urllib.parse.urljoin(URL, f"download/{message_id}")
    title = html.escape(f"Watch - {media.file_name}")
    name = html.escape(media.file_name)

    return WATCH_HTML.format(
        title=title,
        file_name=name,
        src=src
    )
