import os
import threading
import schedule
import time
import telebot
from datetime import datetime

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN не задан в переменных окружения")

ADMIN_ID = int(os.environ.get("ADMIN_TELEGRAM_ID", 0))
TARGET_GROUP_ID = -1003482313888

bot = telebot.TeleBot(TOKEN)

message_log = []
log_lock = threading.Lock()

CONTENT_LABELS = {
    "ТЕКСТ": "💬 Текст",
    "ФОТО": "🖼 Фото",
    "ВИДЕО": "🎬 Видео",
}


def is_admin(message):
    return message.from_user.id == ADMIN_ID


def build_report(entries, title, clear=False):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    if not entries:
        return f"{title}\n📅 {now}\n\nСообщений пока нет."
    lines = [f"{title}\n📅 {now}\nВсего сообщений: {len(entries)}\n"]
    for i, e in enumerate(entries, 1):
        label = CONTENT_LABELS.get(e["type"], e["type"])
        t = e["time"].strftime("%d.%m %H:%M:%S")
        name_str = f"{e['name']} ({e['username']})" if e["username"] != "нет username" else e["name"]
        text_str = f"\n    ✏️ {e['text']}" if e["text"] else ""
        lines.append(f"{i}. [{t}] {label}\n    👤 ID: {e['user_id']} | {name_str}{text_str}")
    return "\n".join(lines)


def log_message(message, content_type, text=None):
    user = message.from_user
    username = f"@{user.username}" if user.username else "нет username"
    name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    now = datetime.now()
    entry = {
        "time": now,
        "type": content_type,
        "user_id": user.id,
        "name": name,
        "username": username,
        "text": text or "",
    }
    with log_lock:
        message_log.append(entry)
    print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] {content_type} | ID: {user.id} | Имя: {name} | {username}")


def send_daily_report():
    if not ADMIN_ID:
        print("ADMIN_TELEGRAM_ID не задан — ежедневный отчёт отключён")
        return
    today = datetime.now().day
    do_clear = today in (1, 15)
    with log_lock:
        entries = list(message_log)
        if do_clear:
            message_log.clear()
    title = "📊 Щоденний звіт + 🗑 Список очищено" if do_clear else "📊 Щоденний звіт"
    report = build_report(entries, title)
    try:
        bot.send_message(ADMIN_ID, report)
        action = "з очищенням списку" if do_clear else "без очищення"
        print(f"Щоденний звіт надіслано адміністратору ({action})")
    except Exception as ex:
        print(f"Ошибка отправки отчёта: {ex}")


def scheduler_thread():
    schedule.every().day.at("20:00").do(send_daily_report)
    while True:
        schedule.run_pending()
        time.sleep(30)


@bot.message_handler(commands=["start"])
def handle_start(message):
    if message.chat.type != "private":
        return
    if is_admin(message):
        bot.send_message(
            message.chat.id,
            "👑 Вітаю, адміне!\n\n"
            "Доступні команди:\n"
            "/report — отримати звіт прямо зараз\n"
            "/clear — очистити список повідомлень\n"
            "/stats — кількість повідомлень за сьогодні\n"
            "/myid — ваш Telegram ID"
        )
    else:
        bot.send_message(
            message.chat.id,
            "Надішліть своє повідомлення і я відправлю його в групу анонімно"
        )


@bot.message_handler(commands=["myid"])
def handle_myid(message):
    if message.chat.type != "private":
        return
    bot.send_message(
        message.chat.id,
        f"Ваш Telegram ID: `{message.from_user.id}`",
        parse_mode="Markdown"
    )


@bot.message_handler(commands=["report"])
def handle_report(message):
    if message.chat.type != "private":
        return
    if not is_admin(message):
        return
    with log_lock:
        entries = list(message_log)
    report = build_report(entries, "📊 Поточний звіт (без очищення)")
    bot.send_message(message.chat.id, report)


@bot.message_handler(commands=["clear"])
def handle_clear(message):
    if message.chat.type != "private":
        return
    if not is_admin(message):
        return
    with log_lock:
        count = len(message_log)
        message_log.clear()
    bot.send_message(message.chat.id, f"🗑 Список очищено. Видалено записів: {count}")


@bot.message_handler(commands=["stats"])
def handle_stats(message):
    if message.chat.type != "private":
        return
    if not is_admin(message):
        return
    with log_lock:
        total = len(message_log)
        texts = sum(1 for e in message_log if e["type"] == "ТЕКСТ")
        photos = sum(1 for e in message_log if e["type"] == "ФОТО")
        videos = sum(1 for e in message_log if e["type"] == "ВИДЕО")
        unique_users = len(set(e["user_id"] for e in message_log))
    bot.send_message(
        message.chat.id,
        f"📈 Статистика (з останнього очищення):\n\n"
        f"Всього повідомлень: {total}\n"
        f"💬 Текст: {texts}\n"
        f"🖼 Фото: {photos}\n"
        f"🎬 Відео: {videos}\n"
        f"👥 Унікальних користувачів: {unique_users}"
    )


@bot.message_handler(content_types=["text"])
def handle_text(message):
    if message.chat.type != "private":
        return
    if is_admin(message):
        bot.send_message(message.chat.id, "⚠️ Ви адмін. Ваше повідомлення не пересилається.")
        return
    log_message(message, "ТЕКСТ", text=message.text)
    try:
        bot.send_message(TARGET_GROUP_ID, message.text)
    except Exception as e:
        print(f"Ошибка при пересылке текста: {e}")


@bot.message_handler(content_types=["photo"])
def handle_photo(message):
    if message.chat.type != "private":
        return
    if is_admin(message):
        return
    log_message(message, "ФОТО", text=message.caption)
    try:
        photo = message.photo[-1]
        caption = message.caption or None
        bot.send_photo(TARGET_GROUP_ID, photo.file_id, caption=caption)
    except Exception as e:
        print(f"Ошибка при пересылке фото: {e}")


@bot.message_handler(content_types=["video"])
def handle_video(message):
    if message.chat.type != "private":
        return
    if is_admin(message):
        return
    log_message(message, "ВИДЕО", text=message.caption)
    try:
        caption = message.caption or None
        bot.send_video(TARGET_GROUP_ID, message.video.file_id, caption=caption)
    except Exception as e:
        print(f"Ошибка при пересылке видео: {e}")


if __name__ == "__main__":
    t = threading.Thread(target=scheduler_thread, daemon=True)
    t.start()
    print("Бот запущен. Ожидаю сообщения...")
    bot.infinity_polling(timeout=60, long_polling_timeout=60)
