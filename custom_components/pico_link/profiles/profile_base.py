# profiles/profile_base.py
from __future__ import annotations
from typing import Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from ..controller import PicoController


class PicoProfile(Protocol):
    """
    Every profile must support:
    - __init__(controller)
    - handle_press()
    - handle_release()
    """

    def __init__(self, controller: "PicoController") -> None:
        ...

    def handle_press(self, button: str) -> None:
        ...

    def handle_release(self, button: str) -> None:
        ...
