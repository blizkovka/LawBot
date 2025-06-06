from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

main_keyboard = ReplyKeyboardMarkup(
    resize_keyboard=True,
    one_time_keyboard=False,
    keyboard=[
        [
            KeyboardButton(text='📄 Составить документ', callback_data='generate_contract')
        ],
        [
            KeyboardButton(text='💼 Трудовое право', callback_data='law_labor'),
            KeyboardButton(text='🏠 Жилищное право', callback_data='law_housing'),
        ],
        [
            KeyboardButton(text='👪 Семейное право', callback_data='law_family'),
            KeyboardButton(text='💰 Гражданское право', callback_data='law_civil')
        ]
    ]
)



