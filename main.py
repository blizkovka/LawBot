import asyncio

from bot import LegalBot
from db import init_db


# Запуск бота
if __name__ == '__main__':
    init_db()
    bot = LegalBot()
    asyncio.run(bot.run())

