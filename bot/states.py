from aiogram.fsm.state import State, StatesGroup


class Registration(StatesGroup):
    invite = State()
    consent = State()
    full_name = State()
    specialty = State()
    timezone = State()


class AddPatient(StatesGroup):
    full_name = State()
    birth_date = State()
    sex = State()
    phone = State()
    notes = State()


class EditPatient(StatesGroup):
    value = State()


class SearchPatient(StatesGroup):
    query = State()


class AddVisit(StatesGroup):
    step = State()
    draft = State()
    field_value = State()


class AddTemplate(StatesGroup):
    title = State()
    kind = State()
    step = State()


class EditTemplate(StatesGroup):
    value = State()


class AddExam(StatesGroup):
    title = State()
    content = State()


class AskAi(StatesGroup):
    question = State()


class AddNote(StatesGroup):
    text = State()


class CreateReminder(StatesGroup):
    when = State()
    text = State()
