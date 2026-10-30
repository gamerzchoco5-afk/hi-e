import re
import unicodedata
from datetime import date
from email_validator import validate_email, EmailNotValidError
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def clean_text(value: str):
    value = unicodedata.normalize("NFC", value).strip()
    if any(unicodedata.category(c) == "Cc" and c not in "\n\t" for c in value):
        raise ValueError("Control characters are not allowed")
    return value


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class Credentials(Input):
    username: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("username")
    @classmethod
    def username_format(cls, value):
        value = value.strip().lower()
        if "@" in value:
            try:
                return validate_email(
                    value, check_deliverability=False
                ).normalized.lower()
            except EmailNotValidError:
                raise ValueError("Enter a valid email address")
        if not re.fullmatch(r"[a-z0-9_]{3,24}", value):
            raise ValueError("Use 3–24 letters, numbers or underscores")
        return value


class Register(Credentials):
    email: str = Field(max_length=254)
    date_of_birth: date

    @field_validator("email")
    @classmethod
    def email_format(cls, value):
        try:
            return validate_email(
                value.strip(), check_deliverability=False
            ).normalized.lower()
        except EmailNotValidError:
            raise ValueError("Enter a valid email address")

    @model_validator(mode="after")
    def registration_rules(self):
        from wire_common.config import settings

        if not re.fullmatch(r"[a-z0-9_]{3,24}", self.username):
            raise ValueError("Use 3–24 letters, numbers or underscores for username")
        today = date.today()
        age = (
            today.year
            - self.date_of_birth.year
            - (
                (today.month, today.day)
                < (self.date_of_birth.month, self.date_of_birth.day)
            )
        )
        if not settings().minimum_age <= age <= 120:
            raise ValueError("Check your date of birth; Wire requires age 13 or older")
        return self

    display_name: str = Field(min_length=1, max_length=40)

    @field_validator("display_name")
    @classmethod
    def display(cls, value):
        value = clean_text(value)
        if not value or "\n" in value:
            raise ValueError("Enter a display name")
        return value

    @field_validator("password")
    @classmethod
    def strength(cls, value):
        if (
            len(set(value.strip())) < 4
            or any(
                value.lower()
                == (value[:n].lower() * ((len(value) + n - 1) // n))[: len(value)]
                for n in range(1, 5)
            )
            or re.fullmatch(
                r"(?:password|qwerty|letmein|welcome|admin)[0-9!@#$]*", value.lower()
            )
            or len(value) < 12
            or not value.strip()
            or value.lower() in {"password1234", "123456789012", "qwerty123456"}
        ):
            raise ValueError("Use a unique password of 12–128 characters")
        return value


class ProfileEdit(Input):
    username: str = Field(min_length=3, max_length=24)
    display_name: str = Field(min_length=1, max_length=40)
    bio: str = Field(default="", max_length=300)
    pronouns: str = Field(default="", max_length=30)

    @field_validator("username")
    @classmethod
    def username_only(cls, value):
        value = value.strip().lower()
        if not re.fullmatch(r"[a-z0-9_]{3,24}", value):
            raise ValueError("Use 3–24 letters, numbers or underscores")
        return value

    _display = field_validator("display_name")(Register.display.__func__)
    _texts = field_validator("bio", "pronouns")(clean_text)


class PostCreate(Input):
    body: str = Field(min_length=1, max_length=10000)
    kind: Literal["note", "article"] = "note"
    title: str = Field(default="", max_length=160)
    parent_id: int | None = Field(default=None, gt=0)
    client_id: str = Field(pattern=r"^[a-f0-9-]{36}$")
    _texts = field_validator("body", "title")(clean_text)

    @model_validator(mode="after")
    def limits(self):
        if not self.body:
            raise ValueError("Write something first")
        if self.kind == "note" and (len(self.body) > 500 or self.title):
            raise ValueError("Notes allow 500 characters and no title")
        if self.kind == "article" and (not self.title or self.parent_id):
            raise ValueError("Articles need a title and cannot be replies")
        return self


class ReportInput(Input):
    reason: str = Field(min_length=3, max_length=500)
    _text = field_validator("reason")(clean_text)

    @model_validator(mode="after")
    def nonempty(self):
        if len(self.reason) < 3:
            raise ValueError("Describe the problem")
        return self


class PasswordChange(Input):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)
    _strength = field_validator("new_password")(Register.strength.__func__)


class DeleteAccount(Input):
    password: str = Field(min_length=1, max_length=128)


class RecoveryInput(Input):
    username: str = Field(min_length=3, max_length=254)
    code: str = Field(min_length=32, max_length=50)
    new_password: str = Field(min_length=12, max_length=128)
    _identity = field_validator("username")(Credentials.username_format.__func__)
    _strength = field_validator("new_password")(Register.strength.__func__)


class EmailCodeInput(Input):
    code: str = Field(pattern=r"^\d{8}$")


class SettingsEdit(Input):
    message_requests: bool
    show_activity: bool
