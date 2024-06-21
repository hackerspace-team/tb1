#!/usr/bin/env python3

import pickle
import time

import my_gemini
import my_groq
import my_db
import my_shadowjourney
import my_trans


languages_ocr = ["afr", "amh", "ara", "asm", "aze", "aze_cyrl", "bel", "ben", "bod",
                 "bos", "bre", "bul", "cat", "ceb", "ces", "chi_sim", "chi_tra", "chr",
                 "cos", "cym", "dan", "dan_frak", "deu", "deu_frak", "deu_latf", "dzo",
                 "ell", "eng", "enm", "epo", "equ", "est", "eus", "fao", "fas", "fil",
                 "fin", "fra", "frk", "frm", "fry", "gla", "gle", "glg", "grc", "guj",
                 "hat", "heb", "hin", "hrv", "hun", "hye", "iku", "ind", "isl", "ita",
                 "ita_old", "jav", "jpn", "kan", "kat", "kat_old", "kaz", "khm", "kir",
                 "kmr", "kor", "kor_vert", "kur", "lao", "lat", "lav", "lit", "ltz",
                 "mal", "mar", "mkd", "mlt", "mon", "mri", "msa", "mya", "nep", "nld",
                 "nor", "oci", "ori", "osd", "pan", "pol", "por", "pus", "que", "ron",
                 "rus", "san", "sin", "slk", "slk_frak", "slv", "snd", "spa", "spa_old",
                 "sqi", "srp", "srp_latn", "sun", "swa", "swe", "syr", "tam", "tat", "tel",
                 "tgk", "tgl", "tha", "tir", "ton", "tur", "uig", "ukr", "urd", "uzb", "uzb_cyrl",
                 "vie", "yid", "yor",
                 "arab", "armn", "beng", "cans", "cher", "cyrl", "deva", "ethi", "frak", 
                 "geor", "grek", "gujr", "guru", "hans", "hans-vert", "hant", "hant-vert", "hang",
                 "hang-vert", "hebr", "jpan", "jpan-vert", "knda", "khmr", "laoo", "latn", "mlym",
                 "mymr", "orya", "sinh", "syrc", "taml", "telu", "thaa", "thai", "tibt", "viet"]


supported_langs_trans = [
        "af","am","ar","az","be","bg","bn","bs","ca","ceb","co","cs","cy","da","de",
        "el","en","eo","es","et","eu","fa","fi","fr","fy","ga","gd","gl","gu","ha",
        "haw","he","hi","hmn","hr","ht","hu","hy","id","ig","is","it","iw","ja","jw",
        "ka","kk","km","kn","ko","ku","ky","la","lb","lo","lt","lv","mg","mi","mk",
        "ml","mn","mr","ms","mt","my","ne","nl","no","ny","or","pa","pl","ps","pt",
        "ro","ru","rw","sd","si","sk","sl","sm","sn","so","sq","sr","st","su","sv",
        "sw","ta","te","tg","th","tl","tr","ua","uk","ur","uz","vi","xh","yi","yo","zh",
        "zh-TW","zu"]

supported_langs_tts = [
        'af', 'am', 'ar', 'as', 'az', 'be', 'bg', 'bn', 'bs', 'ca', 'cs', 'cy', 'da',
        'de', 'el', 'en', 'en2', 'eo', 'es', 'et', 'eu', 'fa', 'fi', 'fil', 'fr', 'ga', 'gl',
        'gu', 'he', 'hi', 'hr', 'ht', 'hu', 'hy', 'id', 'is', 'it', 'ja', 'jv', 'ka',
        'kk', 'km', 'kn', 'ko', 'ku', 'ky', 'la', 'lb', 'lo', 'lt', 'lv', 'mg', 'mi',
        'mk', 'ml', 'mn', 'mr', 'ms', 'mt', 'my', 'nb', 'ne', 'nl', 'nn', 'no', 'ny',
        'or', 'pa', 'pl', 'ps', 'pt', 'ro', 'ru', 'rw', 'sd', 'si', 'sk', 'sl', 'sm',
        'sn', 'so', 'sq', 'sr', 'st', 'su', 'sv', 'sw', 'ta', 'te', 'tg', 'th', 'tk',
        'tl', 'tr', 'tt', 'ua', 'ug', 'uk', 'ur', 'uz', 'vi', 'xh', 'yi', 'yo', 'zh', 'zu']


start_msg = '''Hello, I`m AI chat bot powered by Google, Microsoft, Openai etc.

Ask me anything. Send me you text/image/audio/documents with questions.
Generate images with /image command.

Change language with /lang command.
Remove keyboard /remove_keyboard.
'''

help_msg = f"""Please use /image2 command for generating not safe pictures (nsfw).

🔭 If you send a link or text file in a private message, the bot will try to extract and provide a brief summary of the content.
After the file or link is downloaded, you can ask questions about file using the /ask command.

🛸 To get text from an image, send the image with the caption "ocr".

🎙️ You can issue commands and make requests using voice messages.

👻 /purge command to remove all your data


Report issues on Telegram:
https://t.me/kun4_sun_bot_support

"""

start_msg_file = 'msg_hello.dat'
help_msg_file = 'msg_help.dat'


def generate_start_msg():
    msgs = {}
    for x in supported_langs_trans:
    # for x in ['ru', 'uk', 'de']:
        msg = ''

        # for _ in range(2):
        #     if not msg:
        #         msg = my_shadowjourney.translate(start_msg, to_lang = x)
        #     else:
        #         break
        #     if not msg:
        #         time.sleep(60)

        if not msg:
            msg = my_trans.translate_deepl(start_msg, to_lang=x)
        if not msg:
            msg = my_groq.translate(start_msg, to_lang = x)
        if not msg:
            msg = start_msg
        if msg:
            msgs[x] = msg
            print('\n\n', x, '\n\n', msg)
        if not msg:
            print(f'google translate failed {x}')

    with open(start_msg_file, 'wb') as f:
        pickle.dump(msgs, f)


def generate_help_msg():
    msgs = {}
    for x in supported_langs_trans:
    # for x in ['ru', 'uk', 'de']:
        # msg = my_trans.translate_text2(help_msg, x)
        msg = my_shadowjourney.translate(help_msg, from_lang='en', to_lang=x, help='It is a /help message for telegram chat bot.')
        if msg:
            msgs[x] = msg
            print('\n\n', x, '\n\n', msg)
        if not msg:
            print(f'google translate failed {x}')

    with open(help_msg_file, 'wb') as f:
        pickle.dump(msgs, f)


def check_translations(original: str, translated: str, lang):
    q = f'''Decide if translation to language "lang" was made correctly.
Your answer should be "yes" or "no" or "other".

Original text:

{original}


Translated text:

{translated}
'''
    res = my_groq.ai(q, temperature = 0, max_tokens_ = 10)
    result = True if 'yes' in res.lower() else False
    return result


def found_bad_translations(fname: str = start_msg_file, original: str = start_msg):
    with open(fname, 'rb') as f:
        db = pickle.load(f)
    bad = []
    for lang in db:
        msg = db[lang]
        translated_good = check_translations(original, msg, lang)
        if not translated_good:
            bad.append(lang)
    print(bad)


def fix_translations(fname: str = start_msg_file, original: str = start_msg, langs = []):
    with open(fname, 'rb') as f:
        db = pickle.load(f)
    for lang in langs:
        print(lang)
        translated = my_gemini.translate(original, to_lang=lang, model = 'gemini-1.5-pro')
        if translated:
            if 'no translation needed' in translated.lower():
                translated = original
            db[lang] = translated
            print(translated)
    with open(fname, 'wb') as f:
        pickle.dump(db, f)


def fix_translations_start(langs = []):
    with open(start_msg_file, 'rb') as f:
        db = pickle.load(f)
    for lang in langs:
        print(lang)
        translated = my_gemini.translate(db['en'], to_lang=lang, model = 'gemini-1.5-pro')
        if not translated:
            translated = my_shadowjourney.translate(db['en'], to_lang=lang)
        if translated:
            if 'no translation needed' in translated.lower():
                translated = db['en']
            db[lang] = translated
            print(translated)
        else:
            del db[lang]
    with open(start_msg_file, 'wb') as f:
        pickle.dump(db, f)


if __name__ == '__main__':
    pass
    my_db.init()
    my_groq.load_users_keys()
    my_gemini.load_users_keys()
    my_trans.load_users_keys()


    # generate_start_msg()
    # generate_help_msg()

    # fix_translations_start(['am', ])
    my_db.close()
