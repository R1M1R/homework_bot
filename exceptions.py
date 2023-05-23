class WrongResponseCode(Exception):
    """Неверный ответ API."""

    pass


class NotForSend(Exception):
    """Исключение не для пересылки в telegram."""

    pass


class RequestExceptionError(Exception):
    """Ошибка запроса."""


class UnknownStatusError(Exception):
    """Ошибка: Неизвестный статус в homework_status."""

    def __init__(self, message):
        """Конструктор класса."""
        self.message = message
        super().__init__(self.message)

    def __str__(self):
        """Форматируем вывод сообщения об ошибке."""
        return f'{type(self).__name__} --> {self.message}'
