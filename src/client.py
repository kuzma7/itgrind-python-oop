import hashlib
import hmac
import secrets
import uuid
from datetime import date, datetime
from enum import Enum

from src.exceptions import InvalidOperationError


class ClientStatus(Enum):
    ACTIVE = "active"
    BLOCKED = "blocked"


class Client:
    def __init__(self, full_name: str, birth_date: date, contacts: dict[str, str], password: str):
        if not isinstance(full_name, str) or not full_name.strip():
            raise InvalidOperationError("Full name must be a non-empty string")

        if not isinstance(birth_date, date) or isinstance(birth_date, datetime):
            raise InvalidOperationError("Birth date must be a date object")

        today = date.today()

        if birth_date > today:
            raise InvalidOperationError("Birth date cannot be in the future")

        age = today.year - birth_date.year

        if (today.month, today.day) < (birth_date.month, birth_date.day):
            age -= 1

        if age < 18:
            raise InvalidOperationError("Client must be at least 18 years old")

        if not isinstance(contacts, dict) or not contacts:
            raise InvalidOperationError("Contacts must be a non-empty dictionary")

        for key, value in contacts.items():
            if not isinstance(key, str) or not key.strip():
                raise InvalidOperationError("Invalid contact type")

            if not isinstance(value, str) or not value.strip():
                raise InvalidOperationError("Invalid contact value")

        self.client_id = uuid.uuid4().hex[:8]
        self.full_name = full_name.strip()
        self.birth_date = birth_date
        self.contacts = contacts.copy()
        self.status = ClientStatus.ACTIVE
        self.account_ids: list[str] = []
        if not isinstance(password, str) or not password:
            raise InvalidOperationError("Password cannot be empty")

        self.failed_login_attempts = 0

        self._password_salt = secrets.token_bytes(16)
        self._password_hash = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            self._password_salt,
            200_000,
        )

    def verify_password(self, password: str) -> bool:
        if not isinstance(password, str):
            return False

        password_hash = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            self._password_salt,
            200_000,
        )

        return hmac.compare_digest(self._password_hash, password_hash)
