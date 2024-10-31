import time
import telebot
from telebot import types
from pymongo import MongoClient
from dotenv import load_dotenv
from bson import ObjectId
from datetime import datetime
from telebot import apihelper
import os

load_dotenv()
bot = telebot.TeleBot(os.getenv('BOT_TOKEN'))
client = MongoClient(os.getenv('MONGO_CONNECT_URL'))
MANAGER_CHAT_ID = os.getenv('MANAGER_CHAT_ID')

db = client['Pinyatko_orderBot']
pins_collection = db['Pins']
clients_collection = db['Clients']
orders_collection = db['Orders']

carts = {}


# Обробник команди /start
@bot.message_handler(commands=['start'])
def start(message):
    # Створення клієнта в базі даних
    if clients_collection.find_one({"chatID": message.chat.id}) is None:  # якщо ще немає такого клієнта
        clients_collection.insert_one(
            {'chatID': message.chat.id, 'status': 0, 'username': message.from_user.username, 'last_message_time': None})

    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    button1 = types.KeyboardButton('Замовити пін(-и)')
    manager_button = types.KeyboardButton('Зв\'язок з менеджером')
    cart_button = types.KeyboardButton('Кошик')
    volunteer_btn = types.KeyboardButton('Я військовий(-а)/волонтер(-ка)')
    keyboard.add(button1, manager_button, volunteer_btn, cart_button)

    bot.send_message(message.chat.id, 'Оберіть потрібну дію:', reply_markup=keyboard)


# обробка звязку з менеджером
@bot.message_handler(
    func=lambda message: message.text == 'Зв\'язок з менеджером')
def manager_chat(message):
    manager_button = types.InlineKeyboardMarkup().add(
        types.InlineKeyboardButton(text='Менеджер', url='https://t.me/pinyatkomanager'))
    bot.send_message(message.chat.id, 'Чат з менеджером:', reply_markup=manager_button)


# обробка кнопки повернутись назад
@bot.message_handler(func=lambda message: message.text == 'Повернутись назад')
def back_button(message):
    start(message)


# Обробка кнопки волонтер

@bot.message_handler(func=lambda message: message.text == 'Я військовий(-а)/волонтер(-ка)')
def volunteer_processing(message):
    user_id = message.from_user.id

    # Створюємо inline кнопки
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    volonteer_btn = types.KeyboardButton("Я волонтер(-ка)")
    military_btn = types.KeyboardButton("Я військовий(-ва)")
    back_btn = types.KeyboardButton("Повернутись назад")
    keyboard.add(volonteer_btn, military_btn, back_btn)

    # Відправляємо повідомлення з кнопками
    bot.send_message(user_id, f'Ми вдячні вам за вашу роботу, тому пропонуємо Вам знижку❤️‍🩹.\n'
                              f'Волонтерам 22%\n'
                              f'Військовим 33%\n'
                              f'Оберіть потрібну кнопку, після чого з Вами зв\'яжеться наш менеджер для підтвердження',
                     reply_markup=keyboard)


@bot.message_handler(func=lambda message: message.text in ['Я військовий(-ва)', 'Я волонтер(-ка)'])
def client_status_request(message):
    try:
        user_id = message.from_user.id
        user_status = clients_collection.find_one({'chatID': user_id})['status']

        last_message_time = clients_collection.find_one({'chatID': user_id})['last_message_time']
        current_time = time.time()

        # Якщо статус користувача 5 і час з останнього повідомлення більше ніж 5 хвилин
        if user_status == 5 and (last_message_time is None or current_time - last_message_time > 10):
            bot.send_message(user_id, 'Ваш запит уже відправлено. Будь ласка, зачекайте.')
            # Оновлюємо час останнього повідомлення
            clients_collection.update_one({'chatID': user_id}, {"$set": {'last_message_time': current_time}})
        elif user_status != 5:
            if message.text == "Я військовий(-ва)":
                clients_collection.update_one({'chatID': user_id}, {"$set": {'status': 5}})
                bot.send_message(MANAGER_CHAT_ID, f'Надійшов новий запит для підтвердежння статуса військового:\n'
                                                  f'userID: {user_id}, username: @{message.from_user.username}')
                bot.send_message(user_id,
                                 f'Ваш запит на підтвердження статусу відправлено. Менеджер зв\'яжеться з Вами якнайшвидше')
            elif message.text == "Я волонтер(-ка)":
                clients_collection.update_one({'chatID': user_id}, {"$set": {'status': 5}})
                bot.send_message(MANAGER_CHAT_ID, f'Надійшов новий запит для підтвердежння статуса волонтера:\n'
                                                  f'userID: {user_id}, username: @{message.from_user.username}')
                bot.send_message(user_id,
                                 f'Ваш запит на підтвердження статусу відправлено. Менеджер зв\'яжеться з Вами якнайшвидше')
    except Exception as e:
        print(f'[ERROR] {e}')


@bot.message_handler(func=lambda message: message.text == 'Очистити кошик')
def clear_cart(message):
    try:
        user_id = message.from_user.id
        if user_id in carts:
            del carts[user_id]  # Очищення кошика користувача
            bot.send_message(message.chat.id, "Ваш кошик очищено")
        else:
            bot.send_message(message.chat.id, "Кошик вже порожній")
    except Exception as e:
        print(f'[clear_cart ERROR] {e}')


@bot.message_handler(func=lambda message: message.text == 'Кошик')
def show_cart(message):
    try:
        user_id = message.from_user.id
        cart = carts.get(user_id, {})
        if not cart:
            bot.send_message(message.chat.id, "Кошик порожній")
        else:
            response = "Вміст вашого кошика:\n"
            for pin, quantity in cart.items():
                response += f"{pin}: {quantity} шт.\n"
            total_price = get_order_price(user_id)
            response += f"\nВсього до оплати: {total_price}грн.\n"
            bot.send_message(message.chat.id, response)

        # Кнопки
        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        back_btn = types.KeyboardButton('Повернутись назад')
        confirm_btn = types.KeyboardButton('Підтвердити замовлення')
        clear_cart_btn = types.KeyboardButton('Очистити кошик')
        keyboard.add(back_btn, confirm_btn, clear_cart_btn)
        bot.send_message(message.chat.id, 'Оберіть потрібну дію:', reply_markup=keyboard)
    except Exception as e:
        print(f'[clear_cart ERROR] {e}')


# функція для обчислення ціни замовлення
def get_order_price(user_id):
    cart = carts.get(user_id, {})
    if not cart:
        return 0
    price = 0
    for pin, quantity in cart.items():
        price += pins_collection.find_one({'name': pin})['price'] * quantity
    if clients_collection.find_one({'chatID': user_id, 'status': 1}):
        return price - (price * 22 / 100)  # для волонтера -22%
    elif clients_collection.find_one({'chatID': user_id, 'status': 2}):
        return price - (price * 33 / 100)  # для військового -33%
    else:
        return price


@bot.message_handler(func=lambda message: message.text == 'Замовити пін(-и)')
def choosing_pin_menu(message):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    pins_data = pins_collection.find()
    pin_buttons = [types.KeyboardButton(pin_data['name']) for pin_data in pins_data]
    back_btn = types.KeyboardButton('Повернутись назад')
    cart_button = types.KeyboardButton('Кошик')
    keyboard.add(*pin_buttons, back_btn, cart_button)

    bot.send_message(message.chat.id, 'Оберіть пін(-и):\n', reply_markup=keyboard)


# Коли вибираєш пін:
@bot.message_handler(func=lambda message: message.text in [pin['name'] for pin in pins_collection.find()])
def handle_pin(message):
    user_id = message.from_user.id
    keyboard = types.ReplyKeyboardMarkup(row_width=3, resize_keyboard=True)
    quantity_buttons = [types.KeyboardButton(str(i)) for i in range(1, 4)]
    back_btn = types.KeyboardButton('Повернутись назад')
    keyboard.add(*quantity_buttons, back_btn)
    bot.send_message(message.chat.id, f"Виберіть кількість (або напишіть цифру в чат)",
                     reply_markup=keyboard)
    bot.register_next_step_handler(message, handle_quantity, message.text, user_id)


# Обробка кількості пінів в базі
def handle_quantity(message, pin, user_id):
    try:
        quantity = int(message.text)  # кількість пінів яку ввів замовник
        pin_data = pins_collection.find_one({'name': pin})

        if pin_data is None:
            bot.send_message(message.chat.id, "Помилка: пін не знайдено")
            choosing_pin_menu(message)
        else:
            pin_quantity = pin_data['quantity']  # кількість піна в базі
            if 0 < quantity <= pin_quantity:
                cart = carts.get(user_id, {})
                if pin in cart:  # якщо такий пін вже є в кошику
                    cart[pin] += quantity
                else:
                    cart[pin] = quantity

                carts[user_id] = cart
                bot.send_message(message.chat.id, f"Пін(-и) '{pin}' додано в кошик ({quantity} шт.)")
                choosing_pin_menu(message)
            else:
                bot.send_message(message.chat.id, f"На складі не достатньо пінів '{pin}'")
                choosing_pin_menu(message)

    except ValueError:
        if message.text != 'Повернутись назад':
            bot.send_message(message.chat.id, "[Помилка] Введіть коректне число")
        choosing_pin_menu(message)


# Обробник редагування даних після перевірки користувачем
@bot.callback_query_handler(func=lambda call: True)
def handle_callback_query(call):
    if orders_collection.find_one(
            {'_id': ObjectId(str(call.data).split()[1])}):  # для зміни даних замовлення якщо вони не правильні
        object_id = ObjectId(str(call.data).split()[1])
        action = str(call.data).split()[0]

        if action == "edit_address":
            edit_data(call.message, object_id, 'nova_post')
        elif action == "edit_phone":
            edit_data(call.message, object_id, 'phone')
        elif action == "edit_name":
            edit_data(call.message, object_id, 'name')


# Обробка збереження фото оплати
@bot.message_handler(content_types=['photo'])
def photo_handler(message):
    user_id = message.from_user.id
    # Обробка скріншота оплати
    if orders_collection.find_one({'chatID': user_id, 'order_status': None}):
        # Отримання скріншота оплати
        payment_screenshot = message.photo[-1].file_id
        # Збереження скріншота оплати в поточному замовленні
        orders_collection.update_one({'chatID': user_id, 'order_status': None},
                                     {'$set': {'payment_screenshot': payment_screenshot}})

        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
        confirm_btn = types.KeyboardButton('Підтверджую')
        keyboard.add(confirm_btn)
        bot.send_message(user_id, f'Скріншот успішно додано до замовлення.\n'
                                  f'Щоб завершити замовлення - натисніть кнопку.', reply_markup=keyboard)

    # Обробка якщо це фото для розсилки
    if '/spam' in str(message.caption):
        send_spam(message)


# Введення нового значення даних в замовленні
def edit_data(message, order_id, field_name):
    user_id = message.chat.id
    bot.send_message(user_id, "Введіть нове значення:")
    bot.register_next_step_handler(message, lambda msg: update_data(msg, order_id, field_name))


# Оновлення цих даних в базі
def update_data(message, order_id, field_name):
    user_id = message.from_user.id
    new_value = message.text
    orders_collection.update_one({'_id': order_id}, {'$set': {field_name: new_value}})
    bot.send_message(user_id,
                     "Дані оновлено.\n"
                     "Перевірте інші поля, якщо все правильно - відправте скріншот оплати")


@bot.message_handler(func=lambda message: str(message.text).lower() == 'підтверджую')
def finally_confirm_order(message):
    user_id = message.from_user.id
    if orders_collection.find_one({'chatID': user_id, 'order_status': None}) is None:
        bot.send_message(user_id, 'Спочатку введіть свої дані у замовлення.')
    else:
        if orders_collection.find_one({'chatID': user_id, 'order_status': None})['payment_screenshot'] is None:
            bot.send_message(user_id, 'Будь ласка, надішліть скріншот оплати перед підтвердженням замовлення.')
        else:
            date = datetime.now()
            orders_collection.update_one({'chatID': user_id, 'order_status': None},
                                         {'$set': {'order_status': 1, 'date': date,
                                                   'order_price': get_order_price(user_id)}})

            # Отримання скріншота оплати
            payment_screenshot = orders_collection.find_one({'chatID': user_id, 'date': date})['payment_screenshot']

            # Відправлення інформації про замовлення окремій людині разом із скріншотом оплати
            order_info = f"Замовлення від користувача @{message.from_user.username}, id{user_id}:\n\n"
            order_info += f"Адреса нової пошти: {orders_collection.find_one({'chatID': user_id, 'date': date})['nova_post']}\n"
            order_info += f"Номер телефону: {orders_collection.find_one({'chatID': user_id, 'date': date})['phone']}\n"
            order_info += f"Прізвище, ім'я та по батькові: {orders_collection.find_one({'chatID': user_id, 'date': date})['name']}\n"
            order_info += f"До оплати: {get_order_price(user_id)}грн.\n\n"
            order = ''
            for pin, quantity in carts[user_id].items():
                order += f"{pin}: {quantity} шт.\n"

            order_info += order

            # Віднімання кількості пінів з бази
            for pin, quantity in carts[user_id].items():
                pin_data = pins_collection.find_one({'name': pin})
                pin_data['quantity'] -= quantity
                pins_collection.update_one({'_id': pin_data['_id']}, {'$set': {'quantity': pin_data['quantity']}})

            bot.send_message(MANAGER_CHAT_ID, order_info)
            bot.send_photo(MANAGER_CHAT_ID, payment_screenshot)  # Відправка скріншота оплати менеджеру

            bot.send_message(user_id, 'Замовлення успішно підтверджено. Дякуємо, що довіряєте нам!')
            clear_cart(message)
            start(message)


@bot.message_handler(func=lambda message: message.text == 'Підтвердити замовлення')
def confirm_order(message):
    user_id = message.from_user.id
    cart = carts.get(user_id, {})
    if not cart:
        bot.send_message(message.chat.id, "Ваш кошик порожній")
    else:
        # Створення в БД нового замовлення
        order_id = orders_collection.insert_one(
            {'chatID': user_id, 'phone': None, 'name': None, 'nova_post': None,
             'product': cart,
             'order_price': None,
             'payment_screenshot': None,
             'order_status': None,
             'date': None}).inserted_id

        bot.send_message(user_id, "Будь ласка, введіть адресу нової пошти:")
        bot.register_next_step_handler(message, process_post_office, order_id)


def process_post_office(message, order_id):
    user_id = message.from_user.id
    nova_post = message.text

    # Зберегти пошту в поточному замовленні
    orders_collection.update_one({'_id': order_id}, {'$set': {'nova_post': nova_post}})

    bot.send_message(user_id, "Будь ласка, введіть номер телефону:")
    bot.register_next_step_handler(message, process_phone, order_id)


def process_phone(message, order_id):
    user_id = message.from_user.id
    phone = message.text

    # Зберегти номер телефону в поточному замовленні
    orders_collection.update_one({'_id': order_id}, {'$set': {'phone': phone}})

    # Запитати прізвище, ім'я та по батькові
    bot.send_message(user_id, "Будь ласка, введіть ваше прізвище, ім'я та по батькові:")
    bot.register_next_step_handler(message, process_name, order_id)


def process_name(message, order_id):
    user_id = message.from_user.id
    name = message.text

    # Зберегти прізвище, ім'я та по батькові в поточному замовленні
    orders_collection.update_one({'_id': order_id}, {'$set': {'name': name}})

    # Вивести дані користувача для перевірки та редагування
    order_info = f"Перевірте введені дані:\n\n"
    order_info += f"Адреса нової пошти: {orders_collection.find_one({'_id': order_id})['nova_post']}\n"
    order_info += f"Номер телефону: {orders_collection.find_one({'_id': order_id})['phone']}\n"
    order_info += f"Прізвище, ім'я та по батькові: {orders_collection.find_one({'_id': order_id})['name']}\n"

    order_info += f"Всього до оплати: {get_order_price(user_id)}грн.\n\n"

    order_info += (
        "Для підтвердження замовлення потрібно:\n"
        "1. Надіслати скріншот оплати\n"
        "2. Натиснути кнопку 'Підтверджую'\n"
        "\nДані для оплати:\n"
        "Картка 5555 5555 5555 5555\n"
        "\nЯкщо потрібно відредагувати дані, виберіть відповідну кнопку.")

    keyboard = types.InlineKeyboardMarkup()
    edit_address_button = types.InlineKeyboardButton(text="✍️Адреса", callback_data=f"edit_address {order_id}")
    edit_phone_button = types.InlineKeyboardButton(text="✍️Номер телефону",
                                                   callback_data=f"edit_phone {order_id}")
    edit_name_button = types.InlineKeyboardButton(text="✍️ПІБ", callback_data=f"edit_name {order_id}")

    keyboard.add(edit_address_button, edit_phone_button, edit_name_button)
    bot.send_message(user_id, order_info, reply_markup=keyboard, disable_web_page_preview=True)

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    confirm_btn = types.KeyboardButton('Підтверджую')
    markup.add(confirm_btn)
    bot.send_message(user_id, 'Очікуємо скріншот оплати', reply_markup=markup)


# =====================================Manager===========================================================
# команда /help для менеджера
@bot.message_handler(commands=['help'])
def change_pin(message):
    if str(message.chat.id) != MANAGER_CHAT_ID:
        return
    bot.send_message(message.chat.id,
                     f'/change_quantity <Назва піна> <кількість пінів> - змінити кількість пінів в базі\n'
                     f'/change_price <Назва піна> <Нова ціна> - змінити ціну на пін\n'
                     f'/add_pin <Назва піна> <Кількість пінів> <Ціна піна> - додати пін в базу\n'
                     f'/delete_pin <Назва піна> - видалити пін з бази\n'
                     f'/pins_info - інформація по пінам з бази\n'
                     f'/spam <Текст для розсилки> (також можна до тексту додавати фото, але тільки одне)\n'
                     f'/set_status <userID користувача> <номер статусу(0 - звичайний, 1 - волонтер(-ка), 2 - військовий(-ва))>\n'
                     f'/delete_null_orders - видалити всі незавершені замовлення\n'
                     f'/send_message <userID клієнта> <повідомлення> - відправити повідомлення клієнту через бота\n'
                     f'/download_payment <fileID> - получити фотографію оплати по payment_screenshot\n')


# Функція зміни кількості пінів через бота
@bot.message_handler(commands=['change_quantity'])
def change_pin(message):
    try:
        if str(message.chat.id) != MANAGER_CHAT_ID:
            return
        pin = message.text.replace('/change_quantity ', '')
        pin_name = ' '.join(pin.split()[:-1])

        pin_data = pins_collection.find_one({'name': pin_name})

        if pin_data:
            new_pin_value = int(pin.split()[-1])
            pin_data['quantity'] = new_pin_value
            pins_collection.update_one({'_id': pin_data['_id']}, {'$set': {'quantity': new_pin_value}})
            bot.reply_to(message, f"Кількість пінів '{pin_name}' змінено на {new_pin_value}")
        else:
            bot.reply_to(message, f"Пін '{pin_name}' не знайдено")
    except Exception as e:
        bot.reply_to(message, f'Сталася помилка: {e}')


# Функція зміни ціни піна через бота
@bot.message_handler(commands=['change_price'])
def update_price_by_name(message):
    try:
        if str(message.chat.id) != MANAGER_CHAT_ID:
            return
        pin = message.text.replace('/change_price ', '')
        pin_name = ' '.join(pin.split()[:-1])
        pin_data = pins_collection.find_one({'name': pin_name})

        if pin_data:
            new_pin_price = int(pin.split()[-1])
            pin_data['price'] = new_pin_price
            pins_collection.update_one({'_id': pin_data['_id']}, {'$set': {'price': new_pin_price}})
            bot.reply_to(message, f"Ціна піна '{pin_name}' змінена на {new_pin_price}")
        else:
            bot.reply_to(message, f"Пін '{pin_name}' не знайдено")
    except Exception as e:
        bot.reply_to(message, f'Сталася помилка: {e}')


# Функція додавання нового піна в базу, через телеграм бота
@bot.message_handler(commands=['add_pin'])
def add_new_pin(message):
    try:
        if str(message.chat.id) != MANAGER_CHAT_ID:
            return
        try:
            pin = message.text.replace('/add_pin ', '')
            pin_name = ' '.join(pin.split()[:-2])
            pin_quantity = int(pin.split()[-2])
            pin_price = int(pin.split()[-1])
            pin_data = {
                'name': pin_name,
                'quantity': pin_quantity,
                'price': pin_price
            }
            pins_collection.insert_one(pin_data)

            bot.send_message(message.chat.id, f"Пін '{pin_name}' додано до бази даних")
        except ValueError:
            bot.send_message(message.chat.id,
                             "[Помилка] Некоректний формат команди. Використовуйте '/add_pin назва кількість ціна'")
    except Exception as e:
        bot.reply_to(message, f'Сталася помилка: {e}')


# Функція видалення піна з бази, через телеграм бота
@bot.message_handler(commands=['delete_pin'])
def delete_pin(message):
    try:
        if str(message.chat.id) != MANAGER_CHAT_ID:
            return
        pin_name = message.text.replace('/delete_pin ', '')
        pin_data = pins_collection.find_one({'name': pin_name})

        if pin_data:
            pins_collection.delete_one({'_id': pin_data['_id']})
            bot.reply_to(message, f"Пін '{pin_name}' видалено з бази даних")
        else:
            bot.reply_to(message, f"Пін '{pin_name}' не знайдено")
    except Exception as e:
        bot.reply_to(message, f'Сталася помилка: {e}')


# Подивитись інфу про піни
@bot.message_handler(commands=['pins_info'])
def pin_count(message):
    try:
        if str(message.chat.id) != MANAGER_CHAT_ID:
            return
        pins_data = pins_collection.find()
        pins_info = ""
        for pin_data in pins_data:
            pin_name = pin_data['name']
            pin_quantity = pin_data['quantity']
            pin_price = pin_data['price']
            pins_info += f"Назва: {pin_name}\nКількість: {pin_quantity}\nЦіна: {pin_price}\n\n"
        bot.send_message(message.chat.id, pins_info)
    except Exception as e:
        bot.reply_to(message, f'Сталася помилка: {e}')


# Розсилка повідомлень
@bot.message_handler(commands=['spam'])
def send_spam(message):
    try:
        if str(message.chat.id) == MANAGER_CHAT_ID:
            # Отримання всіх користувачів з бази даних
            users = clients_collection.find({})
            try:
                # Якщо для розсилки використовується фото
                if message.photo:
                    photo = message.photo[-1].file_id
                    text = str(message.caption).replace('/spam ', '')
                    for user in users:
                        chat_id = user['chatID']
                        time.sleep(0.5)
                        # Надсилання текстового повідомлення
                        bot.send_photo(chat_id, photo, caption=text)
                else:
                    for user in users:
                        chat_id = user['chatID']
                        time.sleep(0.5)
                        text = str(message.text).replace('/spam ', '')
                        # Надсилання текстового повідомлення
                        bot.send_message(chat_id, text)
            except apihelper.ApiTelegramException as e:
                print(f"[ERROR CODE] {e.error_code}, опис помилки: {e.description}")
    except Exception as e:
        bot.reply_to(message, f'Сталася помилка: {e}')


# Призначення статусу клієнту (волонтер(-ка)/(військовий(-ва)
@bot.message_handler(commands=['set_status'])
def set_status(message):
    if str(message.chat.id) != MANAGER_CHAT_ID:
        return
    try:
        _, user_id, status = message.text.split()
        user_id = int(user_id)  # перетворення user_id у ціле число
        status = int(status)  # перетворення status у ціле число
        clients_collection.update_one({'chatID': user_id}, {"$set": {'status': status}})
        bot.reply_to(message, f"Статус користувача {user_id} оновлено до {status}.")
        bot.send_message(user_id, f'Ваш статус було підтверджено менеджером. Дякуємо що допомагаєте державі!')
    except Exception as e:
        bot.reply_to(message, f"Помилка при оновленні статусу.\n {e}")


@bot.message_handler(commands=['delete_null_orders'])
def delete_null_orders(message):
    if str(message.chat.id) != MANAGER_CHAT_ID:
        return
    orders_collection.delete_many({
        "order_price": None,
        "order_status": None,
        "date": None
    })

    bot.reply_to(message, "Не завершені замовлення видалено")


@bot.message_handler(commands=['send_message'])
def send_message_to_user(message):
    if str(message.chat.id) != MANAGER_CHAT_ID:
        return
    user_id = message.text.split()[1]
    msg = ' '.join(message.text.split()[2:])
    bot.send_message(user_id, msg)
    bot.reply_to(message, "Повідомлення відправлено")


@bot.message_handler(commands=['download_payment'])
def download_photo_by_file_id(message):
    if str(message.chat.id) != MANAGER_CHAT_ID:
        return
    _, file_id = message.text.split()
    # Відправити менеджеру фото оплати
    bot.send_photo(MANAGER_CHAT_ID, file_id)


# запуск бота
bot.polling()
