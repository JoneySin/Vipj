class script(object):

    # ================= START =================
    START_TXT = (
        "<b>👋 Hey {}</b>\n"
        "<i>Welcome to {}</i>\n\n"
        "🤖 I am an <b>Ultra Advanced Auto Filter Bot</b>\n"
        "⚡ Fast • 🔍 Smart • 🧠 Fuzzy Search\n\n"
        "📌 Just send any movie / series name\n"
        "📌 Works in Groups & PM\n"
        "📌 Premium unlocks extra power 💎\n\n"
    )

    # ================= STATUS =================
    STATUS_TXT = (
        "<b>📊 BOT STATUS</b>\n\n"
        "👥 Users      : <code>{}</code>\n"
        "💎 Premium    : <code>{}</code>\n"
        "👨‍👩‍👧 Groups    : <code>{}</code>\n\n"
        "📁 Indexed Files : <code>{}</code>\n"
        "🗄 Database Size : <code>{}</code>\n\n"
        "⏱ Uptime     : <code>{}</code>\n"
        "⚡ Performance : <b>Stable</b>\n"
    )

    # ================= NEW USER / GROUP LOG =================
    NEW_USER_TXT = (
        "👤 <b>New User Started Bot</b>\n\n"
        "🆔 ID   : <code>{}</code>\n"
        "👤 Name : {}"
    )

    NEW_GROUP_TXT = (
        "👥 <b>Bot Added to New Group</b>\n\n"
        "🏷 Title : {}\n"
        "🆔 ID    : <code>{}</code>\n"
        "👤 Users : <code>{}</code>"
    )

    # ================= FILE NOT FOUND =================
    NOT_FILE_TXT = (
        "❌ <b>No Results Found</b>\n\n"
        "🔍 Search : <code>{}</code>\n\n"
        "💡 Tips:\n"
        "• Check spelling\n"
        "• Try short keywords\n"
        "• Use year / quality\n"
    )

    # ================= FILE CAPTION =================
    FILE_CAPTION = (
        "<b>{file_name}</b>\n\n"
        "📦 Size : {file_size}\n\n"
        "⚠️ Please close this message after use"
    )

    # ================= WELCOME =================
    WELCOME_TEXT = (
        "👋 Welcome {mention}!\n\n"
        "🎬 Enjoy unlimited movies & series\n"
        "🔍 Just type the name to search"
    )

    # ================= HELP =================
    HELP_TXT = (
        "<b>ℹ️ Help Menu</b>\n\n"
        "🔍 Send movie / series name\n"
        "📂 Get instant results\n"
        "💎 Use Premium for PM search\n\n"
        "📌 Use /commands to see all features"
    )

    # ================= USER COMMANDS =================
    USER_COMMAND_TXT = (
        "<b>👤 USER COMMANDS</b>\n\n"

        "🔍 <b>Search</b>\n"
        "• Just send movie / series name\n\n"

        "💎 <b>Premium</b>\n"
        "• /plan – View premium plans\n"
        "• /myplan – Check your plan\n"
        "• /invoice – View last invoice\n\n"

        "📤 <b>File Tools</b>\n"
        "• /go – GoFile upload\n"
        "• /trans – Transfer.sh upload\n\n"

        "⚙️ <b>Utilities</b>\n"
        "• /id – Get ID\n"
        "• /ping – Bot response\n"
        "• /uptime – Bot uptime\n"
        "• /health – System health\n"
    )

    # ================= ADMIN COMMANDS =================
    ADMIN_COMMAND_TXT = (
        "<b>👮 ADMIN COMMANDS</b>\n\n"

        "📁 <b>Indexing</b>\n"
        "• /index – Start indexing\n\n"

        "💎 <b>Premium</b>\n"
        "• /premium – Admin premium panel\n"
        "• Trial approval UI\n"
        "• Invoice history\n\n"

        "📢 <b>Broadcast</b>\n"
        "• /broadcast – Users\n"
        "• /grp_broadcast – Groups\n\n"

        "🛡 <b>Moderation</b>\n"
        "• /warn /mute /unmute\n"
        "• /softban /tempban\n\n"

        "📊 <b>Stats</b>\n"
        "• /stats – Bot statistics\n"
        "• /restart – Restart bot\n"
    )
