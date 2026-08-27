from aiogram.fsm.state import State, StatesGroup


class Onboarding(StatesGroup):
    name = State()
    district = State()


class NewTraining(StatesGroup):
    route = State()
    date = State()
    time = State()
    details = State()
    confirm = State()


class NewRoute(StatesGroup):
    title = State()
    location = State()
    start_note = State()
    distance = State()
    elevation = State()
    map_url = State()
    waypoints = State()


class RouteDescribe(StatesGroup):
    waypoints = State()


class CancelTraining(StatesGroup):
    custom_reason = State()


class MoveTraining(StatesGroup):
    datetime_input = State()


class TemplateEdit(StatesGroup):
    new_text = State()
    edit_text = State()
