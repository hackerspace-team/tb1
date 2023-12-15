#!/usr/bin/env python3


import urllib.parse

from duckduckgo_search import DDGS
import googlesearch
import trafilatura

import gpt_basic
import cfg
import my_log
import my_gemini
import my_trans


def download_text(urls: list, max_req: int = cfg.max_request, no_links = False) -> str:
    """
    Downloads text from a list of URLs and returns the concatenated result.
    
    Args:
        urls (list): A list of URLs from which to download text.
        max_req (int, optional): The maximum length of the result string. Defaults to cfg.max_request.
        no_links(bool, optional): Include links in the result. Defaults to False.
        
    Returns:
        str: The concatenated text downloaded from the URLs.
    """
    #max_req += 5000 # 5000 дополнительно под длинные ссылки с запасом
    result = ''
    newconfig = trafilatura.settings.use_config()
    newconfig.set("DEFAULT", "EXTRACTION_TIMEOUT", "0")
    for url in urls:
        content = trafilatura.fetch_url(url)
        # text = trafilatura.extract(content, config=newconfig, include_links=True, deduplicate=True, \
        #                            include_comments = True)
        text = trafilatura.extract(content, config=newconfig, deduplicate=True)
        if text:
            if no_links:
                result += f'\n\n{text}\n\n'
            else:
                result += f'\n\n|||{url}|||\n\n{text}\n\n'
            if len(result) > max_req:
                break
    return result


def ask_gpt(query: str, max_req: int, history: str, result: str, engine: str,
            lang: str = 'ru') -> str:
    """
	Ask GPT to respond to a user query using the results from a Google search on the query.
	Ignore any unclear characters in the search results as they should not affect the response.
	The response should only include what the user searched for and should not include anything they didn't search for.
	Try to understand the meaning of the user's query and what they want to see in the response.
	If it is not possible to answer such queries, then convert everything into a joke.

	Parameters:
	- query (str): The user's query.
	- max_req (int): The maximum number of characters to use from the query.
	- history (str): The previous conversation history.
	- result (str): The results from the Google search on the query.
    - engine (str): Google or DuckDuckGo.

	Return:
	- str: The response generated by GPT based on the given query and search results.
    """

    tr = my_trans.translate_text2
    text = tr(f"""Ответь на запрос юзера, используй результаты поиска в {engine} по этому запросу,
игнорируй непонятные символы в результатах поиска, они не должны влиять на ответ,
в ответе должно быть только то что юзер искал, и не должно быть того что не искал,
постарайся понять смысл его запроса и что он хочет увидеть в ответ,
если на такие запросы нельзя отвечать то переведи всё в шутку.
Отвечай на языке пользователя: {lang}.


О чем говорили до этого:""", lang) + f' {history}'
    text += f"""


{tr('Запрос', lang)}: {query}


Результаты поиска по этому запросу:"""
    text += f"""

{result}"""

    result = my_gemini.ai(text[:max_req])
    if result == '' or result == 'Gemini didnt respond':
        result = gpt_basic.ai(text[:max_req], max_tok=cfg.max_google_answer)
    my_log.log_google(text[:max_req], result)
    return result


def search_google(query: str, max_req: int = cfg.max_request, max_search: int = 20,
                  history: str = '', lang: str = 'ru') -> str:
    """ищет в гугле ответ на вопрос query, отвечает с помощью GPT
    max_req - максимальный размер ответа гугла, сколько текста можно отправить гпт чату
    max_search - сколько ссылок можно прочитать пока не наберется достаточно текстов
    history - история диалога, о чем говорили до этого
    """

    max_req = max_req - len(history)
    # добавляем в список выдачу самого гугла, и она же первая и главная
    urls = [f'https://www.google.com/search?q={urllib.parse.quote(query)}',]
    # добавляем еще несколько ссылок, возможно что внутри будут пустышки, джаваскрипт заглушки итп
    r = googlesearch.search(query, stop = max_search, lang=lang)
    bad_results = ('https://g.co/','.pdf','.docx','.xlsx', '.doc', '.xls')
    for url in r:
        if any(s.lower() in url.lower() for s in bad_results):
            continue
        urls.append(url)
    result = download_text(urls, max_req)

    # text, links = shorten_links(result)
    # answer = ask_gpt(query, max_req, history, text, 'Google')
    # return restore_links(answer, links)
    text = result
    answer = ask_gpt(query, max_req, history, text, 'Google', lang)
    return answer


def ddg_text(query: str) -> str:
    """
    Generate a list of URLs from DuckDuckGo search results based on the given query.

    Parameters:
        query (str): The search query.

    Returns:
        str: A URL from each search result.
    """
    with DDGS() as ddgs:
        for result in ddgs.text(query, safesearch='Off', timelimit='y', region = 'ru-ru'):
            yield result['href']


def search_ddg(query: str, max_req: int = cfg.max_request,
               max_search: int = 10, history: str = '', lang: str = 'ru') -> str:
    """ищет в ddg ответ на вопрос query, отвечает с помощью GPT
    max_req - максимальный размер ответа гугла, сколько текста можно отправить гпт чату
    max_search - сколько ссылок можно прочитать пока не наберется достаточно текстов
    history - история диалога, о чем говорили до этого
    """
    max_req = max_req - len(history)
    urls = []
    # добавляем еще несколько ссылок, возможно что внутри будут пустышки, джаваскрипт заглушки итп
    bad_results = ('https://g.co/','.pdf','.docx','.xlsx', '.doc', '.xls')
    for url in ddg_text(query):
        if any(s.lower() in url.lower() for s in bad_results):
            continue
        urls.append(url)
    result = download_text(urls, max_req)
    
    # text, links = shorten_links(result)
    # answer = ask_gpt(query, max_req, history, text, 'DuckDuckGo')
    # return restore_links(answer, links)
    text = result
    answer = ask_gpt(query, max_req, history, text, 'DuckDuckGo', lang)
    return answer


def search(query: str, lang: str = 'ru') -> str:
    """
    Search for a query string using Google search and return the result.
    Search for a query string using DuckDuckGo if Google fails.

    Parameters:
        query (str): The query string to search for.

    Returns:
        str: The search result.
    """
    try:
        result = search_google(query, lang=lang)
    except urllib.error.HTTPError as error:
        if 'HTTP Error 429: Too Many Requests' in str(error):
            result = search_ddg(query, lang=lang)
            my_log.log2(query)
        else:
            print(error)
            raise error
    return result


if __name__ == "__main__":
    #text, links = shorten_links(text)
    #print(text)
    #print(links, text)
    #print(restore_links(text, links))

    #print(download_text(['https://www.google.com/search?q=курс+доллара'], 10))    

    #print(search('3 закона робототехники'), '\n\n')
    #sys.exit(0)

    #print(gpt_basic.ai('1+1'))
    
    # print(search_google('курс доллара'), '\n\n')
    
    # print(search('полный текст песни doni ft валерия ты такой'), '\n\n')

    # print(search('курс доллара'), '\n\n')
    # print(search('текст песни егора пикачу'), '\n\n')

    # print(search('когда доллар рухнет?'), '\n\n')
    # print(search('как убить соседа'), '\n\n')

    # print(search('Главные герои книги незнайка на луне, подробно'), '\n\n')
    print(search('Главные герои книги три мушкетера, подробно'), '\n\n')
