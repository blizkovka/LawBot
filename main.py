import asyncio
import os
import logging
import sqlite3
import pathlib
import codecs
import httpx
import openai
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ChatAction
from aiogram.filters import Command
from datetime import datetime

from aiogram.fsm.storage.memory import MemoryStorage, SimpleEventIsolation
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv
from db import init_db
from keyboards import main_keyboard



load_dotenv()
# Инициализация бота и диспетчера
bot = Bot(token=os.getenv('TELEGRAM_BOT_TOKEN'))
dp = Dispatcher(
    storage=MemoryStorage(),
    events_isolation=SimpleEventIsolation()
)

# Настройка логгирования
logging.basicConfig(level=logging.INFO)

# Настройка OpenAI
# client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
client = openai.AsyncOpenAI(
    api_key=os.getenv('OPENAI_API_KEY'),
    http_client=httpx.AsyncClient(
        proxy=os.getenv('PROXY_URL'),
    )
)

# подгрузка промпта из каталога
def load_prompt(file_path: str) -> str:
    try:
        return pathlib.Path(file_path).read_text(encoding='utf-8')
    except FileNotFoundError:
        logging.error(f'File {file_path} not found')
        return 'None'

LEGAL_ASSISTANT_PROMPT = load_prompt('prompts/legal_prompt.md')
PROMPTS = {
        'law_labor': open('prompts/work.md').read(),
        'law_housing': open('prompts/housing.md').read(),
        'law_civil': open('prompts/civil.md').read(),
        'law_family': open('prompts/family.md').read(),
        'generate_contract': codecs.open( "prompts/contract.md", "r", "utf_8_sig" )
    }


# Обработчик команды /start
@dp.message(Command('start'))
async def send_welcome(message: types.Message):
    welcome_text = """
    👋 Добро пожаловать в *Юрист GPT*!

    Я - ваш виртуальный юридический помощник. Задайте мне любой юридический вопрос, и я постараюсь помочь.

    Примеры вопросов:
    - Как составить договор аренды?
    - Какие документы нужны для развода?
    - Что делать при незаконном увольнении?

    ⚠️ *Важно*: мои ответы носят информационный характер и не заменяют консультацию живого юриста.
    """
    await message.reply(welcome_text)
    await message.reply('Выберите категорию: ', reply_markup=main_keyboard)


# Обработчик команды /help
@dp.message(Command('help'))
async def send_help(message: types.Message):
    help_text = """
    📝 *Как пользоваться ботом:*

    Просто напишите ваш юридический вопрос, и я постараюсь помочь.

    Некоторые примеры вопросов:
    - Как подать в суд на работодателя?
    - Какие права у арендатора квартиры?
    - Как оформить наследство?

    ⚠️ *Ограничения:*
    - Я не могу представлять вас в суде
    - Мои ответы носят справочный характер
    - Для сложных случаев рекомендую обратиться к живому юристу

    Используйте /start для повторного приветствия.
    """
    await message.reply(help_text)


async def generate_and_save_response(
        bot: Bot,
        user_id: int,
        chat_id: int,
        user_message: str,
        reply_to_message_id: int = None,
        is_regenerate: bool = False,
        prompt: str | None = None
):
    try:
        await bot.send_chat_action(chat_id, ChatAction.TYPING)
        processed_message = f'{user_message} (variant 2)' if is_regenerate else user_message
        save_message(user_id, [{'role': 'user', 'content': processed_message}])
        history = get_conversation_history(user_id)
        messages = [{'role': 'system', 'content': LEGAL_ASSISTANT_PROMPT}] + history
        if prompt:
            messages.append({'role': 'system', 'content': prompt})

        temperature = 0.9 if is_regenerate else 0.7

        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=temperature,
            max_tokens=600
        )

        answer = response.choices[0].message.content
        save_message(user_id, [{'role': 'system', 'content': answer}])

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🧹 Очистить историю", callback_data="clear_history")],
            [InlineKeyboardButton(text='Сгенерировать снова', callback_data='generate_again')]
        ])

        if reply_to_message_id:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=reply_to_message_id,
                text=answer,
                reply_markup=keyboard
            )
        else:
            await bot.send_message(
                chat_id=chat_id,
                text=answer,
                reply_markup=keyboard,
                reply_to_message_id=reply_to_message_id
            )

        return True

    except Exception as e:
        logging.error(f"Error in generate_and_save_response: {e}")
        await bot.send_message(
            chat_id=chat_id,
            text="⚠️ Произошла ошибка при обработке запроса"
        )
        return False


@dp.message()
async def message_handler(message: types.Message):
    """Обработчик текстовых сообщений"""
    await generate_and_save_response(
        bot=bot,
        user_id=message.from_user.id,
        chat_id=message.chat.id,
        user_message=message.text
    )

@dp.callback_query(lambda c: c.data == 'generate_again')
async def handle_regenerate(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)

    # Получаем последний запрос пользователя из истории
    history = get_conversation_history(callback_query.from_user.id)
    last_user_message = next(
        (m['content'] for m in history[::-1] if m['role'] == 'user'),
        None
    )

    if not last_user_message:
        await callback_query.answer("Не найдено предыдущего запроса", show_alert=True)
        return

    await generate_and_save_response(
        bot=bot,
        user_id=callback_query.from_user.id,
        chat_id=callback_query.message.chat.id,
        user_message=last_user_message,
        reply_to_message_id=callback_query.message.message_id,
        is_regenerate=True
    )


# добавить для каждой области свой промпт в дополнение к существующему

@dp.callback_query(lambda c: c.data.startswith('law_') | c.data.startswith('generate'))
async def process_law_question(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)

    if callback_query.data:
        await generate_and_save_response(
            bot=bot,
            user_id=callback_query.from_user.id,
            chat_id=callback_query.message.chat.id,
            user_message=callback_query.text,
            reply_to_message_id=callback_query.message.message_id,
            prompt=PROMPTS[callback_query.data]
        )


@dp.callback_query(lambda c: c.data == 'clear_history')
async def clear_history(callback_query: types.CallbackQuery):
    conn = sqlite3.connect('chat_history.db')
    cursor = conn.cursor()

    cursor.execute('''
    DELETE FROM messages
    WHERE user_id = ?
    ''',
                   (callback_query.from_user.id,)
    )

    conn.commit()
    conn.close()
    await bot.answer_callback_query(callback_query.id, 'История диалога очищена')


def save_message(user_id: int, messages: list):
    conn = sqlite3.connect('chat_history.db')
    cursor = conn.cursor()

    for message in messages:
        cursor.execute('''
        INSERT INTO messages (user_id, role, content, timestamp) 
        VALUES (?, ?, ?, ?)
        ''',
        (user_id, message['role'], message['content'], datetime.now().isoformat()))

    conn.commit()
    conn.close()

def get_conversation_history(user_id: int, limit: int = 10):
    conn = sqlite3.connect('chat_history.db')
    cursor = conn.cursor()

    cursor.execute('''
    SELECT role, content FROM messages
    WHERE user_id = ?
    ORDER BY timestamp DESC
    LIMIT ?''',
    (user_id, limit))

    history = [{'role': row[0], 'content': row[1]} for row in cursor.fetchall()]
    conn.close()

    return history[::-1]

async def main():
    init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot, skip_updates=True)



# Запуск бота
if __name__ == '__main__':
    asyncio.run(main())

