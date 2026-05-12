from __future__ import annotations

try:
    import pygame as pygame  # type: ignore
    HAS_PYGAME = True
except Exception:  # pragma: no cover - used in headless training environments
    HAS_PYGAME = False

    class Rect:
        def __init__(self, x: int = 0, y: int = 0, width: int = 0, height: int = 0) -> None:
            self.x = int(x)
            self.y = int(y)
            self.width = int(width)
            self.height = int(height)

        @property
        def left(self) -> int:
            return self.x

        @property
        def right(self) -> int:
            return self.x + self.width

        @property
        def top(self) -> int:
            return self.y

        @property
        def bottom(self) -> int:
            return self.y + self.height

        @property
        def centerx(self) -> int:
            return self.x + self.width // 2

        @centerx.setter
        def centerx(self, value: int) -> None:
            self.x = int(value) - self.width // 2

        @property
        def centery(self) -> int:
            return self.y + self.height // 2

        @centery.setter
        def centery(self, value: int) -> None:
            self.y = int(value) - self.height // 2

        @property
        def center(self) -> tuple[int, int]:
            return self.centerx, self.centery

        @center.setter
        def center(self, value: tuple[int, int]) -> None:
            self.centerx, self.centery = value

        def colliderect(self, other: "Rect") -> bool:
            return not (
                self.right <= other.left
                or self.left >= other.right
                or self.bottom <= other.top
                or self.top >= other.bottom
            )

    class _PygameStub:
        Rect = Rect

    pygame = _PygameStub()
