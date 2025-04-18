#!/usr/bin/env python3


import base64
import io
import importlib
import json
import os
import random
import re
import time
import threading
import traceback
from io import BytesIO
from multiprocessing.pool import ThreadPool

import PIL
import requests
from sqlitedict import SqliteDict
from PIL import Image

import bing_api_client
import cfg
import my_db
import my_gemini
import my_gemini_genimg
import my_glm
import my_groq
import my_log
import my_mistral
import utils
from my_nebius import txt2img as flux_nebius


DEBUG = cfg.DEBUG if hasattr(cfg, 'DEBUG') else False


# config file timestamp
CONFIG_TIMESTAMP = 0


# каждый юзер дает свои ключи и они используются совместно со всеми
# {full_chat_id as str: key as str}
# {'[9123456789] [0]': 'key1', ...}
USER_KEYS = SqliteDict('db/huggingface_user_keys.db', autocommit=True)
# list of all users keys
ALL_KEYS = []
USER_KEYS_LOCK = threading.Lock()
CURRENT_KEYS_SET = []

# {hash of image:model name, ...}
WHO_AUTOR = {}


# попробовать заблокировать параллельные вызовы бинга
BING_LOCK = threading.Lock()
# 0 - main, 1 - second instance
# если есть второй инстанс с бингом то переключаться между ними циклично
BING_SWITCH = 0


# removed keys
BAD_KEYS = []


def load_users_keys():
    """
    Load users' keys into memory and update the list of all keys available.
    """
    with USER_KEYS_LOCK:
        global USER_KEYS, ALL_KEYS
        if hasattr(cfg, 'huggin_face_api') and cfg.huggin_face_api:
            ALL_KEYS = cfg.huggin_face_api
        for user in USER_KEYS:
            key = USER_KEYS[user]
            if key not in ALL_KEYS:
                ALL_KEYS.append(key)


def upscale(image_bytes: bytes) -> bytes:
    """
    Увеличивает размер изображения, если его ширина или высота меньше 1024 пикселей,
    с сохранением хорошего качества.

    Args:
        image_bytes: Байты изображения.

    Returns:
        Байты увеличенного изображения или исходные байты, если увеличение не требуется.
    """
    try:
        image = Image.open(BytesIO(image_bytes))
        width, height = image.size

        if width < 1024 or height < 1024:
            if width > height:
                new_width = 1024
                new_height = int(height * (1024 / width))
            else:
                new_height = 1024
                new_width = int(width * (1024 / height))

            # Используем качественный алгоритм ресайза (Lanczos)
            resized_image = image.resize((new_width, new_height), Image.LANCZOS)

            # Сохраняем изображение в байты
            output_buffer = BytesIO()
            resized_image.save(output_buffer, format=image.format)
            return output_buffer.getvalue()
        else:
            return image_bytes
    except Exception as error:
        error_traceback = traceback.format_exc()
        my_log.log_huggin_face_api(f'my_genimg:upscale: {error}\n\n{error_traceback}')
        return image_bytes


def gemini_flash(prompt: str, width: int = 1024, height: int = 1024, num: int = 1, negative_prompt: str = "", user_id: str = ''):
    """
    Generates images based on a prompt using the bigmodel.cn API.

    Args:
        prompt (str): The prompt for generating the images.
        width (int, optional): The width of the images. Defaults to 1024.
        height (int, optional): The height of the images. Defaults to 1024.
        num (int, optional): The number of images to generate. Defaults to 1.

    Returns:
        list: A list of generated images in bytes format.
    """
    try:
        if num > 1:
            results = []
            for _ in range(num):
                images = gemini_flash(prompt, width, height, 1, negative_prompt)
                if not images:
                    return []
                image = images[0]
                results.append(image)
            return results

        data = my_gemini_genimg.generate_image(prompt, user_id=user_id)
        results = []
        if data:
            WHO_AUTOR[utils.fast_hash(data)] = 'Gemini 2.0 Flash Experimental'
            results.append(data)
            return results

    except Exception as error:
        error_traceback = traceback.format_exc()
        my_log.log_huggin_face_api(f'gemini 2.0 flash exp: {error}\n\n{error_traceback}')

    return []


def bing(prompt: str, moderation_flag: bool = False, user_id: str = ''):
    """
    Рисует бингом, не больше 1 потока и 20 секунд пауза между запросами
    Ограничение на размер промпта 950, хз почему


    1 кука, пауза между запросами на рисование 20 секунд

    Одновременно используй только 1 аккаунт.
    Когда с ним проблемы, то переключайся на другой и меняй IP.
    Куки обновляй с той же страны, что и прокси, например США.

    У меня так работает.
    Два прокси США, которые меняются с каждым переключением аккаунта.
    Раз в месяц я их меняю на новые.

    """
    global BING_SWITCH

    # prompt = prompt.strip()[:950] # нельзя больше 950?
    prompt = prompt.strip()

    if moderation_flag or prompt.strip() == '':
        return []

    try:
        with BING_LOCK:
            images = []
            if os.path.exists('cfg_bing.py'):
                images = bing_api_client.gen_images(prompt)

                if images:
                    my_log.log_bing_success('BING SUCCESS ' + prompt + '\n\n' + '\n'.join(images))
                else:
                    my_log.log_bing_img('BING FAILED ' + prompt)

            if any([x for x in images if not x.startswith('https://')]):
                return images

        if type(images) == list:
            return list(set(images))
    except Exception as error_bing_img:
        my_log.log_bing_img(f'my_genimg:bing: {error_bing_img}')
    return []


def remove_huggin_face_key(api_key: str):
    '''Remove an API key from the list of valid API keys'''
    try:
        BAD_KEYS.append(api_key)
        global ALL_KEYS
        try:
            ALL_KEYS.remove(api_key)
        except ValueError:
            my_log.log_huggin_face_api(f'remove_huggin_face_key: Invalid key {api_key} not found in ALL_KEYS')

        keys_to_delete = [] # Список для хранения ключей на удаление
        for user in USER_KEYS:
            if USER_KEYS[user] == api_key:
                keys_to_delete.append(user) # Добавляем ключ для удаления

        for user_key in keys_to_delete: # Удаляем ключи после итерации
            del USER_KEYS[user_key]

        if keys_to_delete:
            my_log.log_keys(f'Invalid key {api_key} removed, users {keys_to_delete}') # Логгируем удаление с указанием пользователей
        else:
            my_log.log_keys(f'Invalid key {api_key} was not associated with any user in USER_KEYS') # Логгируем, если ключ не был найден в USER_KEYS

    except Exception as error:
        error_traceback = traceback.format_exc()
        my_log.log_huggin_face_api(f'Failed to remove key {api_key}: {error}\n\n{error_traceback}')


def get_hf_proxy() -> dict or None:
    """
    Retrieves a proxy configuration for accessing Hugging Face resources.

    If a list of proxies is configured in `cfg.hf_proxy`, a random proxy
    from the list is returned. Otherwise, None is returned, indicating no proxy.

    Returns:
        dict or None: A dictionary containing 'http' and 'https' proxy URLs,
                     or None if no proxy is configured.
    """
    if hasattr(cfg, 'hf_proxy') and cfg.hf_proxy:
        proxy = {'http': random.choice(cfg.hf_proxy), 'https': random.choice(cfg.hf_proxy)}
    else:
        proxy = None
    return proxy


def get_next_key() -> str:
    """
    Retrieves a random API key from the list of valid API keys.

    Returns:
        str: A random API key.
    """
    global CURRENT_KEYS_SET

    with USER_KEYS_LOCK:
        if not CURRENT_KEYS_SET:
            CURRENT_KEYS_SET = ALL_KEYS[:]

        if CURRENT_KEYS_SET:
            random_key = random.choice(CURRENT_KEYS_SET)  # Выбираем случайный ключ
            CURRENT_KEYS_SET.remove(random_key)           # Удаляем выбранный ключ из списка
            return random_key
        else:
            raise Exception('No more keys available')


def huggin_face_api(prompt: str, negative_prompt: str = "", timeout: int = 60) -> list:
    """
    Calls the Hugging Face API to generate text based on a given prompt.
    
    Args:
        prompt (str): The prompt to generate text from.
    
    Returns:
        bytes: The generated text as bytes.
    """
    try:
        # reread config if changed
        global CONFIG_TIMESTAMP
        if os.path.exists('cfg.py'):
            if os.path.getmtime('cfg.py') > CONFIG_TIMESTAMP:
                if CONFIG_TIMESTAMP:
                    my_log.log_huggin_face_api('cfg.py changed')
                importlib.reload(cfg)
                CONFIG_TIMESTAMP = os.path.getmtime('cfg.py')

        if not hasattr(cfg, 'huggin_face_api'):
            return []

        if hasattr(cfg, 'huggin_face_models_urls') and cfg.huggin_face_models_urls:
            API_URL = cfg.huggin_face_models_urls
        else:
            if os.path.exists('huggin_face_models_urls.list'):
                with open('huggin_face_models_urls.list', 'r') as f:
                    API_URL = f.read().splitlines()
                API_URL = [x.strip() for x in API_URL if x.strip() and not x.strip().startswith('#')]
            else:
                API_URL = [
                "https://api-inference.huggingface.co/models/ehristoforu/dalle-3-xl-v2",
                "https://api-inference.huggingface.co/models/digiplay/Juggernaut_final",
                "https://api-inference.huggingface.co/models/RunDiffusion/Juggernaut-X-v10",
                "https://api-inference.huggingface.co/models/dataautogpt3/TempestV0.1",
                "https://api-inference.huggingface.co/models/UnfilteredAI/NSFW-gen-v2",

                # new test
                "https://api-inference.huggingface.co/models/Corcelio/mobius",
                "https://api-inference.huggingface.co/models/sd-community/sdxl-flash",
                "https://api-inference.huggingface.co/models/fluently/Fluently-XL-v4",
                "https://api-inference.huggingface.co/models/Corcelio/openvision",

            ]

        payload = json.dumps({"inputs": prompt, "negative_prompt": negative_prompt,})

        def request_img(prompt, url, p):

            n = 1
            result = []
            while n > 0:
                n -= 1

                proxy = get_hf_proxy()
                api_key = get_next_key()
                headers = {"Authorization": f"Bearer {api_key}"}

                mult_words = [
                    '2D', '3D', 'CGI', 'VFX', 'abstract', 'animate', 'animated', 'animatic',
                    'animation', 'animation_studio', 'animator', 'anime', 'art', 'asset', 'assets', 'background',
                    'blurry', 'bright colors', 'cartoon', 'cartoonish', 'cel', 'celanimation', 'cels', 'character',
                    'character_design', 'characters', 'chibi', 'childish', 'claymation', 'comic', 'compositing', 'concept_art',
                    'concept_design', 'design', 'digital', 'doujinshi', 'draw', 'drawing', 'dreamlike', 'ecchi',
                    'editing', 'effects', 'fanart', 'fantasy', 'film', 'filmmaking', 'frame', 'frames',
                    'genre', 'graphicnovel', 'graphics', 'hentai', 'illustrate', 'illustration', 'inbetween', 'kawaii',
                    'keyframe', 'lighting', 'lineart', 'loli', 'loop', 'low-contrast', 'low-resolution', 'manga',
                    'mecha', 'mocap', 'model', 'modeling', 'models', 'modern', 'motion', 'motion_capture',
                    'movie', 'narrative', 'paint', 'painting', 'palette', 'pipeline', 'pixelated', 'post-production',
                    'pre-production', 'production', 'program', 'puppet', 'puppets', 'render', 'rendering', 'rigging',
                    'rotoscoping', 'scene', 'scenes', 'script', 'scripting', 'sequence', 'sequences', 'shading',
                    'short', 'shota', 'simple', 'simplistic', 'sketch', 'software', 'stop_motion', 'stopmotion',
                    'story', 'storyboard', 'storyboards', 'style', 'sunny', 'surreal', 'technique', 'texturing',
                    'timeline', 'tool', 'tween', 'urban', 'vibrant', 'vibrant colors', 'visual', 'visual_development',
                    ]

                try:
                    if (any(word in negative_prompt for word in mult_words)
                        and any(word in url for word in ['m3lt', 'midsommarcartoon', 'FLUX.1-dev-LoRA-One-Click-Creative-Template', 'flux-ghibsky-illustration'])):
                        return []

                    if (any(word in prompt for word in mult_words)
                        and any(word in url for word in ['flux_film_foto', 'Juggernaut_final', 'NSFW-gen-v2'])):
                        return []

                    response = requests.post(url, headers=headers, json=p, timeout=timeout, proxies=proxy)
                except Exception as error:
                    my_log.log_huggin_face_api(f'my_genimg:huggin_face_api:1: {error}\nPrompt: {prompt}\nAPI key: {api_key}\nProxy: {proxy}\nURL: {url}')
                    continue

                if '"error":"Authorization header is correct, but the token seems invalid' in response.text:
                    remove_huggin_face_key(api_key)
                    api_key = get_next_key()
                    continue
                resp_text = str(response.content)[:300]
                if 'read timeout=' in resp_text or "SOCKSHTTPSConnectionPool(host='api-inference.huggingface.co', port=443): Max retries exceeded with url" in resp_text: # и так долго ждали
                    return []
                if response.content and '{"error"' not in resp_text and len(response.content) > 10000:
                    # resize small images, upscale
                    upscaled = upscale(response.content)
                    result.append(upscaled)
                    WHO_AUTOR[utils.fast_hash(upscaled)] = url.split('/')[-1]
                    return result

                if 'is currently loading","estimated_time":' in str(resp_text) or \
                    '"error":"Internal Server Error"' in str(resp_text) or \
                    '"CUDA out of memory' in str(resp_text) or \
                    '"error":"Service Unavailable"' in str(resp_text):
                    if DEBUG:
                        my_log.log_huggin_face_api(f'my_genimg:huggin_face_api:2: {resp_text} | {proxy} | {url}')
                elif response.status_code == 401 and response.reason == 'Unauthorized':
                    remove_huggin_face_key(api_key)
                else: # unknown error
                    if "allow you to make inference requests" in resp_text or \
                    "on a journey to ad" in resp_text:
                        pass
                    else:
                        my_log.log_huggin_face_api(f'my_genimg:huggin_face_api:3: {resp_text} | {proxy} | {url} | {api_key}')
                time.sleep(10)

            return result

        # ограничиваем до 2 случайных
        random.shuffle(API_URL)
        API_URL = API_URL[:2]

        pool = ThreadPool(processes=len(API_URL))
        async_results = []
        for x in API_URL:
            async_results.append(pool.apply_async(request_img, (prompt, x, payload,)))

        result = []
        for x in async_results:
            result += x.get()

        result = list(set(result))

        return result

    except Exception as unknown:
        traceback_error = traceback.format_exc()
        my_log.log2(f'tb:huggin_face_api: {unknown}\n{traceback_error}')
        return []


def huggin_face_api_one_image(
    url: str,
    positive_prompt: str,
    negative_prompt: str,
    retries: int = 5,
    delay: int = 10,
    timeout: int = 120,
    ) -> bytes:
    """
    Попытка сгенерировать изображения через Hugging Face API с заданными положительным и отрицательным промптами.
    Пытается несколько раз в случае неудачи, используя случайные ключи API.

    Args:
        url (str): URL API Hugging Face.
        positive_prompt (str): Положительный промпт.
        negative_prompt (str): Отрицательный промпт.
        retries (int): Количество попыток.
        delay (int): Задержка между попытками (в секундах).

    Returns:
        bytes: Изображение в байтах.
    """
    if not ALL_KEYS:
        # raise Exception("Нет доступных ключей для Hugging Face API")
        return []

    payload = json.dumps({
        "inputs": positive_prompt, 
        "negative_prompt": negative_prompt,
    })

    start_time = time.time()
    for attempt in range(retries):
        api_key = get_next_key()
        headers = {"Authorization": f"Bearer {api_key}"}
        proxy = get_hf_proxy()

        try:
            response = requests.post(url, headers=headers, data=payload, timeout=timeout, proxies=proxy)

            if response.status_code == 200 and len(response.content) > 100:
                # my_log.log_huggin_face_api(f"Успешно сгенерировано изображение на попытке {attempt + 1}")
                return response.content
            elif response.status_code == 401 and response.reason == 'Unauthorized':
                remove_huggin_face_key(api_key)

            # Логируем ошибку статуса
            # my_log.log_huggin_face_api(f"huggin_face_api_one_image: Попытка {attempt + 1} не удалась: статус {response.status_code}, ответ: {response.text[:300]}")

        except Exception as e:
            error_traceback = traceback.format_exc()
            my_log.log_huggin_face_api(f"huggin_face_api_one_image: {str(e)}\nТрассировка: {error_traceback}")

        end_time = time.time()
        if end_time - start_time > timeout:
            return b''

        time.sleep(delay)  # Задержка перед новой попыткой

    # raise Exception("Не удалось получить изображение после нескольких попыток")
    return b''


def size_of_image(data: bytes):
    """
    Calculate the size of an image from the given byte data.

    Args:
        data (bytes): The byte data of the image.

    Returns:
        tuple: A tuple containing the width and height of the image.
    """
    img = PIL.Image.open(io.BytesIO(data))
    return img.size


def glm(prompt: str, width: int = 1024, height: int = 1024, num: int = 1, negative_prompt: str = ""):
    """
    Generates images based on a prompt using the bigmodel.cn API.

    Args:
        prompt (str): The prompt for generating the images.
        width (int, optional): The width of the images. Defaults to 1024.
        height (int, optional): The height of the images. Defaults to 1024.
        num (int, optional): The number of images to generate. Defaults to 1.

    Returns:
        list: A list of generated images in bytes format.
    """
    try:
        if hasattr(cfg, 'GLM_IMAGES') and cfg.GLM_IMAGES:
            images = my_glm.txt2img(prompt, user_id='-')
            results = []
            if images:
                for image in images:
                    data = utils.download_image_as_bytes(image)
                    WHO_AUTOR[utils.fast_hash(data)] = 'bigmodel.cn cogView-3-plus'
                    results.append(data)
                return results

    except Exception as error:
        error_traceback = traceback.format_exc()
        my_log.log_huggin_face_api(f'glm: {error}\n\n{error_traceback}')

    return []


# def kandinski_old(prompt: str, width: int = 1024, height: int = 1024, num: int = 1, negative_prompt: str = ""):
#     """
#     Generates images based on a prompt using the KANDINSKI_API.

#     Args:
#         prompt (str): The prompt for generating the images.
#         width (int, optional): The width of the images. Defaults to 1024.
#         height (int, optional): The height of the images. Defaults to 1024.
#         num (int, optional): The number of images to generate. Defaults to 1.

#     Returns:
#         list: A list of generated images in bytes format.
#     """
#     try:
#         if not hasattr(cfg, 'KANDINSKI_API') or not cfg.KANDINSKI_API:
#             return []
#         keys = cfg.KANDINSKI_API[:]
#         key = random.choice(keys)
#         AUTH_HEADERS = {
#             'X-Key': f'Key {key[0]}',
#             'X-Secret': f'Secret {key[1]}',
#         }
#         params = {
#             "type": "GENERATE",
#             "numImages": num,
#             "width": width,
#             "height": height,
#             "generateParams": {
#             "query": f"{prompt}"
# 		    }
# 	    }
#         def get_model():
#             response = requests.get('https://api-key.fusionbrain.ai/key/api/v1/models', headers=AUTH_HEADERS)
#             data = response.json()
#             return data[0]['id']

#         data = {
#             'model_id': (None, get_model()),
#             'params': (None, json.dumps(params), 'application/json')
#         }
#         response = requests.post('https://api-key.fusionbrain.ai/key/api/v1/text2image/run', headers=AUTH_HEADERS, files=data, timeout=120)
#         data = response.json()
#         try:
#             uuid = data['uuid']
#         except KeyError:
#             return []

#         def check_generation(request_id, attempts=10, delay=10):
#             while attempts > 0:
#                 response = requests.get('https://api-key.fusionbrain.ai/key/api/v1/text2image/status/' + request_id, headers=AUTH_HEADERS)
#                 data = response.json()
#                 if  data['censored']:
#                     return []
#                 if data['status'] == 'DONE':
#                     return data['images']
#                 attempts -= 1
#                 time.sleep(delay)

#         images = check_generation(uuid)
#         if images:
#             results = []
#             for image in images:
#                 data = base64.b64decode(image)
#                 WHO_AUTOR[utils.fast_hash(data)] = 'fusionbrain.ai'
#                 results.append(data)
#             return results
#         else:
#             return []

#     except Exception as error:
#         error_traceback = traceback.format_exc()
#         my_log.log_huggin_face_api(f'my_genimg:kandinski: {error}\n\n{error_traceback}')

#     return []


class FusionBrainAPI:

    def __init__(self, url, api_key, secret_key):
        self.URL = url
        self.AUTH_HEADERS = {
            'X-Key': f'Key {api_key}',
            'X-Secret': f'Secret {secret_key}',
        }

    def get_pipeline(self):
        response = requests.get(self.URL + 'key/api/v1/pipelines', headers=self.AUTH_HEADERS)
        data = response.json()
        return data[0]['id']

    def generate(self, prompt, pipeline, images=1, width=1024, height=1024, negative_prompt=""):
        params = {
            "type": "GENERATE",
            "numImages": images,
            "width": width,
            "height": height,
            "generateParams": {
                "query": f"{prompt}"
            }
        }
        if negative_prompt:
            params["negativePromptDecoder"] = negative_prompt
        # Add style here if needed, e.g., params["style"] = "ANIME"
        data = {
            'pipeline_id': (None, pipeline),
            'params': (None, json.dumps(params), 'application/json'),
            'number_of_files': (None, str(images))
        }
        response = requests.post(self.URL + 'key/api/v1/pipeline/run', headers=self.AUTH_HEADERS, files=data)
        data = response.json()
        return data['uuid']

    def check_generation(self, request_id, attempts=10, delay=10):
        while attempts > 0:
            response = requests.get(self.URL + 'key/api/v1/pipeline/status/' + request_id, headers=self.AUTH_HEADERS)
            data = response.json()
            if data['status'] == 'DONE':
                return base64.b64decode(data['result']['files'][0])

            attempts -= 1
            time.sleep(delay)

        return None


def kandinski(prompt: str, width: int = 1024, height: int = 1024, num: int = 1, negative_prompt: str = ""):
    """
    Generates images based on a prompt using the Fusion Brain Kandinsky API (aligned with provided docs).

    Args:
        prompt (str): The prompt for generating the images.
        width (int, optional): The width of the images. Defaults to 1024. Recommended multiple of 64.
        height (int, optional): The height of the images. Defaults to 1024. Recommended multiple of 64.
        num (int, optional): The number of images to generate. NOTE: API docs state only 1 is supported. Defaults to 1.
        negative_prompt (str, optional): Negative prompt to guide the generation away from certain elements. Defaults to "".

    Returns:
        list: A list of generated images in bytes format, or an empty list on failure/censorship.
    """
    if num != 1:
        print(f"Warning: Kandinsky API documentation states only num=1 is supported. Forcing num=1.")
        num = 1 # Enforce API limitation

    # игнорируем негативный промпт потому что бот его не так как надо делает
    negative_prompt = ''

    try:
        if not hasattr(cfg, 'KANDINSKI_API') or not cfg.KANDINSKI_API:
            my_log.log_huggin_face_api('my_genimg:kandinski: KANDINSKI_API not configured in cfg.')
            return []

        keys = cfg.KANDINSKI_API[:]
        if not keys:
             my_log.log_huggin_face_api('my_genimg:kandinski: No API keys found in cfg.KANDINSKI_API.')
             return []

        key_pair = random.choice(keys)
        api_key = key_pair[0]
        secret_key = key_pair[1]


        api = FusionBrainAPI('https://api-key.fusionbrain.ai/', api_key, secret_key)
        pipeline_id = api.get_pipeline()
        uuid = api.generate(
            prompt,
            pipeline_id,
            width=width,
            height=height,
            negative_prompt=negative_prompt
            )
        data = api.check_generation(uuid)
        if not data:
            return []

        results = []
        WHO_AUTOR[utils.fast_hash(data)] = 'fusionbrain.ai'
        results.append(data)
        return results

    except Exception as error:
        # Catch-all for unexpected errors
        error_traceback = traceback.format_exc()
        my_log.log_huggin_face_api(f'my_genimg:kandinski: Unhandled exception: {error}\n\n{error_traceback}')
        return []


def get_reprompt(prompt: str, conversation_history: str = '', chat_id: str = '') -> tuple[str, str] | None:
    """
    Function to get a reprompt for image generation based on user's prompt and conversation history.
    Parameters:
    - prompt: a string containing the user's prompt
    - conversation_history: a string containing the conversation history
    Returns:
    - a string representing the reprompt for image generation
    """
    try:
        conversation_history = conversation_history.replace('𝐔𝐒𝐄𝐑:', 'user:')
        conversation_history = conversation_history.replace('𝐁𝐎𝐓:', 'bot:')

        prompt = prompt.strip()
        dont_translate = prompt.startswith('!')
        prompt = re.sub(r'^!+', '', prompt).strip()

        query = f'''
User want to create image with text to image generator.
Repromt user's PROMPT for image generation.
Generate a good detailed prompt in english language, image generator accept only english so translate if needed.
Answer as a professional image prompt engineer, answer completely grammatically correct and future rich, add details if it was short.
A negative prompt in image generation lets you specify what you DON'T want to see in the picture. It helps exclude unwanted objects, styles, colors, or other characteristics, giving you more control over the result and speeding up the generation process.

Example:

Prompt: "Cat in a wizard hat"

Negative prompt: "sad, angry, blurry, cartoon"

Result: The AI will generate an image of a cat in a wizard hat that looks realistic, rather joyful or neutral, not sad or angry, and the image will be sharp, not blurry.

Start your prompt with word Generate.


User's PROMPT: {prompt}

Dialog history: {conversation_history}

Using this JSON schema:
  reprompt = {{"was_translated": str, "lang_from": str, "reprompt": str, "negative_reprompt": str, "moderation_sexual": bool, "moderation_hate": bool}}
Return a `reprompt`
'''

        negative = ''
        reprompt = ''
        r = ''

        if not r:
            r = my_gemini.get_reprompt_for_image(query, chat_id)
        if r:
            reprompt, negative, moderation_sex, moderation_hate = r
            if moderation_sex or moderation_hate:
                return 'MODERATION', None
        if not reprompt:
            r = my_mistral.get_reprompt_for_image(query, chat_id)
            if r:
                reprompt, negative, moderation_sex, moderation_hate = r
                if moderation_sex or moderation_hate:
                    return 'MODERATION', None

    except Exception as error:
        error_traceback = traceback.format_exc()
        my_log.log_huggin_face_api(f'my_genimg:get_reprompt: {error}\n\nPrompt: {prompt}\n\n{error_traceback}')
    if dont_translate:
        my_log.log_reprompts(f'get_reprompt:\n\n{prompt}\n\n{prompt}\n\nNegative: {negative}')
    else:
        my_log.log_reprompts(f'get_reprompt:\n\n{prompt}\n\n{reprompt}\n\nNegative: {negative}')

    if dont_translate:
        return prompt, negative

    return reprompt, negative


def gen_images_bing_only(prompt: str, user_id: str = '', conversation_history: str ='', iterations: int = 1) -> list:
    if iterations == 0:
        iterations = 1

    if prompt.strip() == '':
        return []

    # переводим на английский и модерируем
    reprompt, _ = get_reprompt(prompt, conversation_history)

    if reprompt == 'MODERATION':
        # если сработала модерация но юзер в белом списке то ок
        if hasattr(cfg, 'ALLOW_PASS_NSFW_FILTER') and utils.extract_user_id(user_id) in cfg.ALLOW_PASS_NSFW_FILTER:
            reprompt = prompt
        # если сработала модерация то возвращаем ошибку
        else:
            return ['moderation',]

    # если промпт начинается с ! то не переводим
    if prompt.startswith('!'):
        reprompt = re.sub(r'^!+', '', prompt).strip()


    if reprompt.strip():
        result = []
        for _ in range(iterations):
            r = bing(reprompt, user_id=user_id)
            if r:
                result += r
            else:
                # если не получилось рисовать то выходим на случай когда промпт плохой, но белому списку доверяем
                if hasattr(cfg, 'ALLOW_PASS_NSFW_FILTER') and utils.extract_user_id(user_id) in cfg.ALLOW_PASS_NSFW_FILTER:
                    continue
                else:
                    break

        return result

    return []


def flux_nebius_gen1(prompt: str, negative_prompt: str, model: str = None):
    '''
    Generate images with Flux Nebius model. Flux dev
    '''
    try:
        image = flux_nebius(prompt, negative_prompt, model)
        if image:
            results = []
            WHO_AUTOR[utils.fast_hash(image)] = 'nebius.ai black-forest-labs/flux-dev'
            results.append(image)
            return results
        else:
            return []
    except Exception as error:
        traceback_error = traceback.format_exc()
        my_log.log_huggin_face_api(f'flux_nebius_gen1: {error}\n{traceback_error}')
        return []


def gen_images(prompt: str, moderation_flag: bool = False,
               user_id: str = '',
               conversation_history: str = '',
               use_bing: bool = True) -> list:
    """рисует одновременно всеми доступными способами"""

    if not user_id:
        user_id = 'test'

    if prompt.strip() == '':
        return []

    negative = ''
    original_prompt = prompt

    reprompt, negative = get_reprompt(prompt, conversation_history, user_id)
    if reprompt == 'MODERATION':
        return ['moderation',]

    if reprompt:
        prompt = reprompt
    else:
        return []

    bing_prompt = original_prompt if original_prompt.startswith('!') else prompt
    bing_prompt = re.sub(r'^!+', '', bing_prompt).strip()

    pool = ThreadPool(processes=9)

    if use_bing:
        async_result1 = pool.apply_async(bing, (bing_prompt, moderation_flag, user_id))

        async_result2 = pool.apply_async(kandinski, (prompt, 1024, 1024, 1, negative))
        async_result3 = pool.apply_async(kandinski, (prompt, 1024, 1024, 1, negative))

        async_result4 = pool.apply_async(huggin_face_api, (prompt, negative))

        async_result9 = pool.apply_async(glm, (prompt, negative))

        async_result10 = pool.apply_async(gemini_flash, (prompt, 1024, 1024, 2, negative, user_id))

        result = (async_result1.get() or []) + \
                (async_result2.get() or []) + \
                (async_result3.get() or []) + \
                (async_result4.get() or []) + \
                (async_result9.get() or []) + \
                (async_result10.get() or [])
    else:
        async_result2 = pool.apply_async(kandinski, (prompt, 1024, 1024, 1, negative))
        async_result3 = pool.apply_async(kandinski, (prompt, 1024, 1024, 1, negative))

        async_result4 = pool.apply_async(huggin_face_api, (prompt, negative))

        async_result9 = pool.apply_async(glm, (prompt, negative))

        async_result10 = pool.apply_async(gemini_flash, (prompt, 1024, 1024, 2, negative, user_id))

        result = (async_result2.get() or []) + \
                (async_result3.get() or []) + \
                (async_result4.get() or []) + \
                (async_result9.get() or []) + \
                (async_result10.get() or [])

    return result


def test_hkey(key: str):
    '''test huggingface key'''

    if key in BAD_KEYS:
        return False

    API_URL = [
        "https://api-inference.huggingface.co/models/ehristoforu/dalle-3-xl-v2",
        "https://api-inference.huggingface.co/models/digiplay/Juggernaut_final",
        "https://api-inference.huggingface.co/models/RunDiffusion/Juggernaut-X-v10",
        "https://api-inference.huggingface.co/models/dataautogpt3/TempestV0.1",
        "https://api-inference.huggingface.co/models/UnfilteredAI/NSFW-gen-v2",
    ]

    payload = json.dumps({"inputs": 'golden apple', "negative_prompt": 'big',})

    n = 1
    while n > 0:
        n -= 1

        proxy = get_hf_proxy()
        api_key = key
        headers = {"Authorization": f"Bearer {api_key}"}

        try:
            response = requests.post(API_URL[0], headers=headers, json=payload, timeout=10, proxies=proxy)
        except Exception as error:
            # print(error)
            my_log.log_keys(f'hf key test error: {api_key}\n\n{str(error)}')
            continue

        try:
            resp_text = response.text
        except:
            return True
        # print(resp_text)
        if 'Authorization header is correct, but the token seems invalid' in resp_text:
            my_log.log_keys(f'hf key test error: {resp_text}\n{api_key}\n\n{str(response)}')
            return False

    return True


def guess_hf_url(url: str) -> str:
    if url.startswith('http'):
        return url
    else:
        if '/' in url:
            url = 'https://api-inference.huggingface.co/models/' + url
        else:
            try:
                if os.path.exists('huggin_face_models_urls.list'):
                    with open('huggin_face_models_urls.list', 'r') as f:
                        API_URL = f.read().splitlines()
                    API_URL = [x.strip() for x in API_URL if x.strip() and not x.strip().startswith('#')]
                    for x in API_URL:
                        if url in x:
                            url = x
                            break
                    if not url.startswith('http'):
                        return ''
            except:
                return ''
    return url


def gen_one_image(prompt: str,
               user_id: str = '',
               url: str = '',
               ) -> bytes:
    """рисует указанной в урле моделькой хаггинг фейса"""

    url = guess_hf_url(url)
    if not url or not url.startswith('https://api-inference.huggingface.co/models/'):
        return None

    if not user_id:
        user_id = 'test'

    if prompt.strip() == '':
        return None

    negative = ''

    reprompt = ''

    reprompt, negative = get_reprompt(prompt, '', user_id)
    if reprompt == 'MODERATION':
        return None

    if reprompt:
        prompt = reprompt
    else:
        return None

    result = huggin_face_api_one_image(
        url,
        prompt,
        negative
        )

    return result


if __name__ == '__main__':
    my_db.init()
    load_users_keys()
    my_groq.load_users_keys()
    my_gemini.load_users_keys()
    my_mistral.load_users_keys()

    # print(get_reprompt('Потрясающая блондинка с длинными распущенными волосами сидит на деревянной лестнице. На ней минимум одежды, ее тело полностью видно с акцентом на вульву, демонстрируя ее гладкую, безупречную кожу и естественную красоту. Освещение мягкое и естественное, подчеркивающее ее изгибы и текстуру кожи. Высокая детализация, разрешение 8K, фотореалистичная фотография, отмеченная наградами.'))
    # print(get_reprompt('картину где бабушка сидит во рту с огурцами  рядом сидит ее внучка пишет математику,а сверху бог летает'))

    # print(gen_images('golden apple', use_bing=False))

    # print(huggin_face_api_one_image('https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-3.5-large-turbo', 'golden apple', ''))

    # r = gemini_flash('golden apple', num = 2)
    # print(r)


    r = kandinski('рука ладонью вверх все пальцы отчетливо видно', 1024, 1024, 1, negative_prompt = 'ugly')
    with open(r'C:\Users\user\Downloads\1.jpg', 'wb') as f:
        f.write(r[0])

    my_db.close()