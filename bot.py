import logging
import asyncio
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
def get_sheet():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
    client = gspread.authorize(creds)
    return client.open(SHEET_NAME).sheet1

# Получить задачи сотрудника по Telegram ID
def get_tasks_for_user(telegram_id):
    sheet = get_sheet()
    rows = sheet.get_all_records()
    tasks = []
    for i, row in enumerate(rows, start=2):
        if str(row.get("Telegram ID", "")) == str(telegram_id):
            tasks.append({"row": i, **row})
    return tasks

# Отметить задачу выполненной
def mark_task_done(row_number):
    sheet = get_sheet()
    headers = sheet.row_values(1)
    status_col = headers.index("Статус") + 1
    sheet.update_cell(row_number, status_col, "Выполнено")

# Сохранить Telegram ID пользователя в таблицу
def save_telegram_id(name, telegram_id):
    sheet = get_sheet()
    rows = sheet.get_all_records()
    headers = sheet.row_values(1)
    telegram_id_col = headers.index("Telegram ID") + 1
    for i, row in enumerate(rows, start=2):
        employee = str(row.get("Сотрудник", "")).strip().lower()
        if employee == name.strip().lower() and not row.get("Telegram ID"):
            sheet.update_cell(i, telegram_id_col, str(telegram_id))
            return True
    return False

# === КОМАНДЫ БОТА ===

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
            keyboard.append([
                InlineKeyboardButton(
                    f"🔄 В работе: {task['Задача'][:25]}",
                    callback_data=f"inprogress_{task['row']}"
                ),
                InlineKeyboardButton(
                    f"✅ Готово",
                    callback_data=f"done_{task['row']}"
                )
            ])
    else:
        text += "Все задачи выполнены! 🎉\n"

    if done:
        text += f"\n*Выполнено:* {len(done)} задач ✓"

    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)

def mark_task_in_progress(row_number):
    sheet = get_sheet()
    headers = sheet.row_values(1)
    status_col = headers.index("Статус") + 1
    sheet.update_cell(row_number, status_col, "В работе")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("done_"):
        row = int(query.data.split("_")[1])
        sheet = get_sheet()
        task_name = sheet.cell(row, 3).value
        mark_task_done(row)
        await query.edit_message_text("✅ Задача отмечена как выполненная! Молодец!")
        await context.bot.send_message(
            chat_id=MANAGER_ID,
            text=f"✅ Задача выполнена!\n\n📌 {task_name}\nСотрудник: {query.from_user.first_name}"
        )
    elif query.data.startswith("inprogress_"):
        row = int(query.data.split("_")[1])
        sheet = get_sheet()
        task_name = sheet.cell(row, 3).value
        mark_task_in_progress(row)
        await query.edit_message_text("🔄 Отлично! Задача отмечена как 'В работе'.")
        await context.bot.send_message(
            chat_id=MANAGER_ID,
            text=f"🔄 Задача взята в работу!\n\n📌 {task_name}\nСотрудник: {query.from_user.first_name}"
        )

# === УВЕДОМЛЕНИЯ О НОВЫХ ЗАДАЧАХ ===

async def notify_new_tasks(context: ContextTypes.DEFAULT_TYPE):
    try:
        sheet = get_sheet()
        rows = sheet.get_all_records()
        headers = sheet.row_values(1)
        notified_col = headers.index("Уведомлено") + 1
        telegram_id_col = headers.index("Telegram ID") + 1

        # Собираем словарь имя -> telegram_id из всех строк где ID уже есть
        name_to_id = {}
        for row in rows:
            name = str(row.get("Сотрудник", "")).strip()
            tid = str(row.get("Telegram ID", "")).strip()
            if name and tid:
                name_to_id[name] = tid

        for i, row in enumerate(rows, start=2):
            name = str(row.get("Сотрудник", "")).strip()
            task = str(row.get("Задача", "")).strip()
            deadline = str(row.get("Дедлайн", "")).strip()
            notified = str(row.get("Уведомлено", "")).strip()
            telegram_id = str(row.get("Telegram ID", "")).strip()

            if not task or notified == "Да":
                continue

            # Если ID нет — пробуем найти по имени
            if not telegram_id and name in name_to_id:
                telegram_id = name_to_id[name]
                sheet.update_cell(i, telegram_id_col, telegram_id)

            if not telegram_id:
                continue

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
        logger.error(f"Ошибка при уведомлении о новых задачах: {e}")

# === НАПОМИНАНИЯ ===

async def send_reminders(context: ContextTypes.DEFAULT_TYPE):
    try:
        sheet = get_sheet()
        rows = sheet.get_all_records()
        now = datetime.now()

        for i, row in enumerate(rows, start=2):
            telegram_id = str(row.get("Telegram ID", "")).strip()
            status = str(row.get("Статус", "")).strip()
            deadline_str = str(row.get("Дедлайн", "")).strip()
            task = str(row.get("Задача", "")).strip()

            if not telegram_id or status == "Выполнено" or not deadline_str:
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
        logger.error(f"Ошибка при отправке напоминаний: {e}")

# === ЕЖЕДНЕВНЫЙ ОТЧЁТ ===

async def daily_report(context: ContextTypes.DEFAULT_TYPE):
    try:
        sheet = get_sheet()
        rows = sheet.get_all_records()
        now = datetime.now()

        pending = []
        overdue = []
        done_today = []

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
        sheet = get_sheet()
        rows = sheet.get_all_records()
        headers = sheet.row_values(1)
        now = datetime.now()

        for i, row in enumerate(rows, start=2):
            status = str(row.get("Статус", "")).strip()
            task = str(row.get("Задача", "")).strip()
            employee = str(row.get("Сотрудник", "")).strip()
            deadline_str = str(row.get("Дедлайн", "")).strip()
            telegram_id = str(row.get("Telegram ID", "")).strip()

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
                         f"👤 Сотрудник: {employee}\n"
                         f"📌 Задача: {task}\n"
                         f"⏰ Дедлайн был: {deadline_str}",
                    parse_mode="Markdown"
                )
    except Exception as e:
        logger.error(f"Ошибка при проверке просрочек: {e}")

# === ЗАПУСК ===

def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("zadachi", tasks_command))
    app.add_handler(CommandHandler("moe_imya", set_name))
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
