from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from .db import Database


router = Router()

BOT_QUESTION = "Какой у вас опыт работы с Python?"


class RegistrationStates(StatesGroup):
    waiting_for_full_name = State()
    waiting_for_answer = State()


def setup_handlers(db: Database) -> Router:
    """
    Фабрика, возвращающая настроенный роутер.
    """

    @router.message(CommandStart())
    async def cmd_start(message: Message, state: FSMContext) -> None:
        await state.clear()
        await message.answer(
            "Здравствуйте! Пожалуйста, отправьте ваше ФИО одной строкой."
        )
        await state.set_state(RegistrationStates.waiting_for_full_name)

    @router.message(RegistrationStates.waiting_for_full_name)
    async def process_full_name(message: Message, state: FSMContext) -> None:
        full_name = message.text.strip() if message.text else ""
        if not full_name:
            await message.answer("Похоже, вы отправили пустое сообщение. Введите ФИО.")
            return

        await state.update_data(full_name=full_name)
        await message.answer(
            f"Спасибо, {full_name}!\n\n"
            f"Теперь ответьте, пожалуйста, на вопрос:\n\n{BOT_QUESTION}"
        )
        await state.set_state(RegistrationStates.waiting_for_answer)

    @router.message(RegistrationStates.waiting_for_answer, F.text)
    async def process_answer(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        full_name = data.get("full_name")
        answer = message.text.strip() if message.text else ""

        if not full_name:
            await message.answer(
                "Не удалось найти ваши данные. Давайте начнём сначала: отправьте /start."
            )
            await state.clear()
            return

        db.upsert_user(
            telegram_id=message.from_user.id,
            full_name=full_name,
            question=BOT_QUESTION,
            answer=answer,
        )

        await message.answer(
            "Спасибо за ваш ответ! Данные сохранены в базе.\n"
            "Вы можете снова ввести /start, чтобы обновить свои данные."
        )
        await state.clear()

    return router

