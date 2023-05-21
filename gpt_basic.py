#!/usr/bin/env python3


import requests
import cfg
import openai


openai.api_key = cfg.key


def ai(prompt):
    """Сырой текстовый запрос к GPT чату, возвращает сырой ответ"""
    
    messages = [    {"role": "system",
                    #"content": 'Ты информационная система отвечающая на запросы юзера.'
                    "content": 'Ты интерпретатор вымышленного языка программирования "GPT-BASIC 3000". Тебе дают программы на естественном языке, ты даешь результат.'
                    },
                
                    {"role": "user",
                     "content": prompt
                    }
                ]

    completion = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=messages
    )

    response = completion.choices[0].message.content
    return response


def translate_text(text, fr = None, to = 'ru'):
    """переводит текст с помощью GPT-чата, возвращает None при ошибке"""
    if fr:
        prompt = f'Исправь явные опечатки в тексте, и переведи с языка ({fr}) на язык ({to}). Переносы строк исправлять не надо. Покажи только перевод без оформления и отладочной информации. Текст: '
    else:
        prompt = f'Исправь явные опечатки в тексте, и переведи на язык ({to}). Переносы строк исправлять не надо. Покажи только перевод без оформления и отладочной информации. Текст: '
    prompt += text
    
    try:
        r = ai(prompt)
    except Exception as e:
        print(e)
        return None
    return r


if __name__ == '__main__':
    pass
    
    print(translate_text("Доброго дня! Я готовий допомогти вам з\nбудь-якими питаннями, пов'язаними з моїм функціоналом."))
    
    #print(ai("сгенерируй список реалистичных турецких имен на русском, 10шт, отсортируй по фамилии по возрастанию, покажи строку содержащую сериализованный питон список"))
