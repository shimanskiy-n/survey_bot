from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from .db import Database


router = Router()


class UserStates(StatesGroup):
    waiting_for_full_name = State()
    waiting_for_answer = State()


class AdminStates(StatesGroup):
    waiting_for_new_question_text = State()
    waiting_for_deactivate_question_id = State()


def _get_text_from_command(message: Message) -> str | None:
    """
    В `aiogram 3` удобнее парсить аргументы команды вручную.
    """

    raw = message.text or ""
    parts = raw.split(maxsplit=1)
    if len(parts) < 2:
        return None
    value = parts[1].strip()
    return value or None


def _is_admin_message(
    user_data: tuple[str, int] | None,
) -> bool:
    return bool(user_data and int(user_data[1]) == 1)


def _admin_menu_kb() -> InlineKeyboardMarkup:
    # Inline-кнопки для админских функций (работают через callback_query).
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Список вопросов",
                    callback_data="admin:list_questions",
                ),
                InlineKeyboardButton(
                    text="Добавить вопрос",
                    callback_data="admin:add_question",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Деактивировать вопрос",
                    callback_data="admin:deactivate_question",
                )
            ],
        ]
    )


def setup_handlers(db: Database, *, admin_telegram_id: int | None) -> Router:
    async def send_active_questions(
        message: Message,
        state: FSMContext,
        *,
        is_admin: bool,
    ) -> None:
        questions = db.get_active_questions()
        if not questions:
            await message.answer("Активных вопросов пока нет.")
            await state.clear()
            return

        await state.update_data(questions=questions, question_index=0)
        await state.set_state(UserStates.waiting_for_answer)

        _, first_text = questions[0]
        await message.answer(
            f"Ответьте на вопрос:\n\n{first_text}",
            reply_markup=_admin_menu_kb() if is_admin else None,
        )

    @router.message(CommandStart())
    async def cmd_start(message: Message, state: FSMContext) -> None:
        await state.clear()
        telegram_id = message.from_user.id

        user = db.get_user(telegram_id)
        if not user:
            await message.answer(
                "Здравствуйте! Пожалуйста, отправьте ваше ФИО одной строкой."
            )
            await state.set_state(UserStates.waiting_for_full_name)
            return

        full_name, is_admin = user
        # Bootstrap admin rights:
        # 1) If `ADMIN_TELEGRAM_ID` is set and matches current user - mark them as admin.
        # 2) If there are no admins in DB yet - first authorised user becomes admin.
        if (admin_telegram_id and telegram_id == admin_telegram_id and is_admin == 0) or (
            not admin_telegram_id and is_admin == 0 and db.count_admins() == 0
        ):
            db.set_user_admin(telegram_id=telegram_id, is_admin=True)
            is_admin = 1
        await message.answer(
            f"Здравствуйте, {full_name}! Сейчас отвечайте на активные вопросы."
        )
        await send_active_questions(message, state, is_admin=bool(is_admin))

    @router.message(UserStates.waiting_for_full_name, F.text)
    async def process_full_name(message: Message, state: FSMContext) -> None:
        full_name = (message.text or "").strip()
        if not full_name:
            await message.answer("Похоже, вы отправили пустое сообщение. Введите ФИО.")
            return

        telegram_id = message.from_user.id
        user_exists = db.get_user(telegram_id) is not None
        if user_exists:
            # На всякий случай, если пользователь повторно попал в состояние.
            await state.clear()
            return

        is_admin = 0
        if admin_telegram_id and telegram_id == admin_telegram_id:
            is_admin = 1
        elif db.count_users() == 0:
            # Удобный bootstrap: первый пользователь в базе становится админом.
            is_admin = 1

        db.upsert_user(telegram_id=telegram_id, full_name=full_name, is_admin=is_admin)

        await message.answer(
            f"Спасибо, {full_name}! Сейчас отвечайте на активные вопросы."
        )
        await send_active_questions(message, state, is_admin=bool(is_admin))

    @router.message(Command("admin"))
    async def cmd_admin_menu(message: Message, state: FSMContext) -> None:
        telegram_id = message.from_user.id
        user = db.get_user(telegram_id)
        if not _is_admin_message(user):
            await message.answer("Недостаточно прав.")
            return
        await message.answer("Админ-меню:", reply_markup=_admin_menu_kb())

    @router.message(UserStates.waiting_for_answer, F.text)
    async def process_answer(message: Message, state: FSMContext) -> None:
        telegram_id = message.from_user.id
        is_admin = _is_admin_message(db.get_user(telegram_id))
        data = await state.get_data()

        questions = data.get("questions") or []
        question_index = int(data.get("question_index", 0))

        if question_index >= len(questions):
            await state.clear()
            await message.answer("Сессия завершена. Нажмите /start, чтобы начать заново.")
            return

        question_id, _question_text = questions[question_index]
        answer_text = (message.text or "").strip()
        if not answer_text:
            await message.answer("Похоже, ответ пустой. Напишите ответ ещё раз.")
            return

        db.upsert_answer(
            telegram_id=telegram_id,
            question_id=int(question_id),
            answer_text=answer_text,
        )

        question_index += 1
        if question_index < len(questions):
            await state.update_data(question_index=question_index)
            _, next_text = questions[question_index]
            await message.answer(
                f"Следующий вопрос:\n\n{next_text}",
                reply_markup=_admin_menu_kb() if is_admin else None,
            )
            return

        await state.clear()
        await message.answer(
            "Спасибо! Ваши ответы сохранены в базе.",
            reply_markup=_admin_menu_kb() if is_admin else None,
        )

    @router.message(Command("list_questions"))
    async def admin_list_questions(message: Message, state: FSMContext) -> None:
        await state.clear()
        telegram_id = message.from_user.id
        user = db.get_user(telegram_id)
        if not _is_admin_message(user):
            await message.answer("Недостаточно прав.")
            return

        questions = db.list_questions()
        if not questions:
            await message.answer("В базе пока нет вопросов.")
            return

        lines: list[str] = []
        for q_id, text, active, order in questions:
            status = "ACTIVE" if active == 1 else "INACTIVE"
            lines.append(f"#{q_id} [{status}] order={order}\n{text}")

        out = "\n\n".join(lines)
        if len(out) > 3900:
            out = out[:3900] + "\n..."
        await message.answer(out, reply_markup=_admin_menu_kb())

    @router.callback_query(F.data == "admin:list_questions")
    async def cb_admin_list_questions(call: CallbackQuery, state: FSMContext) -> None:
        telegram_id = call.from_user.id
        user = db.get_user(telegram_id)
        if not _is_admin_message(user):
            await call.answer("Недостаточно прав.", show_alert=True)
            return

        await call.answer()
        questions = db.list_questions()
        if not questions:
            if call.message:
                await call.message.edit_text(
                    "В базе пока нет вопросов.",
                    reply_markup=_admin_menu_kb(),
                )
            return

        lines: list[str] = []
        for q_id, text, active, order in questions:
            status = "ACTIVE" if active == 1 else "INACTIVE"
            lines.append(f"#{q_id} [{status}] order={order}\n{text}")

        out = "\n\n".join(lines)
        if len(out) > 3900:
            out = out[:3900] + "\n..."

        if call.message:
            await call.message.edit_text(out, reply_markup=_admin_menu_kb())

    @router.callback_query(F.data == "admin:add_question")
    async def cb_admin_add_question(call: CallbackQuery, state: FSMContext) -> None:
        telegram_id = call.from_user.id
        user = db.get_user(telegram_id)
        if not _is_admin_message(user):
            await call.answer("Недостаточно прав.", show_alert=True)
            return

        await call.answer()
        await state.clear()
        await state.set_state(AdminStates.waiting_for_new_question_text)
        if call.message:
            await call.message.edit_text("Введите текст нового вопроса одним сообщением.")

    @router.callback_query(F.data == "admin:deactivate_question")
    async def cb_admin_deactivate_question(
        call: CallbackQuery,
        state: FSMContext,
    ) -> None:
        telegram_id = call.from_user.id
        user = db.get_user(telegram_id)
        if not _is_admin_message(user):
            await call.answer("Недостаточно прав.", show_alert=True)
            return

        await call.answer()
        await state.clear()
        await state.set_state(AdminStates.waiting_for_deactivate_question_id)
        if call.message:
            await call.message.edit_text(
                "Укажите id вопроса. Пример:  /deactivate_question 1"
            )

    @router.message(Command("add_question"))
    async def admin_add_question(message: Message, state: FSMContext) -> None:
        await state.clear()
        telegram_id = message.from_user.id
        user = db.get_user(telegram_id)
        if not _is_admin_message(user):
            await message.answer("Недостаточно прав.")
            return

        question_text = _get_text_from_command(message)
        if question_text:
            q_id = db.create_question(question_text)
            await message.answer(
                f"Вопрос создан: #{q_id} (активен).",
                reply_markup=_admin_menu_kb(),
            )
            return

        await message.answer("Введите текст нового вопроса одним сообщением.")
        await state.set_state(AdminStates.waiting_for_new_question_text)

    @router.message(AdminStates.waiting_for_new_question_text, F.text)
    async def admin_add_question_text(message: Message, state: FSMContext) -> None:
        telegram_id = message.from_user.id
        user = db.get_user(telegram_id)
        if not _is_admin_message(user):
            await state.clear()
            await message.answer("Недостаточно прав.")
            return

        question_text = (message.text or "").strip()
        if not question_text:
            await message.answer("Текст вопроса не может быть пустым.")
            return

        q_id = db.create_question(question_text)
        await state.clear()
        await message.answer(
            f"Вопрос создан: #{q_id} (активен).",
            reply_markup=_admin_menu_kb(),
        )

    @router.message(Command("deactivate_question"))
    async def admin_deactivate_question(message: Message, state: FSMContext) -> None:
        await state.clear()
        telegram_id = message.from_user.id
        user = db.get_user(telegram_id)
        if not _is_admin_message(user):
            await message.answer("Недостаточно прав.")
            return

        raw = _get_text_from_command(message)
        if not raw:
            await message.answer("Укажите id вопроса. Пример: /deactivate_question 1")
            await state.set_state(AdminStates.waiting_for_deactivate_question_id)
            return

        try:
            q_id = int(raw)
        except ValueError:
            await message.answer("id вопроса должен быть числом.")
            return

        ok = db.set_question_active(q_id, is_active=False)
        if ok:
            await message.answer(
                f"Вопрос #{q_id} помечен как неактивный.",
                reply_markup=_admin_menu_kb(),
            )
        else:
            await message.answer(
                f"Вопрос #{q_id} не найден.",
                reply_markup=_admin_menu_kb(),
            )

    @router.message(AdminStates.waiting_for_deactivate_question_id, F.text)
    async def admin_deactivate_question_id(message: Message, state: FSMContext) -> None:
        telegram_id = message.from_user.id
        user = db.get_user(telegram_id)
        if not _is_admin_message(user):
            await state.clear()
            await message.answer("Недостаточно прав.")
            return

        raw = (message.text or "").strip()
        try:
            q_id = int(raw)
        except ValueError:
            await message.answer("id вопроса должен быть числом.")
            return

        ok = db.set_question_active(q_id, is_active=False)
        await state.clear()
        if ok:
            await message.answer(
                f"Вопрос #{q_id} помечен как неактивный.",
                reply_markup=_admin_menu_kb(),
            )
        else:
            await message.answer(
                f"Вопрос #{q_id} не найден.",
                reply_markup=_admin_menu_kb(),
            )

    return router

