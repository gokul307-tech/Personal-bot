from contextvars import ContextVar


_current_user_id: ContextVar[int] = ContextVar("sage_current_user_id", default=1)


def current_user_id() -> int:
    return _current_user_id.get()


def set_current_user_id(user_id: int):
    return _current_user_id.set(user_id)


def reset_current_user_id(token) -> None:
    _current_user_id.reset(token)