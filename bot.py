"""
Телеграм-бот для проверки занятости юзернеймов БОТОВ.

Токен: 8765723335:AAE-XaH0oAu1VizrKNfmGjhCy2LYyGzxckU
"""

import asyncio
import logging
import os
import re

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
import requests

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

BOT_TOKEN = "8765723335:AAE-XaH0oAu1VizrKNfmGjhCy2LYyGzxckU"

# Пауза между запросами (в секундах)
REQUEST_DELAY = 0.1
# Лимит длины сообщения
TELEGRAM_MESSAGE_LIMIT = 3800

# Валидный юзернейм
BASENAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]{0,27}$")

STATUS_BULLET = {"free": "○", "taken": "●", "other": "⚠"}
STATUS_LABEL = {"free": "free", "taken": "taken", "other": "error"}


def extract_basenames(text: str) -> list[str]:
    """Достаём из сообщения все базовые имена."""
    raw_tokens = re.split(r"[\s,;]+", text.strip())
    names = []
    for token in raw_tokens:
        token = token.strip()
        if not token:
            continue
        token = token.replace("https://t.me/", "").replace("http://t.me/", "")
        token = token.lstrip("@")
        if token.lower().endswith("_bot"):
            token = token[:-4]
        elif token.lower().endswith("bot"):
            token = token[:-3]
        if token and BASENAME_RE.match(token):
            names.append(token)
    
    seen = set()
    unique = []
    for n in names:
        if n.lower() not in seen:
            seen.add(n.lower())
            unique.append(n)
    return unique


def check_exists(username: str) -> str:
    """Проверка через Telegram Bot API - username занят если найден любой чат."""
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getChat"
        params = {"chat_id": f"@{username}"}
        
        response = requests.get(url, params=params, timeout=5)
        data = response.json()
        
        if data.get("ok"):
            # Чат найден - username занят (пользователь, бот, канал, группа - все равно)
            chat_info = data.get("result", {})
            chat_type = chat_info.get("type", "")
            log.info(f"@{username}: найден (type={chat_type}), занят")
            return "taken"
        else:
            error_desc = data.get("description", "").lower()
            if "chat not found" in error_desc:
                log.info(f"@{username}: chat not found, свободен")
                return "free"
            elif "username is invalid" in error_desc or "username not occupied" in error_desc:
                log.info(f"@{username}: {error_desc}, свободен")
                return "free"
            else:
                log.warning(f"@{username}: ошибка API: {error_desc}")
                return "other"
                
    except requests.exceptions.Timeout:
        log.warning(f"@{username}: timeout")
        return "other"
    except requests.exceptions.RequestException as e:
        log.warning(f"@{username}: ошибка сети: {e}")
        return "other"
    except Exception as e:
        log.warning("Ошибка при проверке %s: %s", username, e)
        return "other"


def build_report(basenames: list[str], results: dict[str, dict[str, str]]) -> list[str]:
    """Строит отчёт."""
    free_count = taken_count = other_count = 0
    free_usernames: list[str] = []
    free_basenames: list[str] = []

    group_blocks: list[str] = []
    for basename in basenames:
        base_status = results[basename].get("base", "other")
        lines = [f"@{basename}"]
        
        base_bullet = STATUS_BULLET[base_status]
        base_label = STATUS_LABEL[base_status]
        lines.append(f"{base_bullet} @{basename} {base_label} (базовое)")
        
        if base_status == "free":
            free_basenames.append(basename)
            for suffix in ("bot", "_bot"):
                status = results[basename].get(suffix, "other")
                username = f"{basename}{suffix}"
                bullet = STATUS_BULLET[status]
                label = STATUS_LABEL[status]
                lines.append(f"{bullet} @{username} {label}")

                if status == "free":
                    free_count += 1
                    free_usernames.append(username)
                elif status == "taken":
                    taken_count += 1
                else:
                    other_count += 1
        else:
            taken_count += 2
            lines.append(f"● @{basename}bot taken (базовое занято)")
            lines.append(f"● @{basename}_bot taken (базовое занято)")
            
        group_blocks.append("\n".join(lines))

    summary = f"○ free {free_count}  ● taken {taken_count} · other {other_count}"
    separator = "──────────────"

    header = f"VALID REPORT\n\n{summary}\n\n{separator}"

    footer_lines = [separator, "", "Свободные базовые имена:"]
    if free_basenames:
        for u in free_basenames:
            footer_lines.append(f"@{u}")
    else:
        footer_lines.append("Свободных базовых имён нет")
    
    footer_lines.extend(["", "Свободные варианты с bot:"])
    if free_usernames:
        for u in free_usernames:
            footer_lines.append(f"@{u}")
    else:
        footer_lines.append("Свободных вариантов нет")
    footer = "\n".join(footer_lines)

    messages = []
    current = header
    for block in group_blocks:
        candidate = current + "\n\n" + block
        if len(candidate) > TELEGRAM_MESSAGE_LIMIT:
            messages.append(current)
            current = block
        else:
            current = candidate

    if len(current) + len(footer) + 2 > TELEGRAM_MESSAGE_LIMIT:
        messages.append(current)
        messages.append(footer)
    else:
        messages.append(current + "\n\n" + footer)

    return messages


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Пришли базовые имена для проверки (каждое с новой "
        "строки или через пробел/запятую), например:\n\n"
        "zalupa122\nkoch121\nfog229\n\n"
        "Я проверю базовые имена и варианты с суффиксами bot/_bot"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    basenames = extract_basenames(text)

    if not basenames:
        await update.message.reply_text(
            "Не нашёл ни одного подходящего базового имени. Имя должно "
            "начинаться с буквы и состоять из латинских букв, цифр и "
            "подчёркивания."
        )
        return

    status_msg = await update.message.reply_text(
        f"Проверяю {len(basenames)} базовых имён, подожди немного…"
    )

    try:
        results = {}
        total = len(basenames)
        
        for i, basename in enumerate(basenames):
            try:
                progress = f"Проверяю {i+1}/{total}: @{basename}…"
                await status_msg.edit_text(progress)
                
                base_status = check_exists(basename)
                results[basename] = {"base": base_status}
                
                if base_status == "free":
                    for suffix in ("bot", "_bot"):
                        username = f"{basename}{suffix}"
                        status = check_exists(username)
                        results[basename][suffix] = status
                else:
                    results[basename]["bot"] = "taken"
                    results[basename]["_bot"] = "taken"
                    
            except Exception as e:
                log.warning(f"Ошибка при проверке {basename}: {e}")
                results[basename] = {"base": "other", "bot": "other", "_bot": "other"}
        
        messages = build_report(basenames, results)
        await status_msg.edit_text(messages[0])
        for msg in messages[1:]:
            await update.message.reply_text(msg)
            
    except Exception as e:
        log.error(f"Ошибка при обработке сообщения: {e}")
        await status_msg.edit_text(
            f"Произошла ошибка при проверке. Попробуйте снова."
        )


def main():
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN не найден")

    # Увеличиваем таймауты соединения
    from telegram.request import HTTPXRequest
    request = HTTPXRequest(connection_pool_size=8, connect_timeout=30.0, read_timeout=30.0, write_timeout=30.0)
    
    app = Application.builder().token(BOT_TOKEN).request(request).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", start_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    log.info("Бот запущен, жду сообщений…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
