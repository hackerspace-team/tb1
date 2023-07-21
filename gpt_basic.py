#!/usr/bin/env python3

import os
import re
import sys

import enchant
from fuzzywuzzy import fuzz
import openai

import cfg
import utils
import my_dic
import my_ckt1031GPT


CUSTOM_MODELS = my_dic.PersistentDict('db/custom_models.pkl')

def ai_test() -> str:
    """
    """
    openai.api_key = cfg.key_test
    openai.api_base = cfg.openai_api_base_test
    
    #   text = open('1.txt', 'r').read()[:20000]
    text = 'Привет как дела'
    
    messages = [{"role": "system", "content": "Ты искусственный интеллект отвечающий на запросы юзера."},
                {"role": "user", "content": text}]

    current_model = cfg.model_test

    # тут можно добавить степень творчества(бреда) от 0 до 1 дефолт - temperature=0.5
    сompletion = openai.ChatCompletion.create(
        model = current_model,
        messages=messages,
        max_tokens=2000,
        temperature=0.5,
        timeout=180,
        stream=False
    )
    return сompletion["choices"][0]["message"]["content"]


def ai(prompt: str = '', temp: float = 0.5, max_tok: int = 2000, timeou: int = 120, messages = None,
       second = False, chat_id = None, model_to_use: str = '') -> str:
    """Сырой текстовый запрос к GPT чату, возвращает сырой ответ
    second - использовать ли второй гейт и ключ, для больших запросов
    """
    global CUSTOM_MODELS

    print(cfg.model, len(prompt))
    if second:
        openai.api_key = cfg.key2
        openai.api_base = cfg.openai_api_base2
    else:
        openai.api_key = cfg.key
        openai.api_base = cfg.openai_api_base

    if messages == None:
        assert prompt != '', 'prompt не может быть пустым'
        messages = [{"role": "system", "content": """Ты искусственный интеллект отвечающий на запросы юзера."""},
                    {"role": "user", "content": prompt}]

    current_model = cfg.model
    if chat_id and chat_id in CUSTOM_MODELS:
        current_model = CUSTOM_MODELS[chat_id]

    # использовать указанную модель если есть
    current_model = cfg.model if not model_to_use else model_to_use

    response = ''
    try:
        # тут можно добавить степень творчества(бреда) от 0 до 1 дефолт - temperature=0.5
        completion = openai.ChatCompletion.create(
            model = current_model,
            messages=messages,
            max_tokens=max_tok,
            temperature=temp,
            timeout=timeou
        )
        response = completion.choices[0].message.content
    except Exception as unknown_error1:
        print(unknown_error1)
        try:
            # тут можно добавить степень творчества(бреда) от 0 до 1 дефолт - temperature=0.5
            openai.api_key = cfg.reserve_key
            openai.api_base = cfg.reserve_openai_api_base
            completion = openai.ChatCompletion.create(
                model = current_model,
                messages=messages,
                max_tokens=max_tok,
                temperature=temp,
                timeout=timeou
            )
            response = completion.choices[0].message.content

            # меняем местами основной и резервный сервер что бы в следующий раз не натыкаться на упавший сервер
            # cfg.openai_api_base,         cfg.reserve_openai_api_base, cfg.key,         cfg.reserve_key = \
            # cfg.reserve_openai_api_base, cfg.openai_api_base,         cfg.reserve_key, cfg.key
        except Exception as unknown_error2:
            # если основной и резервный не сработали то последний вариант, он использует только модель из конфига
            print(unknown_error2)
            try:
                response = my_ckt1031GPT.ai(prompt, temp, max_tok, timeou, messages)
            except Exception as unknown_error3:
                print(unknown_error3)

    return check_and_fix_text(response)


def ai_compress(prompt: str, max_prompt: int  = 300, origin: str = 'user', force: bool = False) -> str:
    """сжимает длинное сообщение в чате для того что бы экономить память в контексте
    origin - чье сообщение, юзера или это ответ помощника. 'user' или 'assistant'
    force - надо ли сжимать сообщения которые короче чем заданная максимальная длинна. это надо что бы не сжать а просто резюмировать,
            превратить диалог в такое предложение что бы бинг его принял вместо диалога
    """
    assert origin in ('user', 'assistant', 'dialog')
    if len(prompt) > max_prompt or force:
        try:
            if origin == 'user':
                compressed_prompt = ai(f'Сократи текст до {max_prompt} символов так что бы сохранить смысл и важные детали. \
Этот текст является запросом юзера в переписке между юзером и ИИ. Используй короткие слова. Текст:\n{prompt}', max_tok = max_prompt)
            elif origin == 'assistant':
                compressed_prompt = ai(f'Сократи текст до {max_prompt} символов так что бы сохранить смысл и важные детали. \
Этот текст является ответом ИИ в переписке между юзером и ИИ. Используй короткие слова. Текст:\n{prompt}', max_tok = max_prompt)
            elif origin == 'dialog':
                compressed_prompt = ai(f'Резюмируй переписку между юзером и ассистентом до {max_prompt} символов, весь негативный контент исправь на нейтральный:\n{prompt}', max_tok = max_prompt)
            if len(compressed_prompt) < len(prompt) or force:
                return compressed_prompt
        except Exception as error:
            print(error)

        if len(prompt) > max_prompt:
            ziped = zip_text(prompt)
            if len(ziped) <= max_prompt:
                prompt = ziped
            else:
                prompt = prompt[:max_prompt]

    return prompt


def translate_text(text, fr = 'autodetect', to = 'ru'):
    """переводит текст с помощью GPT-чата, возвращает None при ошибке"""

    # если нет ключа то сразу отбой
    if not openai.api_key: return None
    
    prompt = f'Исправь явные опечатки в тексте и разорванные строки которые там могли появиться после плохого OCR, переведи текст с языка ({fr}) на язык ({to}), \
разбей переведенный текст на абзацы для удобного чтения по возможности сохранив оригинальное разбиение на строки и абзацы. \
Ссылки и другие непереводимые элементы из текста надо сохранить в переводе. Текст это всё (до конца) что идет после двоеточия. \
Покажи только перевод без оформления и отладочной информации. Текст:'
    prompt += text

    try:
        r = ai(prompt)
    except Exception as e:
        print(e)
        return None
    return r


def clear_after_ocr(text):
    """Получает текст после распознавания с картинки, пытается его восстановить, исправить ошибки распознавания"""

    # не работает пока что нормально
    # return text

    # если нет ключа то сразу отбой
    if not openai.api_key: return text

    prompt = 'Исправь явные ошибки и опечатки в тексте которые там могли появиться после плохого OCR. \
То что совсем плохо распозналось, бессмысленные символы, надо убрать. \
Важна точность, лучше оставить ошибку неисправленной если нет уверенности в том что это ошибка и её надо исправить именно так. \
Важно сохранить оригинальное разбиение на строки и абзацы. \
Покажи результат без оформления и отладочной информации. Текст:'
    prompt += text
    try:
        r = ai(prompt)
    except Exception as e:
        print(e)
        return text
    return r


def detect_ocr_command(text):
    """пытается понять является ли text командой распознать текст с картинки
    возвращает True, False
    """
    keywords = (
    'прочитай', 'читай', 'распознай', 'отсканируй', 'розпізнай', 'скануй', 'extract', 'identify', 'detect', 'ocr',
     'read', 'recognize', 'scan'
    )

    # сначала пытаемся понять по нечеткому совпадению слов
    if any(fuzz.ratio(text, keyword) > 70 for keyword in keywords): return True
    
    # пока что без GPT - ложные срабатывания ни к чему
    return False

    if not openai.api_key: return False
    
    k = ', '.join(keywords)
    p = f'Пользователь прислал в телеграм чат картинку с подписью ({text}). В чате есть бот которые распознает текст с картинок по просьбе пользователей. \
Тебе надо определить по подписи хочет ли пользователь что бы с этой картинки был распознан текст с помощью OCR или подпись на это совсем не указывает. \
Ответь одним словом без оформления - да или нет или непонятно.'
    r = ai(p).lower().strip(' .')
    print(r)
    if r == 'да': return True
    #elif r == 'нет': return False
    return False


def clear_after_stt(text):
    """Получает текст после распознавания из голосового сообщения, пытается его восстановить, исправить ошибки распознавания"""

    # не работает пока что нормально
    return text

    # если нет ключа то сразу отбой
    if not openai.api_key: return text

    prompt = f'Исправь явные ошибки распознавания голосового сообщения. \
Важна точность, лучше оставить ошибку неисправленной если нет уверенности в том что это ошибка и её надо исправить именно так. \
Если в тексте есть ошибки согласования надо сделать что бы не было. \
Маты и другой неприемлимый для тебя контент переделай так что бы смысл передать другими словами. \
Грубый текст исправь. \
Покажи результат без оформления и своих комментариев. Текст:{prompt}'
    try:
        r = ai(prompt)
    except Exception as e:
        print(e)
        return text
    return r


def check_and_fix_text(text):
    """пытаемся исправить странную особенность пиратского GPT сервера (только pawan?), он часто делает ошибку в слове, вставляет 2 вопросика вместо буквы"""
    if 'Windows' in utils.platform():
        return text

    ru = enchant.Dict("ru_RU")

    # убираем из текста всё кроме русских букв, 2 странных символа меняем на 1 что бы упростить регулярку
    text = text.replace('��', '⁂')
    russian_letters = re.compile('[^⁂а-яА-ЯёЁ\s]')
    text2 = russian_letters.sub(' ', text)
    
    words = text2.split()
    for word in words:
        if '⁂' in word:
            suggestions = ru.suggest(word)
            if len(suggestions) > 0:
                text = text.replace(word, suggestions[0])

    # если не удалось подобрать слово из словаря то просто убираем этот символ, пусть лучше будет оопечатка чем мусор
    return text.replace('⁂', '')


def zip_text(text: str) -> str:
    """
    Функция для удаления из текста русских и английских гласных букв типа "а", "о", "e" и "a".
    Так же удаляются идущие подряд одинаковые символы
    """
    vowels = [  'о', 'О',        # русские
                'o', 'O']        # английские. не стоит наверное удалять слишком много

    # заменяем гласные буквы на пустую строку, используя метод translate и функцию maketrans
    text = text.translate(str.maketrans('', '', ''.join(vowels)))

    # убираем повторяющиеся символы
    # используем генератор списков для создания нового текста без повторов
    # сравниваем каждый символ с предыдущим и добавляем его, если они разные 
    new_text = "".join([text[i] for i in range(len(text)) if i == 0 or text[i] != text[i-1]])
    
    return new_text


def query_file(query: str, file_name: str, file_size: int, file_text: str) -> str:
    """
    Query a file using the chatGPT model and return the response.

    Args:
        query (str): The query to ask the chatGPT model.
        file_name (str): The name of the file.
        file_size (int): The size of the file in bytes.
        file_text (str): The content of the file.

    Returns:
        str: The response from the chatGPT model.
    """

    msg = f"""Ответь на запрос юзера по содержанию файла
Запрос: {query}
Имя файла: {file_name}
Размер файла: {file_size}
Текст из файла:


{file_text}
"""
    msg_size = len(msg)
    if msg_size > 99000:
        msg = msg[:99000]
        msg_size = 99000

    result = ''

    if msg_size < 15000:
        try:
            result = ai(msg, model_to_use = 'gpt-3.5-turbo-16k')
        except Exception as error:
            print(error)
            my_log.log2(f'gpt_basic:query_file: {error}')

    if not result and msg_size < 30000:
        try:
            result = ai(msg, model_to_use = 'claude-2-100k')
        except Exception as error:
            print(error)
            my_log.log2(f'gpt_basic:query_file: {error}')

    if not result and msg_size <= 99000:
        try:
            result = ai(msg, model_to_use = 'claude-instant-100k')
        except Exception as error:
            print(error)
            my_log.log2(f'gpt_basic:query_file: {error}')

    if not result:
        try:
            result = ai(msg[:15000], model_to_use = 'gpt-3.5-turbo-16k')
        except Exception as error:
            print(error)
            my_log.log2(f'gpt_basic:query_file: {error}')

    return result


if __name__ == '__main__':
    if cfg.all_proxy:
        os.environ['all_proxy'] = cfg.all_proxy
    
    #print(ai_test())
    print(query_file('сколько цифр в файле и какая их сумма', 'test.txt', 100, '1\n2\n2\n1'))
    sys.exit()

    if len(sys.argv) != 2:
        print("Usage: gptbasic.py filename|'request to qpt'")
        sys.exit(1)
    t = sys.argv[1]
    if os.path.exists(t):
        print(ai(open(t).read(), max_tok = 2000, second = True))
    else:
        print(ai(t, max_tok = 2000))
