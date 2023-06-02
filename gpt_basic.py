#!/usr/bin/env python3


import os
import re
import sys

import enchant
from fuzzywuzzy import fuzz
import openai

try:
    import cfg
except Exception as e:
    print(e)


# используем другой сервер, openai нас не пускает и ключей не продает, приходится заходить черз задний вход
# бесплатные ключи у дискорд бота https://github.com/PawanOsman/ChatGPT#use-our-hosted-api-reverse-proxy
# To use our hosted ChatGPT API, you can use the following steps:
# * Join our Discord server.
# * Get your API key from the #Bot channel by sending /key command.
# * Use the API Key in your requests to the following endpoints.
# * Присоединитесь к нашему серверу Discord.
# * Получите свой API-ключ в канале #Bot, отправив команду /key.
# * Используйте API-ключ в ваших запросах к следующим конечным точкам.
# * Если у бота поменялся адрес надо в дискорде боту написать /resetip

openai.api_base = 'https://api.pawan.krd/v1'


# Пробуем получить апи ключ из конфига или переменной окружения
openai.api_key = None
try:
    openai.api_key = cfg.key
except Exception as e:
    print(e)
    try:
        openai.api_key = os.getenv('OPENAI_KEY')
    except Exception as e:
        print(e)


def ai(prompt, temp = 0.5, max_tok = 2000, timeou = 15, messages = None):
    """Сырой текстовый запрос к GPT чату, возвращает сырой ответ"""
    if messages == None:
        messages = [    {"role": "system",
                    "content": """Ты информационная система отвечающая на запросы юзера."""
                    # в роли интерпретатра бейсика он говорит много лишнего и странного
                    #"content": 'Ты интерпретатор вымышленного языка программирования "GPT-BASIC 3000". Тебе дают программы на естественном языке, ты даешь самый очевидный и скучный результат.'
                    },

                    #{"role": "assistant",
                    # "content": "history messages from assistant for more context"
                    #},
                
                    #{"role": "user",
                    # "content": "history messages from user for more context"
                    #},

                    #{"role": "assistant",
                    # "content": "history messages from assistant for more context"
                    #},


                    {"role": "user",
                     "content": prompt
                    }
                ]

    # тут можно добавить степерь творчества(бреда) от 0 до 1 дефолт - temperature=0.5
    completion = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=messages,
        max_tokens=max_tok,
        temperature=temp,
        timeout=timeou
    )

    response = completion.choices[0].message.content
    return check_and_fix_text(response)


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

    prompt = f'Исправь явные ошибки и опечатки в тексте которые там могли появиться после плохого OCR. \
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
    """пытаемся исправить странную особенность пиратского GPT сервера, он часто делает ошибку в слове, вставляет 2 вопросика вместо буквы"""
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


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Usage: gptbasic.py 'request to qpt'")
        sys.exit(1)
    print(ai(sys.argv[1]))
