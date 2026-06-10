from typing import Final

from prompt_toolkit.validation import Validator, ValidationError


class PriceValidator(Validator):
    def validate(self, document):
        text = document.text.strip()
        if text:
            try:
                price = float(text)
                if price <= 0:
                    raise ValidationError(
                        message="Цена должна быть больше 0", cursor_position=len(text)
                    )
            except ValueError as e:
                raise ValidationError(
                    message="Введите число", cursor_position=len(text)
                ) from e


class NonEmptyValidator(Validator):
    def __init__(self, message="Поле не может быть пустым"):
        self.message = message

    def validate(self, document):
        text = document.text.strip()
        if not text:
            raise ValidationError(message=self.message, cursor_position=0)


class YesNoValidator(Validator):
    YES_VALUES: Final[frozenset[str]] = frozenset(["y", "yes", "д", "да"])
    NO_VALUES: Final[frozenset[str]] = frozenset(["n", "no", "н", "нет"])
    ALL_VALUES: Final[frozenset[str]] = YES_VALUES | NO_VALUES

    @classmethod
    def is_yes(cls, answer: str) -> bool:
        return answer.lower() in cls.YES_VALUES

    @classmethod
    def is_no(cls, answer: str) -> bool:
        return answer.lower() in cls.NO_VALUES

    def validate(self, document):
        text = document.text.lower()
        if text not in self.ALL_VALUES:
            raise ValidationError(message="Введите y/n (yes/no)")


class ChoiceValidator(Validator):
    def __init__(
        self,
        choices: list[str],
        message: str = "Значение должно быть из списка. Используйте Tab для автодополнения.",
    ):
        self.choices = choices
        self.message = message

    def validate(self, document):
        text = document.text.strip()
        if text and text not in self.choices:
            raise ValidationError(message=self.message, cursor_position=len(text))
