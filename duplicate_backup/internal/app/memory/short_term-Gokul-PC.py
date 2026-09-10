from typing import Any


class ShortTermMemory:

    def __init__(
        self,
        max_messages: int = 20,
    ):

        self.max_messages = max_messages

        self.messages: list[
            dict[str, Any]
        ] = []

    def add(
        self,
        role: str,
        content: str,
    ):

        self.messages.append(
            {
                "role": role,
                "content": content,
            }
        )

        if len(self.messages) > self.max_messages:

            self.messages = self.messages[
                -self.max_messages:
            ]

    def get_messages(self):

        return list(self.messages)

    def clear(self):

        self.messages.clear()