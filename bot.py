import os
import logging
import sqlite3
import pathlib
import httpx
import openai
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ChatAction
from aiogram.filters import Command
from datetime import datetime
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv
from keyboards import main_keyboard



class LegalBot:
    def __init__(self):
        load_dotenv()
        self._setup_logging()
        self.bot = Bot(token=os.getenv('TELEGRAM_BOT_TOKEN'))
        self.dp = Dispatcher(storage=MemoryStorage())
        self.client = self._init_openai_client()
        self.prompts = self._load_prompts()
        self._register_handlers()

    def _setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)

    @staticmethod
    def _init_openai_client():
        return openai.AsyncOpenAI(
            api_key=os.getenv('OPENAI_API_KEY'),
            http_client=httpx.AsyncClient(
                # proxy=os.getenv('PROXY_URL', None),
                timeout=30.0
            )
        )

    def _load_prompts(self):
        prompts_dir = 'prompts'
        return {
            'law_labor': self._load_prompt(f'{prompts_dir}/work.md'),
            'law_housing': self._load_prompt(f'{prompts_dir}/housing.md'),
            'law_civil': self._load_prompt(f'{prompts_dir}/civil.md'),
            'law_family': self._load_prompt(f'{prompts_dir}/family.md'),
            'generate_contract': self._load_prompt(f'{prompts_dir}/contract.md'),
            'legal_assistant': self._load_prompt(f'{prompts_dir}/legal_prompt.md')
        }

    def _load_prompt(self, file_path: str) -> str:
        try:
            return pathlib.Path(file_path).read_text(encoding='utf-8')
        except FileNotFoundError:
            self.logger.error(f'Prompt file not found: {file_path}')
            return ''

    def _register_handlers(self):
        self.dp.message(Command('start'))(self._send_welcome)
        self.dp.message(Command('help'))(self._send_help)
        self.dp.message()(self._handle_message)
        self.dp.callback_query(lambda c: c.data == 'generate_again')(self._handle_regenerate)
        self.dp.callback_query(lambda c: c.data.startswith('law_') or c.data.startswith('generate'))(
            self._handle_law_question)
        self.dp.callback_query(lambda c: c.data == 'clear_history')(self._clear_history)

    @staticmethod
    async def _send_welcome(message: types.Message):
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
        await message.reply('Выберите категорию:', reply_markup=main_keyboard)

    @staticmethod
    async def _send_help(message: types.Message):
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



    async def _handle_message(self, message: types.Message):
        await self.generate_and_save_response(
            user_id=message.from_user.id,
            chat_id=message.chat.id,
            user_message=message.text
        )

    async def _handle_regenerate(self, callback_query: types.CallbackQuery):
        await self.bot.answer_callback_query(callback_query.id)
        history = self.get_conversation_history(callback_query.from_user.id)
        last_user_message = next(
            (m['content'] for m in reversed(history) if m['role'] == 'user'),
            None
        )

        if last_user_message:
            await self.generate_and_save_response(
                user_id=callback_query.from_user.id,
                chat_id=callback_query.message.chat.id,
                user_message=last_user_message,
                reply_to_message_id=callback_query.message.message_id,
                is_regenerate=True
            )

    async def _handle_law_question(self, callback_query: types.CallbackQuery):
        await self.bot.answer_callback_query(callback_query.id)
        if callback_query.data in self.prompts:
            await self.generate_and_save_response(
                user_id=callback_query.from_user.id,
                chat_id=callback_query.message.chat.id,
                user_message=callback_query.data,
                reply_to_message_id=callback_query.message.message_id,
                prompt=self.prompts[callback_query.data]
            )

    async def _clear_history(self, callback_query: types.CallbackQuery):
        conn = sqlite3.connect('chat_history.db')
        conn.execute('DELETE FROM messages WHERE user_id = ?', (callback_query.from_user.id,))
        conn.commit()
        conn.close()
        await self.bot.answer_callback_query(callback_query.id, 'История диалога очищена')


    async def generate_and_save_response(self, user_id: int, chat_id: int, user_message: str,
                                         reply_to_message_id: int = None, is_regenerate: bool = False,
                                         prompt: str = None):
        try:
            await self.bot.send_chat_action(chat_id, ChatAction.TYPING)

            # Обработка сообщения и сохранение в историю
            processed_message = f'{user_message} (variant 2)' if is_regenerate else user_message
            self.save_message(user_id, [{'role': 'user', 'content': processed_message}])

            # Формирование контекста для GPT
            messages = self._prepare_gpt_messages(user_id, prompt)

            # Отправка запроса к OpenAI
            response = await self._call_gpt_api(messages, is_regenerate)

            # Обработка и сохранение ответа
            answer = response.choices[0].message.content
            self.save_message(user_id, [{'role': 'assistant', 'content': answer}])

            # Отправка ответа пользователю
            await self._send_response(
                chat_id=chat_id,
                message_id=reply_to_message_id,
                text=answer
            )

        except Exception as e:
            self.logger.error(f"Error in generate_and_save_response: {e}")
            await self.bot.send_message(chat_id, "⚠️ Произошла ошибка при обработке запроса")

    def _prepare_gpt_messages(self, user_id: int, prompt: str = None) -> list:
        history = self.get_conversation_history(user_id)
        messages = [{'role': 'system', 'content': self.prompts['legal_assistant']}]
        messages.extend(history)
        if prompt:
            messages.append({'role': 'system', 'content': prompt})
        return messages

    async def _call_gpt_api(self, messages: list, is_regenerate: bool = False):
        return await self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.9 if is_regenerate else 0.7,
            max_tokens=800,
        )

    async def _send_response(self, chat_id: int, text: str, message_id: int = None):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🧹 Очистить историю", callback_data="clear_history")],
            [InlineKeyboardButton(text='Сгенерировать снова', callback_data='generate_again')]
        ])

        if message_id:
            await self.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=keyboard
            )
        else:
            await self.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=keyboard
            )

    @staticmethod
    def save_message(user_id: int, messages: list):
        conn = sqlite3.connect('chat_history.db')
        cursor = conn.cursor()
        for message in messages:
            cursor.execute(
                'INSERT INTO messages (user_id, role, content, timestamp) VALUES (?, ?, ?, ?)',
                (user_id, message['role'], message['content'], datetime.now().isoformat())
            )
        conn.commit()
        conn.close()

    @staticmethod
    def get_conversation_history(user_id: int, limit: int = 10) -> list:
        conn = sqlite3.connect('chat_history.db')
        cursor = conn.cursor()
        cursor.execute(
            'SELECT role, content FROM messages WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?',
            (user_id, limit)
        )
        history = [{'role': row[0], 'content': row[1]} for row in cursor.fetchall()]
        conn.close()
        return history[::-1]

    async def run(self):
        await self.bot.delete_webhook(drop_pending_updates=True)
        await self.dp.start_polling(self.bot)


