#!/usr/bin/env python3


import io
import os
import re
import sys
from urllib.parse import urlparse
from youtube_transcript_api import YouTubeTranscriptApi

import chardet
# import magic
import PyPDF2
import requests
import trafilatura

import my_log
import my_gemini
import my_trans
import utils


def get_text_from_youtube(url: str) -> str:
    """Вытаскивает текст из субтитров на ютубе

    Args:
        url (str): ссылка на ютуб видео

    Returns:
        str: первые субтитры из списка какие есть в видео
    """
    top_langs = ('ru', 'en', 'uk', 'es', 'pt', 'fr', 'ar', 'id', 'it', 'de', 'ja', 'ko', 'pl', 'th', 'tr', 'nl', 'hi', 'vi', 'sv', 'ro')

    video_id = re.search(r"(?:v=|\/)([a-zA-Z0-9_-]{11})(?:\?|&|\/|$)", url).group(1)

    try:
        t = YouTubeTranscriptApi.get_transcript(video_id, languages=top_langs)
    except Exception as error:
        if 'If you are sure that the described cause is not responsible for this error and that a transcript should be retrievable, please create an issue at' not in str(error):
            my_log.log2(f'get_text_from_youtube: {error}')
        t = ''

    text = '\n'.join([x['text'] for x in t])

    return text or ''


def shrink_text_for_bing(text: str, max_size = 60000) -> str:
    """уменьшаем текст до 60000 байт (не символов!)"""
    text2 = text
    if len(text2) > max_size:
        text2 = text2[:max_size]
    text_bytes = text2.encode()

    while len(text_bytes) > max_size:
        text2 = text2[:-1]
        text_bytes = text2.encode()

    return text2


def summ_text_worker(text: str, subj: str = 'text', lang: str = 'ru', query: str = '') -> str:
    """параллельный воркер для summ_text
       subj == 'text' or 'pdf'  - обычный текст о котором ничего не известно
       subj == 'chat_log'       - журнал чата
       subj == 'youtube_video'  - субтитры к видео на ютубе
    """

    # если запустили из pool.map и передали параметры как список
    if isinstance(text, tuple):
        text, subj, _ = text[0], text[1], text[2]

    if subj == 'text' or subj == 'pdf':
        prompt = f"""Summarize the following, briefly answer in [{lang}] language with easy-to-read formatting:
-------------
{text}
-------------
BEGIN:
"""
    elif subj == 'chat_log':
        prompt = f"""Summarize the following telegram chat log, briefly answer in [{lang}] language with easy-to-read formatting:
-------------
{text}
-------------
BEGIN:
"""
    elif subj == 'youtube_video':
        prompt = f"""Summarize the following video subtitles extracted from youtube, briefly answer in [{lang}] language with easy-to-read formatting:
-------------
{text}
-------------
"""

    if type(text) != str or len(text) < 1: return ''

    result = ''
    tr = my_trans.translate_text2

    if not result:
        try:
            if subj == 'youtube_video':
                qq = f'Summarize the content of this YouTube video using only the subtitles, what this video about, in 500-4000 words, answer in [{lang}] language.'
            else:
                qq = f'Summarize the content of this article using only provided text, what this text about, in 500-4000 words, answer in [{lang}] language.'
            if query:
                qq = query
            r = my_gemini.sum_big_text(text[:my_gemini.MAX_SUM_REQUEST], qq).strip()
            if r != '':
                result = f'{r}\n\n--\nGemini Pro [{len(prompt[:my_gemini.MAX_SUM_REQUEST])} {tr("символов", lang)}]'
        except Exception as error:
            print(f'my_sum:summ_text_worker:gpt: {error}')
            my_log.log2(f'my_sum:summ_text_worker:gpt: {error}')

    return result


def summ_text(text: str, subj: str = 'text', lang: str = 'ru', query: str = '') -> str:
    """сумморизирует текст с помощью бинга или гптчата или клод-100к, возвращает краткое содержание, только первые 30(60)(99)т символов
    subj - смотрите summ_text_worker()
    """
    return summ_text_worker(text, subj, lang, query)


def summ_url(url:str, download_only: bool = False, lang: str = 'ru') -> str:
    """скачивает веб страницу, просит гптчат или бинг сделать краткое изложение текста, возвращает текст
    если в ссылке ютуб то скачивает субтитры к видео вместо текста
    может просто скачать текст без саммаризации, для другой обработки"""
    youtube = False
    pdf = False
    if '/youtu.be/' in url or 'youtube.com/' in url:
        text = get_text_from_youtube(url)
        youtube = True
    else:
        # Получаем содержимое страницы
                
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'}

        response = requests.get(url, stream=True, headers=headers, timeout=10)
        content = b''
        # Ограничиваем размер
        for chunk in response.iter_content(chunk_size=1024):
            content += chunk
            if len(content) > 1 * 1024 * 1024: # 1 MB
                break

        if utils.mime_from_buffer(content) == 'application/pdf':
            pdf = True
            file_bytes = io.BytesIO(content)
            pdf_reader = PyPDF2.PdfReader(file_bytes)
            text = ''
            for page in pdf_reader.pages:
                text += page.extract_text()
        else:
            # Определяем кодировку текста
            encoding = chardet.detect(content[:2000])['encoding']
            # Декодируем содержимое страницы
            try:
                content = content.decode(encoding)
            except UnicodeDecodeError as error:
                print(error)
                content = response.content.decode('utf-8')

            newconfig = trafilatura.settings.use_config()
            newconfig.set("DEFAULT", "EXTRACTION_TIMEOUT", "0")
            text = trafilatura.extract(content, config=newconfig)
   
    if download_only:
        if youtube:
            r = f'URL: {url}\nСубтитры из видео на ютубе (полное содержание, отметки времени были удалены):\n\n{text}'
        else:
            r = f'URL: {url}\nРаспознанное содержание веб страницы:\n\n{text}'
        return r
    else:
        if youtube:
            r = summ_text(text, 'youtube_video', lang)
        elif pdf:
            r = summ_text(text, 'pdf', lang)
        else:
            r = summ_text(text, 'text', lang)
        return r, text


def is_valid_url(url: str) -> bool:
    """Функция is_valid_url() принимает строку url и возвращает True, если эта строка является веб-ссылкой,
    и False в противном случае."""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False


if __name__ == "__main__":
    """Usage ./summarize.py '|URL|filename"""
    urls = [
        # 'https://habr.com/ru/articles/780688/',
        # 'https://habr.com/ru/articles/785320/',
        # 'https://habr.com/ru/articles/784858/',
        # 'https://habr.com/ru/articles/785328/',
        # 'https://www.youtube.com/watch?v=grMAWQBwijw',
        # 'https://www.youtube.com/watch?v=x9hfUXAlVd0',
        # 'https://www.youtube.com/watch?v=kW3_syJruKs&t=623s',
        # 'https://www.youtube.com/watch?v=8Aov8WhV4ME',
        # 'https://www.youtube.com/watch?v=WlUT-szZQWg',
        # 'https://www.youtube.com/watch?v=rbL6hJR1k0I',
        'https://www.youtube.com/watch?v=nrFjjsAc_E8',
    ]
    for url in urls:
        print(summ_url(url))

    sys.exit(0)
    
    t = sys.argv[1]
    
    if is_valid_url(t):
        print(summ_url(t))
    elif os.path.exists(t):
        print(summ_text(open(t).read()))
    else:
        print("""Usage ./summarize.py '|URL|filename""")
