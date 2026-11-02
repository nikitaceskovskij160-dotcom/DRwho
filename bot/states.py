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
    complaints = State()
    diagnosis = State()
    prescriptions = State()
    comment = State()


class AddNote(StatesGroup):
    text = State()


class CreateReminder(StatesGroup):
    when = State()
    text = State()
