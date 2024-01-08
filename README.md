# Телеграм бот для доступа к chatGPT, Google Bard, Claude AI и др

Тестовый образец https://t.me/kun4sun_bot

Чат бот отзывается на кодовое слово `бот`(можно сменить командой /name) `бот расскажи про биткоин`

Кодовое слово `гугл`(нельзя изменить) позволит получить более актуальную информацию, бот будет гуглить перед ответом `гугл, сколько людей на земле осталось`

В привате можно не писать кодовые слова для обращения к боту

Если он перестал отвечать то возможно надо почистить ему память командой `забудь`

Кодовое слово `нарисуй` и дальше описание даст картинки сгенерированные по описанию. В чате надо добавлять к этому обращение `бот нарисуй на заборе неприличное слово`

В чате бот будет автоматически переводить иностранные тексты на русский и распознавать голосовые сообщения, отключить это можно кодовым словом `бот замолчи`, включить обратно `бот вернись`

Если отправить картинку или .pdf с подписью `прочитай` то вытащит текст из них.

Если отправить картинку с подписью что (Что на картинке итп) или без подписи то напишет описание того что изображено на картинке

Если отправить ссылку в приват с подписью (ocr, прочитай, читай) то попытается прочитать текст из неё и выдать краткое содержание.

Если ссылка на тикток видео то предложит его скачать (это нужно для рф где он заблокирован)

Если отправить номер телефона то попробует узнать кто звонил

Если отправить текстовый файл или пдф с подписью `что там` или `перескажи` то выдаст краткое содержание.

Если начать с точки то будет использована модель gpt-3.5-turbo-instruct, она дает ответы без дополнений которые обычно есть в диалогах, например если попросить ее перечислить 10 имен через запятую то ответ будет состоять из 10 имен через запятую, а если попросить обычную чат модель то в ответе будут лишние слова типа хорошо я попробуй сделать такой список, как у меня получилось? У этой модели нет цензуры, или она сильно ослаблена.

При общении с Claude загруженные файлы отправляются прямо к нему и в дальнейшем он может отвечать по их содержанию. Отправленные в этом режиме ссылки будут переданы клауду как текстовые файлы с содержанием этих веб страниц (и видео субтитров).

Команды и запросы можно делать голосовыми сообщениями, если отправить голосовое сообщение которое начинается на кодовое слово то бот отработает его как текстовую команду.


![Доступные команды](commands.txt)

**Команды для администратора**

/alert - массовая рассылка сообщения от администратора во все чаты, маркдаун форматирование, отправляет сообщение без уведомления но всё равно не приятная штука похожая на спам

/ init - инициализация бота, установка описаний на всех языках, не обязательно, можно и вручную сделать, выполняется долго, ничего не блокирует

/dump_translation - отправляет файл с авто-переводами выполнеными гуглом для ручной доработки, исправленный перевод надо просто отправить боту от имени администратора

/blockadd - добавить id '[chat_id] [thread_id]' в список заблокированных (игнорируемых) юзеров или чатов, учитывается только первая цифра, то есть весь канал со всеми темами внутри

/blockdel - удалить id из игнорируемых

/blocklist - список игнорируемых

/fixlang <lang> - исправить автоперевод сделанный с помощью гугла для указанного языка, будет использоваться чатгпт для этого

/leave <chat_id> - выйти из чата (можно вместо одного id вывалить кучу, все номера похожие на номер группы в тексте будут использованы)
/revoke <chat_id> - убрать чат из списка на автовыхода(бана) (можно вместо одного id вывалить кучу, все номера похожие на номер группы в тексте будут использованы)

/model - меняет модель для chatGPT, доступно всем но как работает неизвестно, зависит от того что есть на бекендах

/restart - перезапуск бота на случай зависания

/stats - статистика бота

/style2 - изменить стиль бота для заданного чата (пример: /style2 [id] [topic id] новая роль)

/reset_gemini2 - очистить историю чата Gemini Pro в другом чате Usage: /reset_gemini2 <chat_id_full!>

/gemini_proxy - [DEBUG] показывает список прокси которые нашел бот для Gemini Pro

/bingcookie - (/cookie /k) добавить куки для бинга, можно несколько через пробел
bingcookieclear - удалить все куки для бинга

/disable_chat_mode from to - принудительно сменить всем режим чата, например у кого бард переключить на джемини

/trial - userid_as_integer amount_of_monthes_to_add


![Скриншоты](pics/README.md)


## Установка

Для установки проекта выполните следующие шаги:

1. Установите Python 3.8+.
2. Установите утилиту trans `sudo apt-get install translate-shell`
3. Установите утилиту tesseract. В убунте 22.04.х (и дебиане 11) в репах очень старая версия тессеракта, надо подключать репозиторий с новыми версиями или ставить из бекпортов
    ```
    sudo apt-get update && \
    sudo apt-get install -y software-properties-common && \
    sudo add-apt-repository -y ppa:alex-p/tesseract-ocr5 && \
    sudo apt-get update && \
    sudo apt install tesseract-ocr tesseract-ocr-eng \
    tesseract-ocr-rus tesseract-ocr-ukr tesseract-ocr-osd
    ```
4. Установите словари и прочее `sudo apt install aspell aspell-en aspell-ru aspell-uk catdoc enchant-2 ffmpeg pandoc python3-venv sox`
   yt-dlp надо установить отдельно, т.к. в репах нет актуальной свежей версии, а она нужна для скачивания тиктоков и музыки с ютуба

5. Клонируйте репозиторий с помощью команды:

   ```
   git clone https://github.com/theurs/tb1.git
   
   python -m venv .tb1
   source ~/.tb1/bin/activate
   
   ```
   
4. Перейдите в директорию проекта:

   ```
   cd tb1
   ```
   
5. Установите зависимости, выполнив команду:

   ```
   pip install -r requirements.txt
   python -m textblob.download_corpora
   ```

6. Создайте файл cfg.py и добавьте в него строку
```
# [urs, port, addr] | None
# webhook = ["https://mydomain.com/bot", 33333, '0.0.0.0']
webhook = None

# описание бота, которое отображается в чате с ботом, если чат пуст. До 512 символов.
bot_description = """Free chat bot

ChatGPT | Google Bard | Claude AI

Голосовое управление, озвучивание текстов, пересказ веб страниц и видеороликов на Youtube, распознавание текста с картинок и из PDF."""

# краткое описание бота, которое отображается на странице профиля бота и отправляется
# вместе со ссылкой, когда пользователи делятся ботом. До 120 символов.
bot_short_description = """Free chat bot

ChatGPT | Google Bard | Claude AI"""

# Имя бота (псевдоним), это не уникальное имя, можно назвать как угодно,
# это не имя бота на которое он отзывается. До 64 символов.
bot_name = "Бот"

# имя на которое отзывается бот по умолчанию
default_bot_name = 'бот'

# какой бот отвечает по умолчанию
# 'bard', 'claude', 'chatgpt'
chat_mode_default = 'chatgpt'

# default locale, язык на который переводятся все сообщения
DEFAULT_LANGUAGE = 'ru'

# список админов, кому можно использовать команды /restart и вкл-выкл автоответы в чатах
admins = [xxx,]

# активированы ли триальные периоды, бот будет слать лесом юзеров которые уже неделю нахаляву тут
# TRIALS = True


# список юзеров кому доступен chatGPT (он хоть и дешевый но не бесплатный)
# если список пуст то всем можно
allow_chatGPT_users = [xxx,]

# сколько раз раз в минуту можно обращаться к боту до бана
DDOS_MAX_PER_MINUTE = 10
# на сколько секунд банить
DDOS_BAN_TIME = 86400

# telegram bot token
token   = "xxx"

# openai tokens and addresses
# список  серверов для chatGPT [['address', 'token', True/False(распознавание голоса), True/False(рисование)], [], ...]
# * где можно попытаться получить халявный ключ - дискорд chimeraGPT https://discord.gg/RFFeutYK https://chimeragpt.adventblocks.cc/ru
# * https://openai-api.ckt1031.xyz/
# * https://api.waveai.link/
openai_servers = [
    ['https://xxx.com/v1', 'sk-xxx', False, False],
    ['https://yyy.com/v1', 'sk-yyy', False, False]
]

# proxy for access openai
# openai_proxy = 'socks5://172.28.1.4:1080'
# openai_proxy = 'http://172.28.1.4:3128'

# токены для google bard
# искать __Secure-1PSID в куках с сайта https://bard.google.com/
# можно указать только 1
bard_tokens = ['xxx',
               'yyy']


# id телеграм группы куда скидываются все сгенерированные картинки
#pics_group = 0
#pics_group_url = ''
pics_group = xxx
pics_group_url = 'https://t.me/xxx'
# id телеграм группы куда скидываются все скаченные ролики с ютуба
#videos_group = 0
videos_group = xxxx
videos_group_url = 'https://t.me/xxx'


# размер буфера для поиска в гугле, чем больше тем лучше ищет и отвечает
# и тем больше токенов жрет
# для модели с 4к памяти
#max_request = 2800
#max_google_answer = 1000
# для модели с 16к памяти
max_request = 14000
max_google_answer = 2000


# насколько большие сообщения от юзера принимать
# если у gpt всего 4к памяти то 1500
#max_message_from_user = 4000
max_message_from_user = 90000


# 16k
max_hist_lines = 10
max_hist_bytes = 9000
max_hist_compressed=1500
max_hist_mem = 2500
# максимальный запрос от юзера к chatGPT. длинные сообщения телеграм бьет на части но
# бот склеивает их обратно и может получиться слишком много
CHATGPT_MAX_REQUEST = 7000

# ограничение для TTS от openai, если потребуют озвучить больше что будет говорить бесплатным голосом гугла
MAX_OPENAI_TTS = 2000

# 4k
#max_hist_lines = 10
#max_hist_bytes = 2000
#max_hist_compressed=700
#max_hist_mem=300

model = 'gpt-3.5-turbo-16k'
#model = 'gpt-3.5-turbo-8k'
#model = 'gpt-3.5-turbo'
#model = "sage"
#model = 'claude-instant'
#model = 'claude-instant-100k'
#model = 'claude-2-100k'


# язык для распознавания, в том виде в котором принимает tesseract
# 'eng', 'ukr', 'rus+eng+ukr'
# можно указывать несколько через + но чем больше чем хуже, может путать буквы из разных языков даже в одном слове
# пакет для tesseract с этими языками должен быть установлен 
# https://tesseract-ocr.github.io/tessdoc/Data-Files-in-different-versions.html
ocr_language = 'rus'


# ключи для клауда 'sessionKey=sk....' искать на сайте claude.ai через американский прокси
claudeai_keys = ['sessionKey=sk-xxxxxxxxxx',] или None
# прокси для клода не получилось сделать, так что надо использовать впн туннель, 
# перенаправить в него адреса которые резолвятся из nslookup claude.ai

# для рисования (платное и пока отключено)
# https://replicate.com/account/api-tokens
replicate_token = 'ххх'

# показывать ли рекламу группы Neural Networks Forum при рисовании, что бы люди туда уходили рисовать и отстали от моего бота
enable_image_adv = False

# кодовые слова которые можно использовать вместо команды /music
MUSIC_WORDS = ['муз', 'ytb']

# https://ai.google.dev/
gemini_keys = ['xxx', 'yyy']
# прокси для gemini pro, если не указать то сначала попытается работать
# напрямую а если не получится то будет постоянно искать открытые прокси
# gemini_proxies = ['http://172.28.1.5:3128', 'socks5h://172.28.1.5:1080']

# максимальный размер для скачивания музыки с ютуба в секундах
# если есть локальный сервер то можно много, если нет то 20 минут
MAX_YTB_SECS = 6*60*60
# MAX_YTB_SECS = 20*60

# прокси для рисования бингом
# bing_proxy = ['socks5://172.28.1.4:1080', 'socks5://172.28.1.7:1080']
bing_proxy = []
```

Что бы работало рисование бингом надо заменить куки, взять с сайта bing.com раздел чат, попасть туда можно только с ип приличных стран и с аккаунтом в микрософте. С помощью браузерного расширения cookie editor надо достать куки с именем _U и передать боту через команду /bingcookie xxx



7. Запустить ./tb.py

Можно собрать и запустить докер образ. Ну или нельзя Ж) давно не проверял.

В докер файл можно добавить свой файл cfg.py


```
docker build  -t tb1 .
или
docker build --no-cache -t tb1 .
или
docker build --no-cache -t tb1 . &> build.log

docker run -d --env TOKEN='xxx' --name tb1 --restart unless-stopped tb1
или
docker run --env TOKEN='xxx' --name tb1 --restart unless-stopped tb1
или
docker run -d --env TOKEN='xxx' --env OPENAI_KEY='yyy' -e TZ=Asia/Vladivostok --name tb1 --restart unless-stopped tb1
```


## Использование

Перед тем как приглашать бота на канал надо в настройке бота у @Botfather выбрать бота, затем зайти в `Bot Settings-Group Privacy-` и выключить. После того как бот зашел на канал надо включить опять. Это нужно для того что бы у бота был доступ к сообщениям на канале.

## Лицензия

Лицензия, под которой распространяется проект.
