from TP_config import BOT_SETTINGS, bcolors, DEFAULT_TIMEZONE, MIN_TIME_FOR_BOOKING_BEFORE_EVENT, timezones
from TP_config import DEFAULT_IMG, USERS_START_IMGS_PATH
from TP_bot_msgs import get_translation, format_date, replace_placeholders
from TP_db_functions import get_bot_info_by_id, get_user_info, save_user_info
from TP_db_functions import get_service_settings_by_service_id, get_service_id_by_name, add_new_booking
from TP_db_functions import get_booking_subservices, add_subservice_to_booking, delete_booking_subservice
from TP_db_functions import get_subservice_settings_by_service_id, save_booking, get_keyboard_msg_id
from TP_db_functions import get_user_operation, get_existing_bookings, get_booking_info, delete_booking, get_bot_status
from TP_db_functions import delete_client_data, get_booking_value, set_booking_value, get_user_timezone, get_service_timezone
from TP_db_functions import is_service_subscription_active, set_additional_service_setting, update_client_user_info

from TP_admin import edit_and_delete_messages

from TP_keyboards import create_subservices_selection_keyboard, create_calendary_and_time_keyboard
from TP_keyboards import create_phone_keyboard, create_add_booking_confirmation_keyboard, create_bookings_for_client_keyboard
from TP_keyboards import create_edit_booking_keyboard, create_del_booking_confirmation_keyboard
from TP_keyboards import create_services_selection_keyboard, create_client_main_menu_keyboard, create_client_timezone_setting_keyboard

from telegram import Update, Bot, MessageEntity
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

from telegram.ext import Application, MessageHandler, CallbackQueryHandler, filters, CallbackContext
from telegram.ext import CommandHandler

from telegram.error import Forbidden

from datetime import datetime, timedelta
import pytz
import os

# =======================================================
# ============  Text generation functions ===============
# =======================================================

# генерируем текст с информацией о определенном бронировании пользователя
def get_booking_info_text(language_code, booking_id, user_id, service_id):
    text = f"<b>{get_translation(language_code, 'text_booking_info')}</b>\n\n"

    # информация о сервисе
    service_settings = get_service_settings_by_service_id(service_id, None, 'main_table')
    if service_settings is None:
        return get_translation(language_code, 'err_text_service_not_found')
    print(f"[{user_id}] service_settings >>> ", service_settings)
    text += f"<b>{get_translation(language_code, 'text_where')}:</b> {service_settings['service_workplace_name']}\n"
    text += f"<b>{get_translation(language_code, 'text_master')}</b> {service_settings['service_user_name']} {service_settings['service_user_second_name']}\n"
    text += f"<b>{get_translation(language_code, 'text_address')}:</b> {service_settings['service_workplace_city']}, {service_settings['service_workplace_address']}\n\n"

    # информация о бронировании
    booking = get_booking_info(booking_id, user_id)
    service_timezone = get_service_timezone(service_id)

    print(f"[{user_id}] booking >>> ", booking)
    # Форматирование даты и времени с использованием переводов
    if 'slot_datetime' in booking:
        client_timezone, users_timezone_is_set = get_user_timezone(user_id, 'clients_table')
        slot_datetime = service_timezone.localize(booking['slot_datetime'])
        slot_datetime_in_client_timezone = slot_datetime.astimezone(client_timezone)

        formatted_date = format_date(language_code,  slot_datetime_in_client_timezone)
        text += f"<b>{get_translation(language_code, 'text_time')}:</b> {formatted_date}\n"
    # продолжительность
    if 'total_duration' in booking:
        hours = booking['total_duration'].seconds // 3600
        minutes = (booking['total_duration'].seconds % 3600) // 60
        total_duration = f"{hours} {get_translation(language_code, 'btn_h.ours')} {minutes} {get_translation(language_code, 'btn_m.inutes')}"
        text += f"<b>{get_translation(language_code, 'text_duration')}:</b> {total_duration}\n"
    # стоимость
    if 'total_cost' in booking:
        text += f"<b>{get_translation(language_code, 'text_cost')}:</b> {int(float(booking['total_cost']))}{get_translation(language_code,'btn_currency')}\n"
    # услуги
    text += f"\n<b>{get_translation(language_code, 'text_services')}:</b>\n"
    for subservice in booking['subservices']:
        text += f"{get_translation(language_code, 'text_minus')} {subservice['name']}\n"

    return text

# геренируем текс с датой обновления
def get_data_update_info_text(language_code, user_id, service_id):
    # Получаем текущую дату и время в указанной временной зоне
    timezone, users_timezone_is_set = get_user_timezone(user_id, 'clients_table')
    text = ''
    if not users_timezone_is_set:
        text += f"{get_translation(language_code, 'text_timezone_warning')}\n"

    # Форматируем дату и время в нужный формат
    formatted_date = format_date(language_code, datetime.now(timezone))

    text += f"<i>{get_translation(language_code, 'text_updated')} {formatted_date} ({timezone.zone})</i>"
    return text

# геренируем текст для основного меню с информацией о сервисе и о бронированиях
def get_service_description_text(language_code, user_id, service_id):
    bot_status = get_service_settings_by_service_id(service_id, 'status', 'settings_table')
    if bot_status is not None:
        bot_status = bot_status['value']
    else:
        bot_status = "not_found"

    if bot_status == 'published':
        service_settings = get_service_settings_by_service_id(service_id, None, 'main_table')
        print(f"[{user_id}] service_settings >>> ", service_settings)

        if service_settings:
            text = f"{get_translation(language_code, 'text_booking_to_master')} <b>{service_settings['service_user_name']} {service_settings['service_user_second_name']}</b> " \
                   f"{get_translation(language_code, 'text_booking_to_place')} <b>{service_settings['service_workplace_name']}</b> " \
                   f"{get_translation(language_code, 'text_booking_to_address')} <b>{service_settings['service_workplace_city']}, {service_settings['service_workplace_address']}</b>" 
        else:
            text = get_translation(language_code, 'err_text_service_not_found')

    # если бот не найден или остановлен
    else:
        text = f"<i>{get_translation(language_code, 'text_service_is_stopped')}</i>"

    return text

# геренируем текст с контактами сервиса
def get_service_contacts_text(language_code, user_id, service_id):
    bot_status = get_service_settings_by_service_id(service_id, 'status', 'settings_table')
    if bot_status is not None:
        bot_status = bot_status['value']
    else:
        bot_status = "not_found"

    if bot_status == 'published':
        text = ''

        contact_telegram = get_service_settings_by_service_id(service_id, 'contact_telegram', 'settings_table')

        if contact_telegram is not None:

            text += f"<b>{get_translation(language_code, 'text_telegram_contact')}:</b> @{contact_telegram['value']}"

        contact_instagram = get_service_settings_by_service_id(service_id, 'contact_instagram', 'settings_table')
        if contact_instagram:
            text += f"\n<b>{get_translation(language_code, 'text_instagram_contact')}:</b> {contact_instagram['value']} {get_translation(language_code, 'text_instagram_contact2')}"

        contact_vk = get_service_settings_by_service_id(service_id, 'contact_vk', 'settings_table')
        if contact_vk:
            text += f"\n<b>{get_translation(language_code, 'text_vk_contact')}:</b> {contact_vk['value']}"
    else:
        text = ''
    return text

# геренируем текст со статистикой пользователя
def get_user_bookings_info_text(language_code, user_id, service_id):
    existing_user_bookings = get_existing_bookings(service_id, None, None, None, user_id)
    existing_user_bookings = [booking for booking in existing_user_bookings if 'slot_datetime' in booking]

    if len(existing_user_bookings) == 0:
        return f"{get_translation(language_code, 'text_push_the_button')}\n"
    else:
        # Текущее время
        service_timezone = get_service_timezone(service_id)
        now = datetime.now()

        now_in_service_timezone = now.astimezone(service_timezone)
        now_in_service_timezone_naive = now_in_service_timezone.replace(tzinfo=None)

        # Отфильтровать события, у которых slot_datetime больше текущего времени
        future_bookings = [booking for booking in existing_user_bookings if
                           'slot_datetime' in booking and booking['slot_datetime'] > now_in_service_timezone_naive]

        # Найти ближайшее предстоящее событие
        if future_bookings:
            nearest_booking = min(future_bookings, key=lambda x: x['slot_datetime'])
            text = f"{get_translation(language_code, 'text_nearest_booking')}:\n"
            # информация о бронировании
            booking = get_booking_info(nearest_booking['booking_id'], user_id)
            print(f"[{user_id}] booking >>> ", booking)
            # Форматирование даты и времени с использованием переводов
            if 'slot_datetime' in booking:
                client_timezone, users_timezone_is_set = get_user_timezone(user_id, 'clients_table')
                slot_datetime = service_timezone.localize(booking['slot_datetime'])
                slot_datetime_in_client_timezone = slot_datetime.astimezone(client_timezone)

                formatted_date = format_date(language_code, slot_datetime_in_client_timezone)
                text += f"<b>{get_translation(language_code, 'text_time')}:</b> {formatted_date}\n"
            # продолжительность
            if 'total_duration' in booking:
                hours = booking['total_duration'].seconds // 3600
                minutes = (booking['total_duration'].seconds % 3600) // 60
                total_duration = f"{hours} {get_translation(language_code, 'btn_h.ours')} {minutes} {get_translation(language_code, 'btn_m.inutes')}"
                text += f"<b>{get_translation(language_code, 'text_duration')}:</b> {total_duration}\n"
            # стоимость
            if 'total_cost' in booking:
                text += f"<b>{get_translation(language_code, 'text_cost')}:</b> {int(float(booking['total_cost']))}{get_translation(language_code, 'btn_currency')}\n"
            # услуги
            text += f"\n<b>{get_translation(language_code, 'text_services')}:</b>\n"
            for subservice in booking['subservices']:
                text += f"{get_translation(language_code, 'text_minus')} {subservice['name']}\n"
            return text
        else:
            return f"{get_translation(language_code, 'text_push_the_button')}\n"

# =======================================================
# ===============  Support  functions ===================
# =======================================================

def get_service_start_image(service_admin_id):
    # Формируем путь к изображению пользователя
    if service_admin_id is None:
        return os.path.join(os.path.dirname(__file__), 'img', DEFAULT_IMG)

    user_image_path = os.path.join(USERS_START_IMGS_PATH, f'{service_admin_id}.jpg')

    # Проверяем, существует ли изображение пользователя
    if os.path.exists(user_image_path):
        image_path = user_image_path
    else:
        # Если изображение пользователя не найдено, используем изображение по умолчанию
        image_path = os.path.join(os.path.dirname(__file__), 'img', DEFAULT_IMG)
    return image_path


# =======================================================
# ==============  Telegram Functions ====================
# =======================================================


# Обработчик команды /start 
async def start(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    language_code = user.language_code
    user_id = user.id
    print(f'[{user_id}] {bcolors.OKCYAN}start{bcolors.ENDC}')
    context.user_data.clear()
    phone_number = update.message.contact.phone_number if update.message.contact else None

    # Получаем текущую информацию о пользователе из базы данных
    current_user_info = get_user_info(user.id, 'clients_table')

    # Сохраняем или обновляем информацию о пользователе
    if current_user_info == -1:
        save_user_info(user_id, user.first_name, user.last_name, user.username,
                       phone_number, user.is_bot, language_code, user.is_premium, table='clients_table')
        current_user_info = get_user_info(user.id, 'clients_table')
    else:
        # Проверяем, что изменилось
        changes = []
        if current_user_info:
            if current_user_info['first_name'] != user.first_name:
                changes.append(f"First name changed from {current_user_info['first_name']} to {user.first_name}")
            if current_user_info['last_name'] != user.last_name:
                changes.append(f"Last name changed from {current_user_info['last_name']} to {user.last_name}")
            if current_user_info['username'] != user.username:
                changes.append(f"Username changed from {current_user_info['username']} to {user.username}")
            if current_user_info['language_code'] != language_code:
                changes.append(f"Language code changed from {current_user_info['language_code']} to {language_code}")
            if current_user_info['is_premium'] != user.is_premium:
                changes.append(f"Premium status changed from {current_user_info['is_premium']} to {user.is_premium}")

        # Уведомлениe об изменениях
        if changes:
            changes_message = f"User {user_id} restarts bot and I'v detected changes:\n" + "\n".join(changes)
            print(f'[{user_id}] {bcolors.WARNING}Changes were made:{bcolors.ENDC}\n{changes_message}')

    service_id = None
    image_path = get_service_start_image(None)
    start_param = context.args[0] if context.args else None
    if start_param:
        # если в ссылке зашит сервис
        print(f'[{user_id}] {bcolors.UNDERLINE}start_param: {bcolors.ENDC}{start_param}')
        service_id = get_service_id_by_name(start_param)
        if service_id is None:
            keyboard = create_services_selection_keyboard(language_code, 0)
            await update.message.reply_text(get_translation(language_code, "err_no_service"), parse_mode='HTML', reply_markup=keyboard)
    else:
        # Сервис не зашит в ссылке.
        # Даем возможность выбрать предыдущий сервис, если он был выбран ранее или меню с сервисами.
        if current_user_info['service_id'] is not None:
            last_selected_service_id = current_user_info['service_id']
            service_settings = get_service_settings_by_service_id(last_selected_service_id)
            if service_settings is not None:
                text = service_settings['service_name']
                keyboard = [
                    [InlineKeyboardButton(text, callback_data=f"s_{last_selected_service_id}_select")],
                    [InlineKeyboardButton(f"{get_translation(language_code, 'btn_select_service')}", callback_data=f"services_showList")]
                ]
                text = get_translation(language_code, "text_start_msg_client")
                if is_service_subscription_active(service_id=last_selected_service_id):
                    service_admin_id = service_settings['user_id']
                    image_path = get_service_start_image(service_admin_id)
                with open(image_path, 'rb') as photo:
                    await context.bot.send_photo(chat_id=user_id, photo=photo, parse_mode='HTML', caption=text)

                text = get_translation(language_code, "text_please_select_service")
                msg = await update.message.reply_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
                update_client_user_info(user_id, **{'operation': f'return_menu', 'kbd_msg_id': msg.message_id})
            # что-то случилось и сервис видимо удалили
            else:
                update_client_user_info(user_id, **{'service_id': None})
                text = get_translation(language_code, "text_start_msg_client")

                with open(image_path, 'rb') as photo:
                    await context.bot.send_photo(chat_id=user_id, photo=photo, parse_mode='HTML', caption=text)
                text = get_translation(language_code, "text_please_select_service")
                keyboard = create_services_selection_keyboard(language_code, 0)
                msg = await context.bot.send_message(text=text, chat_id=user_id, parse_mode='HTML',
                                                     reply_markup=keyboard)
                update_client_user_info(user_id, **{'operation': f'return_menu', 'kbd_msg_id': msg.message_id})

        # Нет предыдущего выбранного сервиса. Показываем клавиатуру выбора сервиса.
        else:
            text = get_translation(language_code, "text_start_msg_client")

            with open(image_path, 'rb') as photo:
                await context.bot.send_photo(chat_id=user_id, photo=photo, parse_mode='HTML', caption=text)
            text = get_translation(language_code, "text_please_select_service")
            keyboard = create_services_selection_keyboard(language_code, 0)
            msg = await context.bot.send_message(text=text, chat_id=user_id, parse_mode='HTML', reply_markup=keyboard)
            update_client_user_info(user_id, **{'operation': f'return_menu', 'kbd_msg_id': msg.message_id})
            # await update.message.reply_text(get_translation(language_code, "err_need_start_param"))

    if service_id is not None:
        # Проверяем, доступен ли сервис для записи
        bot_status = get_bot_status(None, service_id)
        # Сервис недоступен
        if bot_status != 'published':
            text = f"<i>{get_translation(language_code, 'text_service_is_stopped')}</i>"
            await update.message.reply_text(text, parse_mode='HTML')
        # Сервис доступен
        else:
            text = get_service_description_text(language_code, user_id, service_id)
            text += f'\n\n{get_service_contacts_text(language_code, user_id, service_id)}'
            keyboard = create_client_main_menu_keyboard(language_code, user_id, service_id)

            # Отправляем сообщение с картинкой и кнопками
            if is_service_subscription_active(service_id=service_id):
                service_settings = get_service_settings_by_service_id(service_id)
                service_admin_id = service_settings['user_id']
                image_path = get_service_start_image(service_admin_id)
            with open(image_path, 'rb') as photo:
                msg = await context.bot.send_photo(chat_id=user_id, photo=photo, parse_mode='HTML', caption=text)
            text += f"\n\n{get_user_bookings_info_text(language_code, user_id, service_id)}"
            text += f"\n{get_data_update_info_text(language_code, user_id, service_id)}"
            msg = await update.message.reply_text(text, parse_mode='HTML', reply_markup=keyboard)

            update_client_user_info(user_id, **{'operation': f'return_menu', 'kbd_msg_id': msg.message_id})
            if current_user_info['service_id'] == -1:
                update_client_user_info(user_id, **{'service_id': service_id})
            elif current_user_info['service_id'] != service_id:
                save_user_info(user_id, user.first_name, user.last_name, user.username,
                               phone_number, user.is_bot, language_code, user.is_premium, service_id, table='clients_table')

# Обработчик контакта
async def handle_phone_number(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id = update.effective_chat.id
    language_code = user.language_code
    phone_number = update.message.contact.phone_number if update.message.contact else None
    kbd_message_id = get_keyboard_msg_id(user_id, table='clients_table')
    message_id = update.message.message_id
    messages_to_delete = context.user_data.get('messages_to_delete', [])
    messages_to_delete.append(message_id)
    context.user_data['messages_to_delete'] = messages_to_delete

    if phone_number:

        update_client_user_info(user_id, **{'phone_number': phone_number})
        operation = get_user_operation(user_id, table='clients_table')
        _, service_id, _, booking_id, _, year, month, day, time = operation.split('_')
        text = get_booking_info_text(language_code, booking_id, user_id, service_id)

        booking = get_booking_info(booking_id, user_id)
        if not 'slot_datetime' in booking:
            slot_datetime = datetime.strptime(f"{year}-{month}-{day} {time}", "%Y-%m-%d %H:%M")
            text += f"\n<b>{get_translation(language_code, 'text_booking_date_time')}:</b> {format_date(language_code, slot_datetime)}"

        text += f"\n\n{get_translation(language_code, 'text_phone_have_been_added')}"

        keyboard = create_add_booking_confirmation_keyboard(language_code, user_id, booking_id, service_id, year, month, day, time)
        await edit_and_delete_messages(update, context, kbd_message_id, text, keyboard)
        update_client_user_info(user_id, **{'operation': f'return_menu'})
    else:
        msg = await update.message.reply_text('Cancel')
        messages_to_delete.append(msg.message_id)
        context.user_data['messages_to_delete'] = messages_to_delete

# Обработчик текстовых сообщений
async def handle_text_message(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_chat.id
    print(f'[{user_id}] {bcolors.OKCYAN}handle_text_message{bcolors.ENDC}')
    language_code = update.effective_user.language_code
    text = update.message.text
    print(f'[{user_id}] {bcolors.UNDERLINE}text{bcolors.ENDC} = {bcolors.OKCYAN}{text}{bcolors.ENDC}')
    message_id = update.message.message_id
    messages_to_delete = context.user_data.get('messages_to_delete', [])
    messages_to_delete.append(message_id)

    if text == 'delete my info':
        delete_client_data(user_id)
        print(f'[{user_id}] {bcolors.OKGREEN}Client data was deleted{bcolors.ENDC}')

# Обработчик нажатий на кнопки
async def handle_callback_query(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    language_code = update.effective_user.language_code
    await query.answer()
    user_id = query.from_user.id
    print(f'[{user_id}] {bcolors.OKCYAN}handle_callback_query{bcolors.ENDC} {format_date(language_code, datetime.now())}')
    message_id = query.message.message_id
    kbd_message_id = get_keyboard_msg_id(user_id, table='clients_table')
    messages_to_delete = context.user_data.get('messages_to_delete', [])
    data = query.data
    data = data.split('_')

    print(f'[{user_id}] {bcolors.UNDERLINE}data{bcolors.ENDC} = {bcolors.OKCYAN}{data}{bcolors.ENDC}')

    # рабоатем с выбранным сервисом
    if data[0] == 's':
        service_id = int(data[1])

        # проверяем, существует ли сервис и опубликован ли он
        bot_status = get_bot_status(None, service_id)
        if bot_status != 'published':
        # сервис недоступен
            text = f"<i>{get_translation(language_code, 'text_service_is_stopped')}</i>\n\n"
            text += get_translation(language_code, "text_please_select_service_or_wait")
            keyboard = create_services_selection_keyboard(language_code, 0)
            msg = await update.callback_query.edit_message_text(text, parse_mode='HTML', reply_markup=keyboard)
        else:
            # сервис доступен
            if data[2] == 'booking':
                # добавляем запись
                if data[3] == 'add':
                    booking_id = add_new_booking(user_id, service_id)
                    text = f"{get_booking_info_text(language_code, booking_id, user_id, service_id)}\n{get_translation(language_code,'text_select_subservices')}"
                    await update.callback_query.edit_message_text(
                        text,
                        parse_mode='HTML',
                        reply_markup=create_subservices_selection_keyboard(language_code, user_id, booking_id, service_id)
                    )

                # показываем бронирования
                elif data[3] == 'show':
                    text = get_service_description_text(language_code, user_id, service_id)
                    existing_bookings = get_existing_bookings(service_id, None, None, None, user_id)

                    client_timezone, users_timezone_is_set = get_user_timezone(user_id, 'clients_table')
                    service_timezone = get_service_timezone(service_id)
                    now = datetime.now()

                    now_in_service_timezone = now.astimezone(service_timezone)
                    now_in_service_timezone_naive = now_in_service_timezone.replace(tzinfo=None)

                    # Отфильтровать события, у которых slot_datetime больше текущего времени
                    future_bookings = [booking for booking in existing_bookings if
                                       'slot_datetime' in booking and booking['slot_datetime'] > now_in_service_timezone_naive]

                    if not future_bookings:
                        text += f"\n\n{get_translation(language_code, 'text_no_nearest_bookings')}"
                    text += f"\n\n{get_user_bookings_info_text(language_code, user_id, service_id)}"
                    text += f"\n{get_data_update_info_text(language_code, user_id, service_id)}"

                    await update.callback_query.edit_message_text(
                        text, parse_mode='HTML',
                        reply_markup=create_bookings_for_client_keyboard(language_code, future_bookings, user_id, service_id)
                    )
                    update_client_user_info(user_id, **{'operation': f'return_bookings', 'kbd_msg_id': message_id})
                    
            elif data[2] == 'b':
                booking_id = int(data[3])

                # шаг первый - добавляем услуги
                if data[4] == 'subservice':
                    print(f'[{user_id}] {bcolors.BOLD}Subservice.{bcolors.ENDC}')
                    subservice_id = int(data[5])
                    # добавляем запись
                    if data[6] == 'add':
                        subservice_settings = get_subservice_settings_by_service_id(service_id, subservice_id)

                        add_subservice_to_booking(user_id, booking_id, service_id, subservice_id,
                                                  subservice_settings['service_name'],
                                                  subservice_settings['service_duration'],
                                                  subservice_settings['service_cost'],
                                                  1)

                        text = f"{get_booking_info_text(language_code, booking_id, user_id, service_id)}"
                        await update.callback_query.edit_message_text(
                            text,
                            parse_mode='HTML',
                            reply_markup=create_subservices_selection_keyboard(language_code, user_id, booking_id, service_id)
                        ) 
                        
                    if data[6] == 'del':
                        delete_booking_subservice(user_id, booking_id, subservice_id)
                        text = f"{get_booking_info_text(language_code, booking_id, user_id, service_id)}"
                        await update.callback_query.edit_message_text(
                            text,
                            parse_mode='HTML',
                            reply_markup=create_subservices_selection_keyboard(language_code, user_id, booking_id, service_id)
                        )
                       
                # _______________________________________________________________
                # шаг второй, третий итд - выбираем дату, время и затем сохраняем
                # ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                if data[4] == 'calendary':
                    print(f'[{user_id}] {bcolors.BOLD}Calendary.{bcolors.ENDC}')
                    day = None
                    err_msg = None
                    # выбрали только месяц
                    if len(data) == 5:
                        current_date = datetime.now()
                        year = current_date.year
                        month = current_date.month
                    # если листаем месяц
                    if len(data) >= 7:
                        year = int(data[5])
                        month = int(data[6])
                    # выбрали дату
                    if len(data) >= 8:
                        day = int(data[7])

                        client_timezone, users_timezone_is_set = get_user_timezone(user_id, 'clients_table')
                        # если часовой пояс не задан
                        if not users_timezone_is_set:
                            service_settings = get_service_settings_by_service_id(service_id, None, 'main_table')
                            service_timezone = service_settings['service_timezone']

                            err_msg = get_translation(language_code, "text_timezone_calendary_warning")
                            err_msg = replace_placeholders(err_msg, service_timezone)

                    # выбрали слот времени - пробуем записать
                    if len(data) == 9:
                        slot_time = data[8]

                        # проверяем, есть ли у нас телефон пользователя
                        user_info = get_user_info(user_id, 'clients_table')
                        print(f"[{user_id}] user_info >>> ", user_info)
                        if user_info['phone_number'] is None:
                        # запрашиваем если нет
                            update_client_user_info(user_id, **{'operation': f's_{service_id}_b_{booking_id}_calendary_{year}_{month}_{day}_{slot_time}', 'kbd_msg_id': message_id})

                            msg = await context.bot.send_message(chat_id=user_id, parse_mode='HTML',
                                                                     text=get_translation(language_code, 'text_need_phone_number'),
                                                                     reply_markup=create_phone_keyboard(language_code,
                                                                                                        'hint_phone'))
                            messages_to_delete.append(msg.message_id)
                        # если есть то добавляем бронирование
                        else:
                            slot_datetime = datetime.strptime(f"{year}-{month}-{day} {slot_time}", "%Y-%m-%d %H:%M")
                            # проверяем что время еще не прошло
                            current_timezone = datetime.now(pytz.utc).astimezone().tzinfo
                            now = datetime.now(current_timezone)

                            client_timezone, users_timezone_is_set = get_user_timezone(user_id, 'clients_table')

                            slot_datetime_client_tz = client_timezone.localize(slot_datetime)
                            slot_datetime_current_tz = slot_datetime_client_tz.astimezone(current_timezone)

                            # время уже прошло
                            if now > slot_datetime_current_tz:
                                text = f"{get_translation(language_code, 'text_time_has_passed')}\n\n"
                                text += f"{get_booking_info_text(language_code, booking_id, user_id, service_id)}"

                                keyboard = create_calendary_and_time_keyboard(language_code, user_id, booking_id,
                                                                              service_id, year, month, day)
                                await edit_and_delete_messages(update, context, message_id, text, keyboard)
                                # отправим еще раз сообщение об ошибке
                                err_msg = get_translation(language_code, "text_time_has_passed")
                                msg = await context.bot.send_message(chat_id=user_id, text=err_msg)
                                messages_to_delete.append(msg.message_id)
                            # Вычисление времени, которое должно быть минимум за MIN_TIME_FOR_BOOKING_BEFORE_EVENT минут до slot_datetime
                            else:
                                min_time_before_event = slot_datetime_current_tz - timedelta(minutes=MIN_TIME_FOR_BOOKING_BEFORE_EVENT)

                            # до события осталось мало времени
                                if now >= min_time_before_event:
                                    text = f"{get_translation(language_code, 'text_time_lag_has_passed')}\n\n"
                                    text = replace_placeholders(text, MIN_TIME_FOR_BOOKING_BEFORE_EVENT)
                                    text += f"{get_booking_info_text(language_code, booking_id, user_id, service_id)}"

                                    keyboard = create_calendary_and_time_keyboard(language_code, user_id, booking_id,
                                                                                  service_id, year, month, day)
                                    await edit_and_delete_messages(update, context, message_id, text, keyboard)
                                    # отправим еще раз сообщение об ошибке
                                    err_msg = get_translation(language_code, "text_time_lag_has_passed")
                                    err_msg = replace_placeholders(err_msg, MIN_TIME_FOR_BOOKING_BEFORE_EVENT)
                                    msg = await context.bot.send_message(chat_id=user_id, text=err_msg)
                                    messages_to_delete.append(msg.message_id)
                            # все норм, отправляем запрос на сохранение
                                else:

                                    keyboard = create_add_booking_confirmation_keyboard(language_code, user_id, booking_id,
                                                                                        service_id, year, month, day, slot_time)
                                    text = get_translation(language_code, 'text_booking_adding_confirmation')
                                    text += f"\n\n{get_booking_info_text(language_code, booking_id, user_id, service_id)}"

                                    # добавляем время записи потому что оно еще не сохраниось в БД
                                    booking = get_booking_info(booking_id, user_id)
                                    if not 'slot_datetime' in booking:
                                        text += f"\n<b>{get_translation(language_code, 'text_booking_date_time')}:</b> {format_date(language_code, slot_datetime)}"

                                    await update.callback_query.edit_message_text(
                                        text,
                                        parse_mode='HTML',
                                        reply_markup=keyboard
                                    )
                    # подтверждение получено, сохраняем бронирование
                    elif len(data) == 10:
                        slot_time = data[8]
                        action = data[9]
                        if action == 'save':

                            slot_datetime = datetime.strptime(f"{year}-{month}-{day} {slot_time}", "%Y-%m-%d %H:%M")
                            # проверяем что время еще не прошло
                            current_timezone = datetime.now(pytz.utc).astimezone().tzinfo
                            now = datetime.now(current_timezone)

                            client_timezone, users_timezone_is_set = get_user_timezone(user_id, 'clients_table')

                            slot_datetime_client_tz = client_timezone.localize(slot_datetime)
                            slot_datetime_current_tz = slot_datetime_client_tz.astimezone(current_timezone)

                            # время уже прошло
                            if now > slot_datetime_current_tz:
                                text = f"{get_translation(language_code, 'text_time_has_passed')}\n\n"
                                text += f"{get_booking_info_text(language_code, booking_id, user_id, service_id)}"

                                keyboard = create_calendary_and_time_keyboard(language_code, user_id, booking_id,
                                                                              service_id, year, month, day)
                                await edit_and_delete_messages(update, context, message_id, text, keyboard)
                                # отправим еще раз сообщение об ошибке
                                err_msg = get_translation(language_code, "text_time_has_passed")
                                msg = await context.bot.send_message(chat_id=user_id, text=err_msg)
                                messages_to_delete.append(msg.message_id)
                            # Вычисление времени, которое должно быть минимум за MIN_TIME_FOR_BOOKING_BEFORE_EVENT минут до slot_datetime
                            else:
                                min_time_before_event = slot_datetime_current_tz - timedelta(minutes=MIN_TIME_FOR_BOOKING_BEFORE_EVENT)

                            # до события осталось мало времени
                                if now >= min_time_before_event:
                                    text = f"{get_translation(language_code, 'text_time_lag_has_passed')}\n\n"
                                    text = replace_placeholders(text, MIN_TIME_FOR_BOOKING_BEFORE_EVENT)
                                    text += f"{get_booking_info_text(language_code, booking_id, user_id, service_id)}"

                                    keyboard = create_calendary_and_time_keyboard(language_code, user_id, booking_id,
                                                                                  service_id, year, month, day)
                                    await edit_and_delete_messages(update, context, message_id, text, keyboard)
                                    # отправим еще раз сообщение об ошибке
                                    err_msg = get_translation(language_code, "text_time_lag_has_passed")
                                    err_msg = replace_placeholders(err_msg, MIN_TIME_FOR_BOOKING_BEFORE_EVENT)
                                    msg = await context.bot.send_message(chat_id=user_id, text=err_msg)
                                    messages_to_delete.append(msg.message_id)
                            # все норм, сохраняем
                                else:
                                    save_booking(user_id, booking_id, service_id, slot_datetime)
                                    r = await send_message_to_service_admin(user_id, booking_id, service_id, "text_client_have_added_booking")

                                    if r == 'blocked':
                                        text = get_translation(language_code, 'err_service_is_stopped')
                                    else:
                                        text = get_translation(language_code, 'text_booking_have_been_added')
                                        text += f"\n\n{get_booking_info_text(language_code, booking_id, user_id, service_id)}"

                                    keyboard = InlineKeyboardMarkup([
                                        [InlineKeyboardButton(f"{get_translation(language_code, 'btn_main_menu')}",
                                                              callback_data=f"s_{service_id}_menu")]
                                    ])
                                    
                                    await edit_and_delete_messages(update, context, message_id, text, keyboard)
                    # если нужно показать только календарь, а также итоговое отображение календаря со всеми вышеперечисленными настройками
                    else:
                        text = f"{get_booking_info_text(language_code, booking_id, user_id, service_id)}"

                        keyboard = create_calendary_and_time_keyboard(language_code, user_id, booking_id, service_id, year, month, day)
                        await edit_and_delete_messages(update, context, message_id, text, keyboard)
                        # если были ошибки, отправляем
                        if err_msg:
                            msg = await context.bot.send_message(chat_id=user_id, text=err_msg)
                            messages_to_delete.append(msg.message_id)
                        
                # информаци о бронировании и управление бронированием
                if data[4] == 'edit':
                    existing_bookings = get_existing_bookings(service_id, None, None, None, user_id)
                    booking = None
                    for b in existing_bookings:
                        if b['booking_id'] == booking_id:
                            booking = b
                            break
                    if booking:
                        text = get_booking_info_text(language_code, booking_id, user_id, service_id)
                        await update.callback_query.edit_message_text(
                            text,
                            parse_mode='HTML',
                            reply_markup=create_edit_booking_keyboard(language_code, user_id, booking_id, service_id)
                        )
                    else:
                        err_msg = get_translation(language_code, "err_booking_not_found")
                        msg = await context.bot.send_message(chat_id=user_id, text=err_msg)
                        messages_to_delete.append(msg.message_id)
                # добавление и удаление сабсервисов во время шага 1
                if data[4] == 'step1':
                    text = f"{get_booking_info_text(language_code, booking_id, user_id, service_id)}"
                    await update.callback_query.edit_message_text(
                        text,
                        parse_mode='HTML',
                        reply_markup=create_subservices_selection_keyboard(language_code, user_id, booking_id, service_id)
                    )
                     
                # удаление бронирования
                if data[4] == 'del':
                    existing_bookings = get_existing_bookings(service_id, None, None, None, user_id, show_only_finished = False)
                    print(f"[{user_id}] existing_bookings >>> ", existing_bookings)
                    booking = None
                    for b in existing_bookings:
                        if b['booking_id'] == booking_id:
                            booking = b
                            break
                    if booking:
                        if len(data) == 6 and data[5] == 'confirm':
                            operation = get_user_operation(user_id, table='clients_table')
                            print(f'[{user_id}] {bcolors.UNDERLINE}operation{bcolors.ENDC} = {operation}')

                            if operation:
                                operation = operation.split('_')
                            # возвращаемся в главное меню
                            if len(operation) >= 2 and operation[1] == 'menu':
                                # удалим бронирование
                                delete_booking(user_id, booking_id)

                                text = get_service_description_text(language_code, user_id, service_id)
                                text += f'\n\n{get_service_contacts_text(language_code, user_id, service_id)}'
                                text += f"\n\n{get_user_bookings_info_text(language_code, user_id, service_id)}"
                                text += f"\n{get_data_update_info_text(language_code, user_id, service_id)}"

                                keyboard = create_client_main_menu_keyboard(language_code, user_id, service_id)
                                msg = await update.callback_query.edit_message_text(text, parse_mode='HTML',
                                                                                    reply_markup=keyboard)

                                update_client_user_info(user_id, **{'operation': f'return_menu', 'kbd_msg_id': msg.message_id})
                            # возвращаемся в меню со списком бронирований
                            else:
                                # сначала отправим сообщение админу потому-что инфу берем из БД
                                await send_message_to_service_admin(user_id, booking_id, service_id,
                                                                    'text_client_have_deleted_booking')
                                # затем удалим бронирование
                                delete_booking(user_id, booking_id)

                                text = f"{get_translation(language_code, 'text_booking_was_deleted')}\n"
                                existing_bookings = get_existing_bookings(service_id, None, None, None, user_id)

                                now = datetime.now()
                                service_timezone = get_service_timezone(service_id)
                                now_in_service_timezone = now.astimezone(service_timezone)
                                now_in_service_timezone_naive = now_in_service_timezone.replace(tzinfo=None)
                                # Отфильтровать события, у которых slot_datetime больше текущего времени
                                future_bookings = [booking for booking in existing_bookings if
                                                   'slot_datetime' in booking and booking['slot_datetime'] > now_in_service_timezone_naive]

                                if not future_bookings:
                                    text += f"\n{get_translation(language_code, 'text_no_nearest_bookings')}\n"

                                text += get_user_bookings_info_text(language_code, user_id, service_id)
                                await update.callback_query.edit_message_text(
                                    text,
                                    parse_mode='HTML',
                                    reply_markup=create_bookings_for_client_keyboard(language_code, future_bookings, user_id,
                                                                                     service_id)
                                )
                                 
                        else:
                            text = get_booking_info_text(language_code, booking_id, user_id, service_id)
                            text += f"\n{get_translation(language_code, 'text_booking_deletion_confirm')}"
                            await update.callback_query.edit_message_text(
                                text,
                                parse_mode='HTML',
                                reply_markup=create_del_booking_confirmation_keyboard(language_code, user_id, booking_id, service_id)
                            )
                    else:
                        err_msg = get_translation(language_code, "err_booking_not_found")
                        msg = await context.bot.send_message(chat_id=user_id, text=err_msg)
                        messages_to_delete.append(msg.message_id)
                # подтверждение визита
                if data[4] == 'reminder':
                    answer = data[5]
                    if answer == 'confirm':
                        try:
                            await context.bot.delete_message(chat_id=user_id, message_id=kbd_message_id)
                        except Exception as e:
                            print(f"Ошибка при удалении сообщения с message_id {kbd_message_id}: {e}")

                        # достаем данные по сервису
                        service_settings = get_service_settings_by_service_id(service_id, None, 'main_table')
                        if service_settings is None:
                            return get_translation(language_code, 'err_text_service_not_found')
                        address = f"{service_settings['service_workplace_city']}, {service_settings['service_workplace_address']}"

                        text = get_translation(language_code, 'text_reminder')
                        slot_str = get_booking_value(booking_id, user_id, 'slot_datetime')
                        slot_datetime = datetime.strptime(slot_str, "%Y-%m-%d %H:%M:%S")
                        text = replace_placeholders(text, format_date(language_code, slot_datetime), address)

                        try:
                            await update.callback_query.edit_message_text(
                            text=text, parse_mode='HTML',
                            reply_markup=create_client_main_menu_keyboard(language_code, user_id, service_id)
                        )
                        except Exception as e:
                            print(f"Ошибка при редактировании сообщения: {e}")

                        now = datetime.now()
                        # Проверяем, является ли slot_datetime сегодняшним или вчерашним днем
                        if now.date() == slot_datetime.date():
                            text = get_translation(language_code, 'text_reminder_thanks_reply_today')
                        else:
                            text = get_translation(language_code, 'text_reminder_thanks_reply_tomorrow')

                        msg = await context.bot.send_message(chat_id=user_id, parse_mode='HTML',
                                                             text=text)

                        messages_to_delete.append(msg.message_id)
                        set_booking_value(booking_id, user_id, 'reminder', 'confirmed')
                        # сообщение админу
                        await send_message_to_service_admin(user_id, booking_id, service_id,
                                                            'text_client_have_confirmed_booking')

                    elif answer == 'reject':
                        try:
                            await context.bot.delete_message(chat_id=user_id, message_id=kbd_message_id)
                        except Exception as e:
                            print(f"Ошибка при удалении сообщения с message_id {kbd_message_id}: {e}")

                        text = get_translation(language_code, 'text_reminder_sorry_reply')

                        try:
                            await update.callback_query.edit_message_text(
                                text=text, parse_mode='HTML',
                                reply_markup=create_client_main_menu_keyboard(language_code, user_id, service_id)
                            )
                        except Exception as e:
                            print(f"Ошибка при редактировании сообщения: {e}")

                        set_booking_value(booking_id, user_id, 'reminder', 'rejected')

                        # сообщение админу
                        await send_message_to_service_admin(user_id, booking_id, service_id,
                                                            'text_client_have_rejected_booking')


            elif data[2] == 'menu' or data[2] == 'select':
                # если была задействована клавиатура выбора сервиса - то сохраняем выбор сервиса
                if data[2] == 'select':
                    update_client_user_info(user_id, **{'service_id': service_id})
                text = get_service_description_text(language_code, user_id, service_id)
                text += f'\n\n{get_service_contacts_text(language_code, user_id, service_id)}'
                text += f"\n\n{get_user_bookings_info_text(language_code, user_id, service_id)}"
                text += f"\n{get_data_update_info_text(language_code, user_id, service_id)}"

                keyboard = create_client_main_menu_keyboard(language_code, user_id, service_id)
                msg = await update.callback_query.edit_message_text(text, parse_mode='HTML', reply_markup=keyboard)

                update_client_user_info(user_id, **{'operation': f'return_menu', 'kbd_msg_id': msg.message_id})
    # ошибки и предупреждения
    elif data[0] == 'warning':
        warning = data[1]
        if warning == 'noSubservices':
            err_msg = get_translation(language_code, "err_need_subservice_to_add")
            msg = await context.bot.send_message(chat_id=user_id, text=err_msg)
            messages_to_delete.append(msg.message_id)
        # день уже прошел
        elif warning == 'dayHasPassed':
            err_msg = get_translation(language_code, "err_day_has_passed")
            msg = await context.bot.send_message(chat_id=user_id, text=err_msg)
            messages_to_delete.append(msg.message_id)
        # в это день нет записи
        elif warning == 'noBookingAllowed':
            err_msg = get_translation(language_code, "err_no_booking_this_day")
            msg = await context.bot.send_message(chat_id=user_id, text=err_msg)
            messages_to_delete.append(msg.message_id)
        # время уже прошло
        elif warning == 'timeHasPassed':
            err_msg = get_translation(language_code, "err_time_has_passed")
            msg = await context.bot.send_message(chat_id=user_id, text=err_msg)
            messages_to_delete.append(msg.message_id)
    # работаем с меню сервисов
    elif data[0] == 'services':
        # показываем список сервисов
        if data[1] == 'showList':
            current_user_info = get_user_info(user_id, 'clients_table')
            last_selected_service_id = current_user_info['service_id']
            text = get_translation(language_code, "text_please_select_service")
            keyboard = create_services_selection_keyboard(language_code, 0, last_selected_service_id)
            msg = await update.callback_query.edit_message_text(text=text, parse_mode='HTML', reply_markup=keyboard)
            update_client_user_info(user_id, **{'kbd_msg_id': msg.message_id})

        # листаем клавиатуру выбора сервиса
        else:
            start = int(data[1])
            keyboard = create_services_selection_keyboard(language_code, start)
            text = get_translation(language_code, "text_please_select_service")
            await update.callback_query.edit_message_text(text, parse_mode='HTML',
                                                                reply_markup=keyboard)
    # настройка часового пояса

    elif data[0] == 'timezone':
        operation = data[1]
        current_user_info = get_user_info(user_id, 'clients_table')
        last_selected_service_id = current_user_info['service_id']
        if operation == 'page':
            page = int(data[2])
            update_client_user_info(user_id, **{'operation': f'set_timezone', 'kbd_msg_id': message_id})

            await edit_and_delete_messages(update, context, kbd_message_id,
                                           get_translation(language_code, 'text_select_timezone'),
                                           create_client_timezone_setting_keyboard(language_code, user_id, page, last_selected_service_id))

        else:
            if operation not in timezones:
                operation = DEFAULT_TIMEZONE
            # сохраняем часовой пояс
            update_client_user_info(user_id, **{'user_timezone': operation})
            # показываем основное меню
            text = get_service_description_text(language_code, user_id, last_selected_service_id)
            text += f'\n\n{get_service_contacts_text(language_code, user_id, last_selected_service_id)}'
            text += f"\n\n{get_user_bookings_info_text(language_code, user_id, last_selected_service_id)}"
            text += f"\n{get_data_update_info_text(language_code, user_id, last_selected_service_id)}"

            keyboard = create_client_main_menu_keyboard(language_code, user_id, last_selected_service_id)
            msg = await update.callback_query.edit_message_text(text, parse_mode='HTML',
                                                                reply_markup=keyboard)

            update_client_user_info(user_id, **{'operation': f'return_menu'})

            # отправляем сообщение об установке часового пояса
            text = get_translation(language_code, 'text_timezone_is_set')
            text = replace_placeholders(text, operation)
            msg = await context.bot.send_message(chat_id=user_id, text=text)
            messages_to_delete.append(msg.message_id)


    context.user_data['messages_to_delete'] = messages_to_delete
    update_client_user_info(user_id, **{'kbd_msg_id': message_id})

# обработчик ошибок
async def error_handler(update, context):
    # logging.error(f"Exception while handling an update: {context.error}")
    print(f"{bcolors.FAIL}{format_date('en', datetime.now())} An error occurred:{bcolors.ENDC} {context.error}")
    

# отправляем сообщение админу сервиса
async def send_message_to_service_admin(user_id, booking_id, service_id, msg):
    service = get_service_settings_by_service_id(service_id)
    booking = get_booking_info(booking_id, user_id)
    user = get_user_info(user_id, 'clients_table')

    admin_info = get_user_info(service['user_id'], 'users_table')
    admin_language_code = admin_info['language_code']

    subservices = ""
    for index, subservice in enumerate(booking['subservices']): 
        if index > 0:
            subservices += ", "
        subservices += f"{subservice['name']}"

    hours = booking['total_duration'].seconds // 3600
    minutes = (booking['total_duration'].seconds % 3600) // 60
    total_duration = f"{hours} {get_translation(admin_language_code, 'btn_h.ours')} {minutes} {get_translation(admin_language_code, 'btn_m.inutes')}"

    text = f"{get_translation(admin_language_code, msg)}"
    text = replace_placeholders(text,
                                f"{user['first_name']} {user['last_name'] if user['last_name'] is not None else ''}",
                                f"{user['username']} +{user['phone_number']}",
                                subservices,
                                format_date(admin_language_code, booking['slot_datetime']),
                                total_duration,
                                int(float(booking['total_cost']))
                                )

    bot = Bot(token=BOT_SETTINGS['admin_api_token'])

    try:
        await bot.send_message(chat_id=service['user_id'], text=text, parse_mode='HTML')
    except Forbidden as e:
        if "bot was blocked by the user" in str(e):
            # Обновляем статус пользователя
            set_additional_service_setting(service['user_id'], "status", 'bot_was_blocked')
            print(f"{bcolors.FAIL}Bot was blocked{bcolors.ENDC} by user {service['user_id']}. Status updated to 'bot_was_blocked'.")
            return 'blocked'
        else:
            # Если это другая ошибка Forbidden, можно обработать её отдельно
            print(f"{bcolors.FAIL}Forbidden error occurred:{bcolors.ENDC} {e}")
    except Exception as e:
        # Обработка других ошибок
        print(f"{bcolors.FAIL}An error occurred:{bcolors.ENDC} {e}")

    return True


def main() -> None:
    try:
        print(f"Starting Client bot.")
        print(f"Loading DB configuration...")

        get_bot_info_by_id(9) # загружаем настройку с токенами и таблицами
        print(f"Loaded.")
        print(f"Starting bot.")
        # Создаем Application и передаем ему токен вашего бота.
        global application
        application = Application.builder().token(BOT_SETTINGS['client_api_token']).http_version(
            '1.1').connection_pool_size(10).pool_timeout(10).build()

        print(f'{bcolors.OKCYAN}Done.{bcolors.ENDC}')

        # Регистрируем обработчики команд
        application.add_handler(CommandHandler("start", start))
        application.add_handler(MessageHandler(filters.CONTACT, handle_phone_number))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
        application.add_handler(CallbackQueryHandler(handle_callback_query))

        # Регистрируем обработчик ошибок
        application.add_error_handler(error_handler)

        # Запускаем бота
        application.run_polling()
    except Exception as e:
        print(f"{bcolors.WARNING}An error occurred:{bcolors.ENDC} {e}")


if __name__ == '__main__':
    main()
