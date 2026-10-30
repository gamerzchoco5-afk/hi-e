"""Request bodies for the chat endpoints."""

import unicodedata

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Start(Input):
    username: str = Field(pattern=r"^[a-z0-9_]{3,24}$")


class Send(Input):
    body: str = Field(min_length=1, max_length=2000)
    client_id: str = Field(pattern=r"^[a-f0-9-]{36}$")

    @field_validator("body")
    @classmethod
    def body_text(cls, value):
        value = unicodedata.normalize("NFC", value).strip()
        if not value or any(
            unicodedata.category(c) == "Cc" and c not in "\n\t" for c in value
        ):
            raise ValueError("Enter a message")
        return value


class Read(Input):
    message_id: int = Field(gt=0)


class ChatReportInput(Input):
    reason: str = Field(min_length=3, max_length=500)
