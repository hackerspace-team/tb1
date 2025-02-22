#!/usr/bin/env python3
# https://github.com/settings/tokens
# https://github.com/marketplace/models/azure-openai/gpt-4o-mini/playground
# https://docs.github.com/en/github-models/prototyping-with-ai-models#rate-limits


import base64
import time
import threading
import traceback

from openai import OpenAI
from sqlitedict import SqliteDict

import cfg
import my_db
import my_log


BASE_URL = 'https://models.inference.ai.azure.com'

# сколько запросов хранить
MAX_MEM_LINES = 20
MAX_HIST_CHARS = 12000
MAX_HIST_CHARS_4K = 6000

# блокировка чатов что бы не испортить историю
# {id:lock}
LOCKS = {}

# не принимать запросы больше чем, это ограничение для телеграм бота, в этом модуле оно не используется
MAX_REQUEST = 8000
KEYS_LOCK = threading.Lock()


DEFAULT_MODEL = 'gpt-4o-mini'
BIG_GPT_MODEL = 'gpt-4o'
DEEPSEEK_R1_MODEL = 'DeepSeek-R1'
DEEPSEEK_R1_MODEL_FALLBACK = 'gpt-4o-mini'


CURRENT_KEY_SET = []

# каждый юзер дает свои ключи и они используются совместно со всеми
# каждый ключ дает всего 50/150 запросов в сутки так что чем больше тем лучше
# {full_chat_id as str: key}
# {'[9123456789] [0]': 'key', ...}
ALL_KEYS = []
USER_KEYS = SqliteDict('db/github_user_keys.db', autocommit=True)
USER_KEYS_LOCK = threading.Lock()


def get_next_key() -> str:
    """
    Retrieves the next API key in a round-robin fashion.

    Returns:
        str: The next available API key.

    Raises:
        Exception: If no API keys are available.
    """
    global CURRENT_KEY_SET
    with KEYS_LOCK:
        if not CURRENT_KEY_SET:
            if ALL_KEYS:
                CURRENT_KEY_SET = ALL_KEYS[:]
        if CURRENT_KEY_SET:
            return CURRENT_KEY_SET.pop(0)
        else:
            raise Exception('No api keys')


def clear_mem(mem: list, user_id: str) -> list:
    """
    Clears the memory (chat history) for a given user, ensuring it does not exceed the maximum allowed size.

    Args:
        mem (list): The chat history list.
        user_id (str): The user's ID.

    Returns:
        list: The trimmed chat history.
    """
    while True:
        sizeofmem = count_tokens(mem)
        if sizeofmem <= MAX_HIST_CHARS:
            break
        try:
            mem = mem[2:]
        except IndexError:
            mem = []
            break

    return mem[-MAX_MEM_LINES * 2 :]


def clear_mem2(mem: list, user_id: str) -> list:
    """
    Clears the memory (chat history) for a given user, ensuring it does not exceed the maximum allowed size.
    Version for 4k context (DeepSeek R1)

    Args:
        mem (list): The chat history list.
        user_id (str): The user's ID.

    Returns:
        list: The trimmed chat history.
    """
    while True:
        sizeofmem = count_tokens(mem)
        if sizeofmem <= MAX_HIST_CHARS_4K:
            break
        try:
            mem = mem[2:]
        except IndexError:
            mem = []
            break

    return mem[-MAX_MEM_LINES * 2 :]


def count_tokens(mem: list) -> int:
    """
    Counts the total number of tokens in the chat history.

    Args:
        mem (list): The chat history list.

    Returns:
        int: The total number of tokens.
    """
    return sum([len(m['content']) for m in mem])


def ai(prompt: str = '',
       mem = None,
       user_id: str = '',
       system: str = '',
       model = DEFAULT_MODEL, # gpt-4o-mini, gpt-4o, DeepSeek-R1,...
       temperature: float = 1,
       max_tokens: int = 4000,
       timeout: int = 120,
       key_: str = None) -> str:

    temperature = temperature/2

    if not model:
        model = DEFAULT_MODEL

    if not prompt and not mem:
        return ''

    mem_ = mem or []
    if system:
        mem_ = [{'role': 'system', 'content': system}] + mem_
    if prompt:
        mem_ = mem_ + [{'role': 'user', 'content': prompt}]

    text = ''

    start_time = time.time()

    key = ''

    for _ in range(3):
        if time.time() - start_time > timeout:
            return ''

        try:
            key = key_ or get_next_key()
            client = OpenAI(
                api_key = key,
                base_url = BASE_URL,
                )
            response = client.chat.completions.create(
                messages = mem_,
                model = model,
                max_tokens = max_tokens,
                temperature = temperature,
                timeout = timeout,
                )
        except Exception as error_other:
            if 'Bad credentials' in str(error_other):
                remove_key(key)
                continue
            if 'tokens_limit_reached' in str(error_other):
                # снять первые 2 записи из mem
                try:
                    mem__ = mem[2:]
                except IndexError:
                    return ''
                return ai(prompt, mem__, user_id, system, model, temperature, max_tokens, timeout, key_)

            my_log.log_github(f'ai:1: {error_other} | {key}')
            return ''

        try:
            text = response.choices[0].message.content
            break
        except Exception as error:
            traceback_error = traceback.format_exc()
            my_log.log_github(f'Failed to parse response: {error}\n\n{str(response)}  | {key}\n\n{traceback_error}')
            text = ''
            if key_:
                break
            time.sleep(2)

    return text


def remove_key(key: str):
    '''
    Removes a given key from the ALL_KEYS list and from the USER_KEYS dictionary.
    '''
    try:
        if key in ALL_KEYS:
            try:
                ALL_KEYS.remove(key) # Use remove for safer deletion by value
            except ValueError:
                my_log.log_keys(f'remove_key: Invalid key {key} not found in ALL_KEYS list') # Log if key not found

        keys_to_delete = [] # List to store user keys for deletion
        with USER_KEYS_LOCK:
            # remove key from USER_KEYS
            for user in USER_KEYS:
                if USER_KEYS[user] == key:
                    keys_to_delete.append(user) # Add user key to deletion list

            for user_key in keys_to_delete: # Iterate over deletion list after initial iteration
                del USER_KEYS[user_key] # Safely delete keys

            if keys_to_delete:
                my_log.log_keys(f'github: Invalid key {key} removed from users {keys_to_delete}') # Log removed keys with users
            else:
                my_log.log_keys(f'github: Invalid key {key} was not associated with any user in USER_KEYS') # Log if key not found in USER_KEYS

    except Exception as error:
        error_traceback = traceback.format_exc()
        my_log.log_github(f'Failed to remove key {key}: {error}\n\n{error_traceback}')


def update_mem(query: str, resp: str, chat_id: str):
    """
    Updates the memory with the user query and assistant response.

    Args:
        query (str): The user query.
        resp (str): The assistant response.
        chat_id (str): The chat ID.

    Returns:
        None
    """
    mem = my_db.blob_to_obj(my_db.get_user_property(chat_id, 'dialog_openrouter')) or []
    mem += [{'role': 'user', 'content': query}]
    mem += [{'role': 'assistant', 'content': resp}]
    mem = clear_mem(mem, chat_id)

    mem__ = []
    try:
        i = 0
        while i < len(mem):
            if i == 0 or mem[i] != mem[i-1]:
                mem__.append(mem[i])
            i += 1
    except Exception as error:
        error_traceback = traceback.format_exc()
        my_log.log_github(f'my_github:update_mem: {error}\n\n{error_traceback}\n\n{query}\n\n{resp}\n\n{mem}')

    my_db.set_user_property(chat_id, 'dialog_openrouter', my_db.obj_to_blob(mem__))


def chat(query: str, chat_id: str = '', temperature: float = 1, system: str = '', model: str = '', max_tokens: int = 4000) -> str:
    """
    Handles chat interaction with the AI model.

    Args:
        query (str): The user query.
        chat_id (str, optional): The chat ID. Defaults to ''.
        temperature (float, optional): The temperature for AI model. Defaults to 1.
        system (str, optional): The system message for AI model. Defaults to ''.
        model (str, optional): The AI model to use. Defaults to ''.

    Returns:
        str: The response from the AI model, or an empty string in case of failure.
    """
    if chat_id in LOCKS:
        lock = LOCKS[chat_id]
    else:
        lock = threading.Lock()
        LOCKS[chat_id] = lock
    with lock:
        mem = my_db.blob_to_obj(my_db.get_user_property(chat_id, 'dialog_openrouter')) or []

        text = ai(query, mem, user_id=chat_id, temperature = temperature, system=system, model=model, max_tokens=max_tokens)

        if text:
            my_db.add_msg(chat_id, model or DEFAULT_MODEL)
            mem += [{'role': 'user', 'content': query}]
            mem += [{'role': 'assistant', 'content': text}]
            if model == DEEPSEEK_R1_MODEL:
                mem = clear_mem2(mem, chat_id)
            else:
                mem = clear_mem(mem, chat_id)
            my_db.set_user_property(chat_id, 'dialog_openrouter', my_db.obj_to_blob(mem))
        return text
    return ''


def chat_cli(model: str = ''):
    """
    Command-line interface for interacting with the chat function.

    Args:
        model (str, optional): The AI model to use. Defaults to ''.

    Returns:
        None
    """
    while 1:
        q = input('>')
        if q == 'mem':
            print(get_mem_as_string('test'))
            continue
        r = chat(q, 'test', model = model)
        print(r)


def force(chat_id: str, text: str) -> None:
    """
    Updates the last bot answer in the chat history with the given text.

    Args:
        chat_id (str): The ID of the chat to update.
        text (str): The new text to replace the last bot answer with.

    Returns:
        None
    """
    try:
        if chat_id in LOCKS:
            lock = LOCKS[chat_id]
        else:
            lock = threading.Lock()
            LOCKS[chat_id] = lock
        with lock:
            mem = my_db.blob_to_obj(my_db.get_user_property(chat_id, 'dialog_openrouter')) or [] # Retrieve chat memory from database
            if mem and len(mem) > 1: # Check if memory exists and has at least two messages (user and bot message)
                mem[-1]['content'] = text # Update the content of the last message (assuming it's the bot's last response)
                my_db.set_user_property(chat_id, 'dialog_openrouter', my_db.obj_to_blob(mem)) # Update the chat memory in the database
    except Exception as error: # Catch any exceptions during the process
        error_traceback = traceback.format_exc() # Get full traceback of the error
        my_log.log_github(f'Failed to force message in chat {chat_id}: {error}\n\n{error_traceback}') # Log error details to GitHub


def undo(chat_id: str) -> None:
    """
    Removes the last two messages (user and bot) from the chat history for a given chat ID.

    Args:
        chat_id (str): The ID of the chat to undo the last messages from.

    Returns:
        None
    """
    try:
        if chat_id in LOCKS:
            lock = LOCKS[chat_id]
        else:
            lock = threading.Lock()
            LOCKS[chat_id] = lock
        with lock:
            mem = my_db.blob_to_obj(my_db.get_user_property(chat_id, 'dialog_openrouter')) or [] # Retrieve chat memory from database
            mem = mem[:-2] # Remove the last two messages from the memory list
            my_db.set_user_property(chat_id, 'dialog_openrouter', my_db.obj_to_blob(mem)) # Update the chat memory in the database
    except Exception as error: # Catch any exceptions during the process
        error_traceback = traceback.format_exc() # Get full traceback of the error
        my_log.log_github(f'Failed to undo chat {chat_id}: {error}\n\n{error_traceback}') # Log error details to GitHub


def reset(chat_id: str) -> None:
    """
    Resets the chat history for the specified chat ID by clearing the memory.

    Args:
        chat_id (str): The ID of the chat to reset.

    Returns:
        None
    """
    mem = [] # Initialize an empty list to represent empty memory
    my_db.set_user_property(chat_id, 'dialog_openrouter', my_db.obj_to_blob(mem)) # Update the chat memory in the database with empty memory, effectively resetting the chat


def get_last_mem(chat_id: str) -> str:
    """
    Returns the last answer for the given ID.

    Parameters:
        chat_id (str): The ID of the chat to get the history for.

    Returns:
        str:
    """
    mem = my_db.blob_to_obj(my_db.get_user_property(chat_id, 'dialog_openrouter')) or []

    last = mem[-1]
    if last:
        return last['content']
    else:
        return ''


def get_mem_as_string(chat_id: str, md: bool = False) -> str:
    """
    Returns the chat history as a string for the given ID.

    Parameters:
        chat_id (str): The ID of the chat to get the history for.

    Returns:
        str: The chat history as a string.
    """
    try:
        mem = my_db.blob_to_obj(my_db.get_user_property(chat_id, 'dialog_openrouter')) or []
        result = ''
        for x in mem:
            role = x['role']
            if role == 'user': role = '𝐔𝐒𝐄𝐑'
            if role == 'assistant': role = '𝐁𝐎𝐓'
            if role == 'system': role = '𝐒𝐘𝐒𝐓𝐄𝐌'
            text = x['content']
            if text.startswith('[Info to help you answer'):
                end = text.find(']') + 1
                text = text[end:].strip()
            if md:
                result += f'{role}:\n\n{text}\n\n'
            else:
                result += f'{role}: {text}\n'
            if role == '𝐁𝐎𝐓':
                if md:
                    result += '\n\n'
                else:
                    result += '\n'
        return result 
    except Exception as error:
        error_traceback = traceback.format_exc()
        my_log.log_github(f'get_mem_as_string: {error}\n\n{error_traceback}')
        return ''


def img2txt(
    image_data: bytes,
    prompt: str = 'Describe picture',
    model = DEFAULT_MODEL,
    temperature: float = 1,
    max_tokens: int = 2000,
    timeout: int = 120,
    chat_id: str = '',
    ) -> str:
    """
    Describes an image using the specified model and parameters.

    Args:
        image_data: The image data as bytes.
        prompt: The prompt to guide the description. Defaults to 'Describe picture'.
        model: The model to use for generating the description. Defaults to 'mistralai/pixtral-12b:free'.
        temperature: The temperature parameter for controlling the randomness of the output. Defaults to 1.
        max_tokens: The maximum number of tokens to generate. Defaults to 2000.
        timeout: The timeout for the request in seconds. Defaults to 120.

    Returns:
        A string containing the description of the image, or an empty string if an error occurs.
    """
    temperature = temperature/2
    if not model:
        model = DEFAULT_MODEL
    if not prompt:
        prompt = 'Describe picture'

    if isinstance(image_data, str):
        with open(image_data, 'rb') as f:
            image_data = f.read()

    img_b64_str = base64.b64encode(image_data).decode('utf-8')
    img_type = 'image/png'

    mem = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{img_type};base64,{img_b64_str}"},
                },
            ],
        }
    ]

    result = ''

    for _ in range(3):
        try:
            key = get_next_key()
            client = OpenAI(
                api_key = key,
                base_url = BASE_URL,
                )
            response = client.chat.completions.create(
                messages = mem,
                model = model,
                max_tokens = max_tokens,
                temperature = temperature,
                timeout = timeout,
                )
        except Exception as error_other:
            if 'Bad credentials' in str(error_other):
                remove_key(key)
                continue
            my_log.log_github(f'ai:2: {error_other}')
            return ''

        try:
            result = response.choices[0].message.content
            break
        except Exception as error:
            my_log.log_github(f'Failed to parse response: {error}\n\n{str(response)}')
            result = ''
            time.sleep(2)

    if chat_id:
        my_db.add_msg(chat_id, model)

    return result


def load_users_keys():
    """
    Load users' keys into memory and update the list of all keys available.
    """
    with USER_KEYS_LOCK:
        global ALL_KEYS
        ALL_KEYS = cfg.GITHUB_TOKENS if hasattr(cfg, 'GITHUB_TOKENS') and cfg.GITHUB_TOKENS else []
        for user in USER_KEYS:
            key = USER_KEYS[user]
            if key not in ALL_KEYS:
                ALL_KEYS.append(key)


def test_key(key: str) -> bool:
    '''
    Tests a given key by making a simple request to the GitHub AI API.
    '''
    r = ai('1+1=', key_=key.strip())
    return bool(r)


if __name__ == '__main__':
    pass
    my_db.init(backup=False)
    load_users_keys()

    # reset('test')
    chat_cli()

    # print(img2txt('C:/Users/user/Downloads/samples for ai/мат задачи.jpg', 'реши задачи, в ответе используй юникод символы для математики вместо latex выражений', model = 'gpt-4o', temperature=0))
    # print(voice2txt('C:/Users/user/Downloads/1.ogg'))

    my_db.close()
