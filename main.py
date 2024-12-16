import uvicorn
import fastapi
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.responses import FileResponse
import telebot
import json
from datetime import datetime
import os
import re
from base64 import b64decode
from search_contacts import (search_in_excel, parcing_row, encode_to_base64,
                             decode_from_base64, get_sheetname_by_index, get_index_by_sheetname, test_data_array)

BOT_NAME = 'info_bot'

MEMBERS_JSON = '/path-to-json/members.json'
PDFS_PATH = '/path-to-files/PDFs'
CONTACTS_PATH = '/path-to-contacts/contacts-photo.xlsx'


API_TOKEN = 'API_TOKEN'
WEBHOOK_HOST = 'bot-host.site'
WEBHOOK_PATH = 'info_bot'

WEBHOOK_URL = "https://{}/{}/".format(WEBHOOK_HOST, WEBHOOK_PATH)


GROUP_CHAT_ID = '-CHAT-ID'
GROUP_CHAT_NAME = 'Название группы'

def recursive_file_search(directory, search_word, found_files=""):
    for item in os.listdir(directory):
        item_path = os.path.join(directory, item)
        if os.path.isdir(item_path):
            if search_word.lower() in item.lower():
                found_files += "Найдено '{}' в директории: {}\n".format(search_word,
                                                                        item_path.replace(PDFS_PATH, ""))
            found_files = recursive_file_search(item_path, search_word, found_files)
        else:
            if search_word.lower() in item.lower():
                found_files += "Найдено '{}' в файле: {}\n".format(search_word,
                                                                   item_path.replace(PDFS_PATH, ""))
    return found_files


bot = telebot.TeleBot(API_TOKEN)

app = fastapi.FastAPI(docs=None, redoc_url=None)

templates = Jinja2Templates(directory="/var/www/bot-host.site")


@app.get("/user/{id}", response_class=HTMLResponse)
async def get_user(request: fastapi.Request, id: str):
    path_matches = re.match(r'^(\d{1,})/(\d{1,})$', decode_from_base64(id))
    user_data = parcing_row(CONTACTS_PATH, get_sheetname_by_index(CONTACTS_PATH,
                                                                  int(path_matches[1])), int(path_matches[2]))

    if test_data_array(user_data) == '' and user_data[5] != 'None':
        match = re.match(r'^8(\d{10})$', user_data[5].replace("-", "").replace(" ", ""))
        user_data[5] = f'+7{match[1]}'

    return templates.TemplateResponse(request=request, name="main.html", context={
        "department": user_data[0],
        "room": user_data[1],
        "name": user_data[2],
        "position": user_data[3],
        'localphone': user_data[4],
        "phone":  user_data[5],
        'email': user_data[6],
        'photo': user_data[7]
    })


@app.post(f'/{WEBHOOK_PATH}/')
def process_webhook(update: dict):
    """
    Process webhook calls
    """
    if update:
        update = telebot.types.Update.de_json(update)
        bot.process_new_updates([update])
    else:
        return



def startKeyboard():
    keyboard = telebot.types.InlineKeyboardMarkup(row_width=2)
    btn1 = telebot.types.InlineKeyboardButton(text='🗂️ Поиск документации', callback_data='start_search')
    btn2 = telebot.types.InlineKeyboardButton('❔ Помощь', callback_data='start_help')
    btn3 = telebot.types.InlineKeyboardButton('Вернуться в главное меню', callback_data='start_again')
    btn4 = telebot.types.InlineKeyboardButton('🗃️ Поиск по контактам', callback_data='start_contact')
    keyboard.add(btn2, btn4)
    return keyboard


@bot.message_handler(commands=['start'])
def send_welcome(message):

    chat_member = bot.get_chat_member(GROUP_CHAT_ID, message.chat.id)

    if chat_member.status in ['member', 'administrator', 'creator']:
        bot.send_message(message.chat.id, f"Здравствуйте {message.chat.username}! Вы в группе "
                                          f"{GROUP_CHAT_NAME}\n *ГЛАВНОЕ МЕНЮ:*",
                              parse_mode="Markdown", reply_markup=startKeyboard())
    else:
        bot.send_message(message.chat.id, f"Для использования бота вы должны состоять в группе {GROUP_CHAT_NAME}",
                              parse_mode="Markdown")


@bot.callback_query_handler(func=lambda call: call.data.startswith('start_'))
def callback_start(call):
    if call.data == 'start_search':
        send_search(call.message)
    elif call.data == 'start_contact':
        send_contact(call.message)
    elif call.data == 'start_help':
        send_help(call.message)
    elif call.data == 'start_download':
        send_download(call.message)
    elif call.data == 'start_again':
        bot.send_message(call.message.chat.id, f"*ГЛАВНОЕ МЕНЮ:*", parse_mode="Markdown", reply_markup=startKeyboard())


def send_contact(message):
    user_markup = telebot.types.InlineKeyboardMarkup(row_width=1)
    btn1 = telebot.types.InlineKeyboardButton('Вернуться в главное меню', callback_data='start_again')
    user_markup.add(btn1)
    msg = bot.send_message(message.chat.id, 'Введите искомую фразу/номер и нажмите отправить', reply_markup=user_markup)
    bot.register_next_step_handler(msg, process_contact_step)


def process_contact_step(message):
    try:
        searching_text = message.text
        # bot.send_message(message.chat.id, f"Ищем по фамилии: {searching_text}")

        results = search_in_excel(CONTACTS_PATH, searching_text)
        return_text = f'{searching_text} - не найдено'
        for result in results:
            return_text = f'Поиск завершен'

            user_data = parcing_row(CONTACTS_PATH, result['sheet'], result['row'])

            if test_data_array(user_data) == '' and user_data[5] != 'None':
                match = re.match(r'^8(\d{10})$', user_data[5].replace("-", "").replace(" ", ""))
                user_data[5] = f'<a href="+7{match[1]}">+7{match[1]}</a>'

            html_string = (f'<strong>{user_data[2]}</strong>\n'
                           f'{user_data[3]}\n'
                           f'<em>{user_data[0]}</em>\n'
                           f'Каб: {user_data[1]}\n'
                           f'Вн. тел: {user_data[4]}\n'
                           f'{user_data[5]}\n'
                           f'{user_data[6]}\n')
            if user_data[7] != 'None':  # if user has photo

                sheetindex = get_index_by_sheetname(CONTACTS_PATH, result["sheet"])
                path = f'{sheetindex}/{int(result["row"])}'
                html_string = html_string +  f'<a href="https://bot-host.site/user/{encode_to_base64(path)}">Анкета</a>'
                bot.send_photo(message.chat.id, f'https://bot-host.site/photos/{user_data[7]}', 
                               caption=html_string, parse_mode='HTML')
            else:
                bot.send_message(message.chat.id, html_string, parse_mode='HTML')

        user_markup = telebot.types.InlineKeyboardMarkup(row_width=1)
        btn1 = telebot.types.InlineKeyboardButton('🗃️ Искать еще', callback_data='start_contact')
        btn2 = telebot.types.InlineKeyboardButton('Вернуться в главное меню', callback_data='start_again')
        user_markup.add(btn1, btn2)
        bot.send_message(message.chat.id, return_text, reply_markup=user_markup)
    except Exception as e:
        bot.reply_to(message, 'oooops')

def send_help(message):
    user_markup = telebot.types.InlineKeyboardMarkup(row_width=1)
    btn1 = telebot.types.InlineKeyboardButton('Вернуться в главное меню', callback_data='start_again')
    user_markup.add(btn1)
    bot.send_message(message.chat.id, 'Это простой бот который может искать документацию и контакты '
                                      'по ключевым словам', reply_markup=user_markup)




def send_download(message):
    user_markup = telebot.types.InlineKeyboardMarkup(row_width=1)
    btn1 = telebot.types.InlineKeyboardButton('Вернуться в главное меню', callback_data='start_again')
    user_markup.add(btn1)
    msg = bot.send_message(message.chat.id, 'Введите путь к файлу который нужно скачать', reply_markup=user_markup)
    bot.register_next_step_handler(msg, process_download_step)

def process_download_step(message):
    try:
        downloading_file = message.text
        bot.send_document(message.chat.id, open(PDFS_PATH + downloading_file, 'rb'))
        user_markup = telebot.types.InlineKeyboardMarkup(row_width=1)
        btn1 = telebot.types.InlineKeyboardButton('Вернуться в главное меню', callback_data='start_again')
        user_markup.add(btn1)
        bot.send_message(message.chat.id, f" - ", reply_markup=user_markup)
    except Exception as e:
        bot.reply_to(message, 'Ошибка: не верный путь к файлу, или файл пустой')

def send_search(message):
    user_markup = telebot.types.InlineKeyboardMarkup(row_width=1)
    btn1 = telebot.types.InlineKeyboardButton('Вернуться в главное меню', callback_data='start_again')
    user_markup.add(btn1)
    msg = bot.send_message(message.chat.id, 'Введите ключевое слово и нажмите отправить', reply_markup=user_markup)
    bot.register_next_step_handler(msg, process_search_step)


def process_search_step(message):
    try:
        searching_text = message.text
        bot.send_message(message.chat.id, f"Ищем: {searching_text}")
        start_directory = f'{PDFS_PATH}/'
        search_word = searching_text
        result = recursive_file_search(start_directory, search_word)
        user_markup = telebot.types.InlineKeyboardMarkup(row_width=1)
        btn1 = telebot.types.InlineKeyboardButton('Искать еще', callback_data='start_search')
        btn2 = telebot.types.InlineKeyboardButton('Вернуться в главное меню', callback_data='start_again')
        btn3 = telebot.types.InlineKeyboardButton('Скачать', callback_data='start_download')
        user_markup.add(btn1, btn2, btn3 )
        bot.send_message(message.chat.id, f"Нашлось: {result}", reply_markup=user_markup)
    except Exception as e:
        bot.reply_to(message, 'oooops')


# Remove webhook, it fails sometimes the set if there is a previous webhook
bot.remove_webhook()


# Set webhook
bot.set_webhook(
    url=WEBHOOK_URL
)


if __name__ == "__main__":
    config = uvicorn.Config(app, port=5003, log_level="info", lifespan="off")
    server = uvicorn.Server(config)
    server.run()