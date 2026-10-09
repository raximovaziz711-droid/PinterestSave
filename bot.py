"""
Pinterest Save Bot — pin.it / pinterest.com linklaridan rasm/video oladi.
Ishga tushirish:
    pip install -r requirements.txt
    python bot.py
"""
import os
import re
import logging
import requests
import telebot
from telebot import types
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
if not BOT_TOKEN:
    raise SystemExit("❌ BOT_TOKEN topilmadi. .env fayliga BOT_TOKEN=... yozing (namuna: .env.example).")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

URL_RE = re.compile(r"https?://[^\s]+")
PINTEREST_DOMAINS = ("pin.it", "pinterest.com", "pinterest.", "pinimg.com")


def is_pinterest_url(url: str) -> bool:
    u = url.lower()
    return any(d in u for d in PINTEREST_DOMAINS)


def extract_og(html: str, prop: str) -> str:
    # <meta property="og:image" content="..." /> — atributlar tartibi har xil bo'lishi mumkin
    patterns = [
        rf'<meta[^>]+property=["\']{prop}["\'][^>]+content=["\']([^"\']+)["\']',
        rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']{prop}["\']',
        rf'<meta[^>]+name=["\']{prop}["\'][^>]+content=["\']([^"\']+)["\']',
    ]
    for p in patterns:
        m = re.search(p, html, re.IGNORECASE)
        if m:
            return m.group(1).replace("&amp;", "&")
    return ""


def get_best_image(og_image: str, html: str) -> str:
    """og:image bilan bir xil faylning eng katta versiyasini topish."""
    if not og_image:
        return ""
    try:
        filename = og_image.rstrip("/").split("/")[-1]  # masalan: abc123.jpg
        if "." not in filename:
            return og_image
        # html ichidagi barcha i.pinimg.com rasmlari
        candidates = re.findall(
            r"https://i\.pinimg\.com/[a-zA-Z0-9]+/[^\"'\s\\]+?\.(?:jpg|jpeg|png|webp)",
            html,
        )
        same = [c for c in candidates if c.endswith(filename)]
        if not same:
            return og_image
        # sifat ustunligi: originals > 1200x > 736x > 474x > 236x
        def score(u: str) -> int:
            if "/originals/" in u:
                return 100
            if "/1200x/" in u:
                return 80
            if "/736x/" in u:
                return 60
            if "/564x/" in u:
                return 50
            if "/474x/" in u:
                return 40
            if "/236x/" in u:
                return 20
            return 10
        same = sorted(set(same), key=score, reverse=True)
        return same[0]
    except Exception as e:
        logger.warning(f"get_best_image xato: {e}")
        return og_image


def get_pinterest_data(url: str) -> dict:
    """Pinterest sahifasidan rasm/video linklarini ajratib oladi."""
    # 1. To'g'ridan-to'g'ri i.pinimg.com bo'lsa — tayyor rasm
    if "i.pinimg.com" in url.lower():
        clean = url.split("?")[0]
        return {"ok": True, "type": "photo", "image": clean, "video": "",
                "title": "", "source": url}

    r = requests.get(url, headers=HEADERS, timeout=25, allow_redirects=True)
    r.raise_for_status()
    html = r.text
    final_url = r.url

    title = extract_og(html, "og:title")
    desc = extract_og(html, "og:description")
    og_image = extract_og(html, "og:image")
    og_video = extract_og(html, "og:video")

    # video pinlar uchun v.pinimg.com mp4 ni ham qidiramiz
    videos = re.findall(r"https://v\.pinimg\.com/[^\"'\s\\]+\.mp4", html)
    video_url = og_video or (videos[0] if videos else "")
    # og:video ba'zan html entity bilan keladi
    video_url = video_url.replace("&amp;", "&")

    best_image = get_best_image(og_image, html) if og_image else ""

    # pin id ni final_url dan olishga urinamiz
    pin_id = ""
    m = re.search(r"/pin/(\d+)", final_url)
    if m:
        pin_id = m.group(1)

    if video_url:
        return {"ok": True, "type": "video", "image": best_image or og_image,
                "video": video_url, "title": title, "desc": desc,
                "source": final_url, "pin_id": pin_id}
    if best_image or og_image:
        return {"ok": True, "type": "photo", "image": best_image or og_image,
                "video": "", "title": title, "desc": desc,
                "source": final_url, "pin_id": pin_id}

    return {"ok": False, "error": "Bu linkdan rasm topilmadi. Pin o'chirilgan yoki yopiq bo'lishi mumkin."}


START_TEXT = (
    "👋 <b>Salom! Pinterest Save Botman</b>\n\n"
    "Menga Pinterest link yuboring — men ostidagi rasm/videoni olib beraman.\n\n"
    "📌 Misol:\n<code>https://pin.it/XXrbrYAhO</code>\n\n"
    "Shunchaki linkni tashlang, qolgani mendan 🙂"
)

HELP_TEXT = (
    "📥 <b>Qanday ishlatish:</b>\n\n"
    "1. Pinterest'dan <b>Share → Copy link</b> qiling\n"
    "2. Linkni shu botga yuboring\n"
    "3. Men rasm yoki videoni qaytaraman\n\n"
    "Qo'llab-quvvatlanadi:\n"
    "• <code>pin.it/...</code> (qisqa linklar)\n"
    "• <code>pinterest.com/pin/...</code>\n"
    "• <code>i.pinimg.com/...</code> (tayyor rasm)\n\n"
    "Savol bo'lsa /start ni bosing."
)


@bot.message_handler(commands=["start"])
def cmd_start(message):
    bot.send_message(message.chat.id, START_TEXT)


@bot.message_handler(commands=["help"])
def cmd_help(message):
    bot.send_message(message.chat.id, HELP_TEXT)


@bot.message_handler(func=lambda m: m.text and ("pin.it" in m.text or "pinterest" in m.text or "pinimg.com" in m.text))
def handle_pinterest(message):
    urls = URL_RE.findall(message.text or "")
    pin_urls = [u.rstrip(").,;!\"'") for u in urls if is_pinterest_url(u)]
    if not pin_urls:
        bot.reply_to(message, "❌ Pinterest link topilmadi. Qaytadan yuboring.")
        return

    for url in pin_urls:
        status = bot.reply_to(message, f"⏳ <b>Yuklanmoqda...</b>\n<code>{url}</code>")
        try:
            bot.send_chat_action(message.chat.id, "upload_photo")
            data = get_pinterest_data(url)
            if not data.get("ok"):
                bot.edit_message_text(f"❌ {data.get('error', 'Xatolik')}",
                                      message.chat.id, status.message_id, parse_mode="HTML")
                continue

            caption = ""
            if data.get("title"):
                # caption juda uzun bo'lmasligi uchun kesamiz
                t = data["title"].strip()
                if len(t) > 200:
                    t = t[:200] + "..."
                caption = f"📌 {t}"

            if data["type"] == "video" and data.get("video"):
                bot.send_chat_action(message.chat.id, "upload_video")
                try:
                    bot.send_video(message.chat.id, data["video"], caption=caption or None,
                                   reply_to_message_id=message.message_id)
                except Exception:
                    # ba'zi videolar to'g'ridan yuborilmasa — preview rasm + link beramiz
                    if data.get("image"):
                        bot.send_photo(message.chat.id, data["image"], caption=(caption + "\n\n🎬 Video: " + data["video"]) or None,
                                       reply_to_message_id=message.message_id)
                    else:
                        raise
            else:
                bot.send_photo(message.chat.id, data["image"], caption=caption or None,
                               reply_to_message_id=message.message_id)

            try:
                bot.delete_message(message.chat.id, status.message_id)
            except Exception:
                pass

        except requests.exceptions.Timeout:
            bot.edit_message_text("❌ Pinterest javob bermadi (timeout). Birozdan keyin qayta urinib ko'ring.",
                                  message.chat.id, status.message_id, parse_mode="HTML")
        except requests.exceptions.RequestException as e:
            logger.error(f"Request xato {url}: {e}")
            bot.edit_message_text("❌ Linkni ochib bo'lmadi. Link to'g'riligini tekshiring.",
                                  message.chat.id, status.message_id, parse_mode="HTML")
        except Exception as e:
            logger.exception(f"Kutilmagan xato {url}: {e}")
            bot.edit_message_text(f"❌ Xatolik yuz berdi. Qaytadan urinib ko'ring.",
                                  message.chat.id, status.message_id, parse_mode="HTML")


@bot.message_handler(func=lambda m: True, content_types=["text"])
def handle_other(message):
    # link bo'lmagan matnlar uchun yo'riqnoma
    if message.text.startswith("/"):
        return
    bot.reply_to(message, "📎 Menga <b>Pinterest link</b> yuboring.\nMisol: <code>https://pin.it/XXrbrYAhO</code>")


def main():
    logger.info("Bot ishga tushmoqda...")
    try:
        me = bot.get_me()
        logger.info(f"Bot ulandi: @{me.username} ({me.first_name})")
    except Exception as e:
        logger.error(f"Token xato yoki internet yo'q: {e}")
        print("❌ Bot tokeni ishlamadi. BOT_TOKEN ni tekshiring.")
        return
    print(f"✅ Bot ishlamoqda: @{me.username}. To'xtatish: Ctrl+C")
    bot.infinity_polling(timeout=30, long_polling_timeout=30, skip_pending=True)


if __name__ == "__main__":
    main()
