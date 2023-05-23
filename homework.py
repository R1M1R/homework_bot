import logging
import sys
import os
import time
import requests
import telegram
from http import HTTPStatus
from exceptions import WrongResponseCode, NotForSend, UnknownStatusError
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
    logging.info('Проверка наличия всех токенов')
    return all([PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID])


def get_api_answer(timestamp):
    """Направление запроса и получение ответа."""
    timestamp = timestamp or int(time.time())
    request_params = {
        'url': ENDPOINT,
        'headers': HEADERS,
        'params': {'from_date': timestamp},
    }
    message = ('Начало запроса к API. Запрос: {url}, {headers}, {params}.'
               ).format(**request_params)
    logging.info(message)
    try:
        response = requests.get(**request_params)
        if response.status_code != HTTPStatus.OK:
            raise WrongResponseCode(
                f'Ответ API не возвращает 200. '
                f'Код ответа: {response.status_code}. '
                f'Причина: {response.reason}. '
                f'Текст: {response.text}.'
            )
        return response.json()
    except Exception as error:
        message = ('API не возвращает 200. Запрос: {url}, {headers}, {params}.'
                   ).format(**request_params)
        raise WrongResponseCode(message, error)


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
    verdict = HOMEWORK_VERDICTS.get(homework.get("status"))
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
    if homework is None:
        raise UnknownStatusError(
            f'Неизвестный статус "{homework_status}" '
            f'у работы "{homework_name}"')
    message = (
        'Изменился статус проверки работы "{homework_name}". {verdict}'
    ).format(
        homework_name=homework_name,
        verdict=HOMEWORK_VERDICTS[homework_status]
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
        message = 'Отсутствует токен. Бот остановлен!'
        logging.critical(message)
        sys.exit(message)
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    start_message = 'Бот начал работу'
    send_message(bot, start_message)
    logging.info(start_message)
    prev_msg = ''

    while True:
        try:
            response = get_api_answer(timestamp)
            timestamp = response.get(
                'current_date', int(time.time())
            )
            homeworks = check_response(response)
            if homeworks:
                message = parse_status(homeworks[0])
            else:
                message = 'Нет новых статусов'
            if message != prev_msg:
                send_message(bot, message)
                prev_msg = message
            else:
                logging.info(message)

        except NotForSend as error:
            message = f'Сбой в работе программы: {error}'
            logging.error(message, exc_info=True)

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logging.error(message, exc_info=True)
            if message != prev_msg:
                send_message(bot, message)
                prev_msg = message

        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        handlers=[
            logging.FileHandler(
                os.path.abspath('main.log'), mode='a', encoding='UTF-8'),
            logging.StreamHandler(stream=sys.stdout)],
        format='%(asctime)s, %(levelname)s, %(funcName)s, '
               '%(lineno)s, %(name)s, %(message)s'
    )
    main()
