"""What the agent wants done on the phone, in phone pixels."""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class Intent:
    kind: str                                    # tap | double_tap | swipe | press | drag | release
    points: list[tuple[float, float]] = field(default_factory=list)  # phone pixels
    text: str = ""                               # instruction for a person doing it by hand


class Actuator(Protocol):
    def tap(self, x: float, y: float) -> None: ...
    def double_tap(self, x: float, y: float) -> None: ...
    def swipe(self, x1: float, y1: float, x2: float, y2: float, fast: bool = False) -> None: ...
    def press(self, x: float, y: float) -> None: ...
    def drag_to(self, x: float, y: float) -> None: ...
    def release(self) -> None: ...
