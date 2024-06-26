#!/usr/bin/env python3


import re
import subprocess

from duckduckgo_search import DDGS
import enchant
from langdetect import detect, detect_langs
# from py_trans import PyTranslator

import my_log
import utils


# keep in memory the translation
TRANSLATE_CACHE = {}


def count_russian_words_not_in_ukrainian_dict(text):
    """Считаем количество русских слов в тексте, эти слова не должны быть в украинском и белорусском"""
    platform = utils.platform().lower()
    if 'wind' in platform:
        return len(text.split())
    d_ru = enchant.Dict("ru_RU")
    d_uk = enchant.Dict("uk_UA")
    russian_words = []
    # Заменяем все символы, которых нет в алфавитах, на пробелы
    text = re.sub(r"[^а-яА-ЯіІїЇєЄёЁ]+", " ", text)
    for word in text.split():
        # Проверяем, является ли слово русским
        if d_ru.check(word) and not d_uk.check(word):
            russian_words.append(word)
    return len(russian_words)


def count_ukr_words(text):
    """Считаем количество украинских слов не пересекающихся с русскими"""
    d_uk = enchant.Dict("uk_UA")
    d_ru = enchant.Dict("ru_RU")
    words = []
    # Заменяем все символы, которых нет в алфавитах, на пробелы
    text = re.sub(r"[^а-яА-ЯіІїЇєЄёЁ]+", " ", text)
    for word in text.split():
        # Проверяем, является ли слово русским
        if d_uk.check(word) and not d_ru.check(word):
            words.append(word)
    return len(words)


def detect_lang(text):
    """ Возвращает None если не удалось определить, 2 буквенное определение языка если получилось 'en', 'ru' итп """
    # минимальное количество слов для определения языка = 8. на коротких текстах детектор сильно врёт, возможно 8 это тоже мало
    if sum(1 for word in text.split() if len(word) >= 2) < 8:
        # если пробелов очень мало то возможно это язык типа японского
        if len(text) < 20 or text.count(' ') > len(text)/20:
            return None
    
    # cчитаем белорусские буквы
    pattern = r'[ЎўІіЎў]'
    if len(re.findall(pattern, text)) > 3:
        return 'be' # возможно украинский но нам всё равно, главное что не русский
    
    # если в тексте больше 2 русских слов возвращаем None
    if count_russian_words_not_in_ukrainian_dict(text) > 2:
        return None

    # если в тексте больше 2 чисто украинских слов возвращаем 'uk'
    if count_ukr_words(text) > 2:
        return 'uk'

    # смотрим список вероятностей, и если в списке есть русский то возвращаем None (с русского на русский не переводим)
    #print(detect_langs(text))
    try:
        for i in detect_langs(text):
            if i.lang == 'ru':
                return None
    except Exception as e:
        print(e)
        return None

    try:
        language = detect(text)
    except Exception as e:
        print(e)
        return None
    return language



def translate_text_ddg(text: str, lang: str = 'ru', _from: str = None) -> str:
    """
    Translates text using the DDG translation service.

    Args:
        text (str): The text to be translated.
        lang (str, optional): The language to translate the text to. Defaults to 'ru'.
        _from (str, optional): The language to translate the text from.
                               Defaults to None.

    Returns:
        str: The translated text.

    Raises:
        AssertionError: If an error occurs during translation.

    Notes:
        This function makes use of a translation cache to improve performance. If the
        translation for the given text and language is already in the cache, it is
        returned directly without making a request to the translation service.
        If the translation is not in the cache, a request is made to the DDG translation
        service and the result is stored in the cache for future use.
    """
    key = str((text, lang))
    if key in TRANSLATE_CACHE:
        return TRANSLATE_CACHE[key]

    try:
        with DDGS() as ddgs:
            result = ddgs.translate(text, _from, lang)['translated']
            if isinstance(result, dict):
                result = result['translated']
            elif not isinstance(result, str):
                my_log.log2(f'my_trans:translate_text_ddg: {result["status"]}\n\n{text}\n\n{lang}')
                return None
    except AssertionError as error:
        my_log.log2(f'my_trans:translate_text_ddg: {error}\n\ntext:{text}\n\nlang:{lang}\n\nfrom:{_from}')
        return None
    except Exception as error2:
        my_log.log2(f'my_trans:translate_text_ddg: {error2}\n\ntext:{text}\n\nlang:{lang}\n\nfrom:{_from}')
        return None

    TRANSLATE_CACHE[key] = result
    return result


def translate_text2(text, lang = 'ru'):
    """
    Translates the given text into the specified language using an external 
    translation service. Requires the `trans` command to be installed.

    Args:
        text (str): The text to be translated.
        lang (str, optional): The language to translate the text to. Defaults to 'ru'.
    
    Returns:
        str: The translated text.
    """
    if 'windows' in utils.platform().lower():
        return translate_text_ddg(text, lang)
        # return translate_text_ddg(text, lang) or translate_text(text, lang)
    text = text.strip()
    startswithslash = False
    if text.startswith('/'):
        text = text.replace('/', '@', 1)
        startswithslash = True
    key = str((text, lang))
    if key in TRANSLATE_CACHE:
        return TRANSLATE_CACHE[key]
    process = subprocess.Popen(['trans', f':{lang}', '-b', text], stdout = subprocess.PIPE)
    output, error = process.communicate()
    result = output.decode('utf-8').strip()
    if error:
        my_log.log2(f'my_trans:translate_text2: {error}\n\n{text}\n\n{lang}')
        return None
    if startswithslash:
        if result.startswith('@'):
            result = result.replace('@', '/', 1)
    TRANSLATE_CACHE[key] = result
    return result


def translate(text):
    """ Проверяем надо ли переводить на русский и переводим если надо.
    Возвращает None если не удалось перевести и текст перевода если удалось """
    if text:
        d = detect_lang(text)
    else:
        return None
    # переводим если язык не русский но определился успешно
    if d and d != 'ru':
        return translate_text2(text) or None
        # return translate_text2(text) or translate_text(text) or None
    return None


if __name__ == "__main__":
    pass