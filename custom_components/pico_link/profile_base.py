from typing import Protocol


class PicoProfile(Protocol):
    """
    Each profile must implement these two methods so the controller
    can call them without type checker errors.
    """

    def handle_press(self, button: str) -> None:
        ...

    def handle_release(self, button: str) -> None:
        ...
