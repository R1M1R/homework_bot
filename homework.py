import logging
import sys
import os
import time
import requests
import telegram

from dotenv import load_dotenv

load_dotenv()


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


class RequestExceptionError(Exception):
    """Ошибка запроса."""


def get_stream_handler():
    """Обработчик логирования."""
    stream_handler = logging.StreamHandler(stream=sys.stdout)
    stream_handler.setFormatter(
        logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    )
    return stream_handler


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(get_stream_handler())


def log_and_send_error_to_Telegram(bot, message):
    """Логирование и направление ошибки в Телеграм."""
    logger.error(message)
    send_message(bot, message)


def check_tokens() -> bool:
    """Проверка наличия ключей."""
    if not PRACTICUM_TOKEN:
        logger.critical('Отсутствует обязательная переменная PRACTICUM_TOKEN')
    elif not TELEGRAM_TOKEN:
        logger.critical('Отсутствует обязательная переменная TELEGRAM_TOKEN')
    elif not TELEGRAM_CHAT_ID:
        logger.critical(
            'Отсутствует обязательная переменная TELEGRAM_CHAT_ID')
    else:
        logger.debug('Проверка ключей проведена')
    return PRACTICUM_TOKEN and TELEGRAM_TOKEN and TELEGRAM_CHAT_ID


def get_api_answer(timestamp):
    """Направление запроса и получение ответа."""
    timestamp = timestamp or int(time.time())
    params = {'from_date': timestamp}
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=params)
        if response.status_code != 200:
            raise Exception(f'Сбой при обращении к URL {response.request.url}'
                            f'; код ответа: {response.status_code} - '
                            f'{response.reason}; параметры: {params}')
        logger.debug('Ответ от сервера получен')
        response = response.json()
    except requests.exceptions.RequestException as request_error:
        code_api_msg = f'Код ответа API (RequestException): {request_error}'
        logger.error(code_api_msg)
        raise RequestExceptionError(code_api_msg) from request_error
    except TypeError:
        raise Exception(
            'Ответ от сервера не соответствует формату JSON'
            'и не может быть обработан'
        )
    return response


def check_response(response):
    """Проверка ответа."""
    if isinstance(response, dict):
        logger.debug(
            f'Тип данных ответа сервера правильный: {type(response)}'
        )
    else:
        raise TypeError(
            f'Неправильный тип данных ответа сервера: {type(response)}'
        )
    if 'homeworks' not in response:
        raise KeyError(
            f'Ответ сервера не содержит ключ "homeworks": {response}'
        )
    if response['homeworks']:
        logger.debug(
            'Ответ сервера содержит сведения о домашних работах'
        )
    else:
        logger.info(
            'Ответ сервера не содержит сведения о домашних работах'
        )
    if 'current_date' not in response:
        raise KeyError(
            'Ответ сервера не содержит текущую дату '
            f'(ключ "current_date"): {response}'
        )
    if response['current_date']:
        logger.debug(
            'Ответ сервера содержит текущую дату (ключ "current_date")'
        )
    if isinstance(response['homeworks'], list):
        logger.debug(
            'Проверен тип данных ответа сервера с ключом "homeworks": '
            f'{type(response["homeworks"])}'
        )
        return response.get('homeworks')
    else:
        raise TypeError(
            'Неправильный тип данных ответа сервера с ключом "homeworks":'
            f'{type(response["homeworks"])}'
        )


def parse_status(homework):
    """Определение статуса работы."""
    homework_name = homework.get("homework_name")
    homework_status = homework.get("status")
    verdict = HOMEWORK_VERDICTS.get(homework.get('status'))
    if homework_status not in HOMEWORK_VERDICTS:
        message_homework_status = "Такого статуса не существует"
        raise KeyError(message_homework_status)
    if "homework_name" not in homework:
        message_homework_name = "Такого имени не существует"
        raise KeyError(message_homework_name)
    if not verdict:
        raise KeyError(
            'Отсутствует документированный статус'
            f'проверки работы "{homework_name}"'
        )
    message = (
        'Изменился статус проверки работы'
        f' "{homework_name}".\n{verdict}'
    )
    return message


def send_message(bot, message):
    """Направление сообщения в Телеграм..."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug(
            f'Сообщение в Telegram отправлено: {message}')
    except telegram.TelegramError as telegram_error:
        logger.error(
            f'Сообщение в Telegram не отправлено: {telegram_error}')


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        sys.exit('Проблемы с токенами! Выход из программы')
    prior_hw, prior_error, prior_message = {}, '', ''
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time()) - 30 * 24 * 60 * 60
    while True:
        try:
            api_answer = get_api_answer(timestamp)
            hw = check_response(api_answer)
            if len(hw) == 0:
                hw = prior_hw
            if hw != prior_hw:
                message = parse_status(hw[0])
                if message != prior_message:
                    send_message(bot, message)
                    prior_message = message
                prior_hw = hw
            else:
                logger.debug(
                    'Сообщение в Телеграм не отправлено, обновлений нет'
                )
            timestamp = api_answer['current_date']
        except Exception as error:
            if str(error) == prior_error:
                logger.error(error)
            else:
                log_and_send_error_to_Telegram(bot=bot, message=error)
                prior_error = str(error)
        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
