import logging
import asyncio
import os
import json
import base64
import tempfile
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import gspread
from oauth2client.service_account import ServiceAccountCredentials

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === НАСТРОЙКИ ===
TOKEN = "8913360916:AAGJXB9E3FAuta0og4bRYtNxwWC0UCz2Cgg"
SHEET_NAME = "Задачи Бот таблица"
CREDENTIALS_FILE = "/Users/sofiasadykova/telegram_bot/credentials.json"
MANAGER_ID = 6691703913  # Telegram ID руководителя (София)

# Подключение к Google Sheets
EMPLOYEE_SHEETS = ["Ратмила", "Елизавета", "Софа", "Настя", "София", "Карина", "Алиса"]

def get_gspread_client():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    b64 = os.environ.get("GOOGLE_CREDENTIALS_B64")
    if b64:
        creds_json = base64.b64decode(b64).decode("utf-8")
        creds_dict = json.loads(creds_json)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    else:
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
    return gspread.authorize(creds)

def get_sheet(tab_name=None):
    client = get_gspread_client()
    spreadsheet = client.open(SHEET_NAME)
    if tab_name:
        return spreadsheet.worksheet(tab_name)
    return spreadsheet.sheet1

def get_all_employee_sheets():
    client = get_gspread_client()
    spreadsheet = client.open(SHEET_NAME)
    sheets = []
    for name in EMPLOYEE_SHEETS:
        try:
            sheets.append((name, spreadsheet.worksheet(name)))
        except Exception:
            pass
    return sheets

# Получить задачи сотрудника по Telegram ID (ищет по всем вкладкам)
def get_tasks_for_user(telegram_id):
    tasks = []
    for name, sheet in get_all_employee_sheets():
        rows = sheet.get_all_records()
        for i, row in enumerate(rows, start=2):
            if str(row.get("Telegram ID", "")) == str(telegram_id):
                tasks.append({"row": i, "sheet_name": name, **row})
    return tasks

# Отметить задачу выполненной
def mark_task_done(row_number, sheet_name=None):
    sheet = get_sheet(sheet_name)
    headers = sheet.row_values(1)
    status_col = headers.index("Статус") + 1
    sheet.update_cell(row_number, status_col, "Выполнено")

# Сохранить Telegram ID пользователя в таблицу
def save_telegram_id(name, telegram_id):
    try:
        sheet = get_sheet(name)
        rows = sheet.get_all_records()
        headers = sheet.row_values(1)
        telegram_id_col = headers.index("Telegram ID") + 1
        # Записываем ID в первую строку с данными или создаём запись
        if rows:
            for i, row in enumerate(rows, start=2):
                if not row.get("Telegram ID"):
                    sheet.update_cell(i, telegram_id_col, str(telegram_id))
                    return True
            # Все строки уже имеют ID, обновим первую
            sheet.update_cell(2, telegram_id_col, str(telegram_id))
            return True
        else:
            # Пустая вкладка — добавим строку с ID
            sheet.append_row([name, "", "", "", "", str(telegram_id), ""])
            return True
    except Exception:
        return False

# === КОМАНДЫ БОТА ===

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MANAGER_ID:
        await update.message.reply_text("Эта команда только для руководителя.")
        return
    if not context.args:
        await update.message.reply_text("Напиши: /vsem Текст сообщения")
        return
    text = " ".join(context.args)
    sent = 0
    failed = 0
    for sheet_name, sheet in get_all_employee_sheets():
        try:
            rows = sheet.get_all_records()
            tid = ""
            for row in rows:
                t = str(row.get("Telegram ID", "")).strip()
                if t:
                    tid = t
                    break
            if tid:
                await context.bot.send_message(chat_id=int(tid), text=f"📢 {text}")
                sent += 1
            else:
                failed += 1
        except Exception:
            failed += 1
    await update.message.reply_text(f"Отправлено: {sent} чел. Не доставлено: {failed} (не зарегистрированы).")



async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    telegram_id = user.id
    logger.info(f"USER ID: {telegram_id} | Имя: {user.first_name} {user.last_name}")
    tasks = get_tasks_for_user(telegram_id)

    if tasks:
        await show_tasks(update, context, tasks)
    else:
        await update.message.reply_text(
            f"Привет, {user.first_name}! 👋\n\n"
            "Сюда будут приходить твои рабочие задачи и напоминалки о дедлайнах.\n\n"
            "📌 Инструкция:\n\n"
            "1️⃣ Зарегистрируйся — напиши своё имя так, как оно записано у @ratmila:\n"
            "/moe_imya Имя Фамилия\n\n"
            "2️⃣ Посмотри свои задачи:\n"
            "/zadachi\n\n"
            "3️⃣ Когда выполнишь задачу — нажми кнопку ✅ под ней. Рук сразу увидит это в таблице.\n\n"
            "🔔 Напоминания приходят автоматически — за 24 часа и за 1 час до дедлайна.\n\n"
            "Если возникнут вопросы — обращайся к Софии."
        )

async def set_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Напиши: /moe_imya ИмяФамилия")
        return
    name = " ".join(context.args)
    telegram_id = update.effective_user.id
    success = save_telegram_id(name, telegram_id)
    if success:
        await update.message.reply_text(
            f"Отлично! Я запомнил тебя как {name}.\n"
            "Теперь напиши /zadachi чтобы увидеть свои задачи."
        )
    else:
        await update.message.reply_text(
            f"Не нашёл сотрудника с именем '{name}' в таблице.\n"
            "Проверь написание или обратись к руководителю."
        )

async def tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    tasks = get_tasks_for_user(telegram_id)
    if not tasks:
        await update.message.reply_text(
            "Задач не найдено. Убедись что твой Telegram ID записан в таблице.\n"
            "Если нет — напиши /moe_imya ИмяФамилия"
        )
        return
    await show_tasks(update, context, tasks)

async def show_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE, tasks):
    pending = [t for t in tasks if t.get("Статус", "") != "Выполнено"]
    done = [t for t in tasks if t.get("Статус", "") == "Выполнено"]

    text = "📋 *Твои задачи:*\n\n"
    keyboard = []

    if pending:
        text += "*Не выполнено:*\n"
        for task in pending:
            deadline = task.get("Дедлайн", "—")
            status = task.get("Статус", "")
            status_icon = "🔄" if status == "В работе" else "🔴"
            text += f"{status_icon} {task['Задача']} — до {deadline}\n"
            sn = task.get("sheet_name", "")
            keyboard.append([
                InlineKeyboardButton(
                    f"🔄 В работе: {task['Задача'][:25]}",
                    callback_data=f"inprogress_{task['row']}_{sn}"
                ),
                InlineKeyboardButton(
                    f"✅ Готово",
                    callback_data=f"done_{task['row']}_{sn}"
                )
            ])
    else:
        text += "Все задачи выполнены! 🎉\n"

    if done:
        text += f"\n*Выполнено:* {len(done)} задач ✓"

    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)

def mark_task_in_progress(row_number, sheet_name=None):
    sheet = get_sheet(sheet_name)
    headers = sheet.row_values(1)
    status_col = headers.index("Статус") + 1
    sheet.update_cell(row_number, status_col, "В работе")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("done_"):
        parts = query.data.split("_", 2)
        row = int(parts[1])
        sheet_name = parts[2] if len(parts) > 2 else None
        sheet = get_sheet(sheet_name)
        task_name = sheet.cell(row, 3).value
        mark_task_done(row, sheet_name)
        await query.edit_message_text("✅ Задача отмечена как выполненная! Молодец!")
        await context.bot.send_message(
            chat_id=MANAGER_ID,
            text=f"✅ Задача выполнена!\n\n📌 {task_name}\nСотрудник: {query.from_user.first_name}"
        )
    elif query.data.startswith("inprogress_"):
        parts = query.data.split("_", 2)
        row = int(parts[1])
        sheet_name = parts[2] if len(parts) > 2 else None
        sheet = get_sheet(sheet_name)
        task_name = sheet.cell(row, 3).value
        mark_task_in_progress(row, sheet_name)
        await query.edit_message_text("🔄 Отлично! Задача отмечена как 'В работе'.")
        await context.bot.send_message(
            chat_id=MANAGER_ID,
            text=f"🔄 Задача взята в работу!\n\n📌 {task_name}\nСотрудник: {query.from_user.first_name}"
        )

# === УВЕДОМЛЕНИЯ О НОВЫХ ЗАДАЧАХ ===

async def notify_new_tasks(context: ContextTypes.DEFAULT_TYPE):
    try:
        for sheet_name, sheet in get_all_employee_sheets():
            try:
                rows = sheet.get_all_records()
                headers = sheet.row_values(1)
                notified_col = headers.index("Уведомлено") + 1
                telegram_id_col = headers.index("Telegram ID") + 1

                # Берём Telegram ID из любой строки где он есть
                sheet_tid = ""
                for row in rows:
                    tid = str(row.get("Telegram ID", "")).strip()
                    if tid:
                        sheet_tid = tid
                        break

                for i, row in enumerate(rows, start=2):
                    task = str(row.get("Задача", "")).strip()
                    deadline = str(row.get("Дедлайн", "")).strip()
                    notified = str(row.get("Уведомлено", "")).strip()
                    telegram_id = str(row.get("Telegram ID", "")).strip() or sheet_tid

                    if not task or notified == "Да" or not telegram_id:
                        continue

                    if not str(row.get("Telegram ID", "")).strip() and telegram_id:
                        sheet.update_cell(i, telegram_id_col, telegram_id)

                    try:
                        await context.bot.send_message(
                            chat_id=int(telegram_id),
                            text=f"📬 *Новая задача!*\n\n"
                                 f"📌 {task}\n"
                                 f"⏰ Дедлайн: {deadline}\n\n"
                                 f"Напиши /zadachi чтобы увидеть все свои задачи.",
                            parse_mode="Markdown"
                        )
                        sheet.update_cell(i, notified_col, "Да")
                    except Exception:
                        pass
            except Exception as e:
                logger.error(f"Ошибка в вкладке {sheet_name}: {e}")
    except Exception as e:
        logger.error(f"Ошибка при уведомлении о новых задачах: {e}")

# === НАПОМИНАНИЯ ===

async def send_reminders(context: ContextTypes.DEFAULT_TYPE):
    try:
        now = datetime.now()
        for sheet_name, sheet in get_all_employee_sheets():
            try:
                rows = sheet.get_all_records()
                sheet_tid = ""
                for row in rows:
                    tid = str(row.get("Telegram ID", "")).strip()
                    if tid:
                        sheet_tid = tid
                        break

                for row in rows:
                    telegram_id = str(row.get("Telegram ID", "")).strip() or sheet_tid
                    status = str(row.get("Статус", "")).strip()
                    deadline_str = str(row.get("Дедлайн", "")).strip()
                    task = str(row.get("Задача", "")).strip()

                    if not telegram_id or status == "Выполнено" or not deadline_str or not task:
                        continue

                    try:
                        deadline = datetime.strptime(deadline_str, "%Y-%m-%d %H:%M")
                    except ValueError:
                        try:
                            deadline = datetime.strptime(deadline_str, "%Y-%m-%d")
                        except ValueError:
                            continue

                    diff = deadline - now
                    if timedelta(hours=23) < diff <= timedelta(hours=24):
                        await context.bot.send_message(
                            chat_id=int(telegram_id),
                            text=f"⏰ Напоминание!\n\nЗавтра дедлайн по задаче:\n*{task}*\n\nДо: {deadline_str}",
                            parse_mode="Markdown"
                        )
                    elif timedelta(minutes=50) < diff <= timedelta(hours=1):
                        await context.bot.send_message(
                            chat_id=int(telegram_id),
                            text=f"🔔 Через час дедлайн!\n\n*{task}*\n\nДо: {deadline_str}",
                            parse_mode="Markdown"
                        )
            except Exception as e:
                logger.error(f"Ошибка напоминания в вкладке {sheet_name}: {e}")
    except Exception as e:
        logger.error(f"Ошибка при отправке напоминаний: {e}")

# === ЕЖЕДНЕВНЫЙ ОТЧЁТ ===

async def daily_report(context: ContextTypes.DEFAULT_TYPE):
    try:
        now = datetime.now()
        pending = []
        overdue = []
        done_today = []

        for sheet_name, sheet in get_all_employee_sheets():
          rows = sheet.get_all_records()
          for row in rows:
            status = str(row.get("Статус", "")).strip()
            task = str(row.get("Задача", "")).strip()
            employee = str(row.get("Сотрудник", "")).strip()
            deadline_str = str(row.get("Дедлайн", "")).strip()

            if not task:
                continue

            try:
                deadline = datetime.strptime(deadline_str, "%Y-%m-%d %H:%M")
            except ValueError:
                try:
                    deadline = datetime.strptime(deadline_str, "%Y-%m-%d")
                except ValueError:
                    deadline = None

            if status == "Выполнено":
                done_today.append(f"✅ {employee}: {task}")
            elif deadline and deadline < now:
                overdue.append(f"🚨 {employee}: {task} (было до {deadline_str})")
            else:
                pending.append(f"🔴 {employee}: {task} (до {deadline_str})")

        text = f"📊 *Ежедневный отчёт — {now.strftime('%d.%m.%Y')}*\n\n"

        if overdue:
            text += "🚨 *Просрочено:*\n" + "\n".join(overdue) + "\n\n"
        if pending:
            text += "🔴 *В процессе:*\n" + "\n".join(pending) + "\n\n"
        if done_today:
            text += "✅ *Выполнено:*\n" + "\n".join(done_today)

        if not overdue and not pending and not done_today:
            text += "Задач нет."

        await context.bot.send_message(chat_id=MANAGER_ID, text=text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Ошибка при отправке отчёта: {e}")

# === УВЕДОМЛЕНИЕ О ПРОСРОЧКЕ ===

async def check_overdue(context: ContextTypes.DEFAULT_TYPE):
    try:
        now = datetime.now()
        for sheet_name, sheet in get_all_employee_sheets():
            try:
                rows = sheet.get_all_records()
                headers = sheet.row_values(1)

                for i, row in enumerate(rows, start=2):
                    status = str(row.get("Статус", "")).strip()
                    task = str(row.get("Задача", "")).strip()
                    deadline_str = str(row.get("Дедлайн", "")).strip()

                    if status == "Выполнено" or status == "Просрочено" or not task or not deadline_str:
                        continue

                    try:
                        deadline = datetime.strptime(deadline_str, "%Y-%m-%d %H:%M")
                    except ValueError:
                        try:
                            deadline = datetime.strptime(deadline_str, "%Y-%m-%d")
                        except ValueError:
                            continue

                    if deadline < now:
                        status_col = headers.index("Статус") + 1
                        sheet.update_cell(i, status_col, "Просрочено")
                        await context.bot.send_message(
                            chat_id=MANAGER_ID,
                            text=f"🚨 *Задача просрочена!*\n\n"
                                 f"👤 Сотрудник: {sheet_name}\n"
                                 f"📌 Задача: {task}\n"
                                 f"⏰ Дедлайн был: {deadline_str}",
                            parse_mode="Markdown"
                        )
            except Exception as e:
                logger.error(f"Ошибка проверки просрочек в вкладке {sheet_name}: {e}")
    except Exception as e:
        logger.error(f"Ошибка при проверке просрочек: {e}")

# === ЗАПУСК ===

def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("zadachi", tasks_command))
    app.add_handler(CommandHandler("moe_imya", set_name))
    app.add_handler(CommandHandler("vsem", broadcast))
    app.add_handler(CallbackQueryHandler(button_callback))

    job_queue = app.job_queue
    job_queue.run_repeating(send_reminders, interval=1800, first=10)
    job_queue.run_repeating(notify_new_tasks, interval=60, first=5)
    job_queue.run_repeating(check_overdue, interval=1800, first=15)
    job_queue.run_daily(daily_report, time=__import__("datetime").time(9, 0, 0))

    print("Бот запущен! Нажми Ctrl+C чтобы остановить.")
    app.run_polling()

if __name__ == "__main__":
    main()
