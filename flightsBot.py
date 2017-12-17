#!/usr/bin/env python
# -*- coding: utf-8 -*-

from datetime import datetime
#из модуля threading импорт класса Thread для создания потоков
from threading import Thread
import time

# импорт модуля yandexAvia
import yandexAvia
# импорт модуля tools
import tools
#импорт из модуля tgAPI класса Telegram
from tgAPI import Telegram
#импорт из модуля flightsChat наших классов
from flightsChat import FlightsChat, SearchParameters, Subscriptions, format_place

# создаем глобальную переменную - экземпляр класса Telegram
tg = Telegram()

def send_suggests(chat, text, place_type = 'origin'):
	'''
	метод отправляет варианты городов пользовтелю (с названием похожим на text)
	place_type - строка, значение которой имеет два варианта : origin и destination
		origin - когда мы отправляем результаты поиска места отправления
		destination - когда мы отправляем результаты поиска места назначения
	'''
	# suggests - дикшинари, который содержит параметры для отправки кнопок, прикрепленных к сообщению
	suggests = get_suggests_as_inline(text, place_type)
	if suggests is not None:
		# если нашли похожие на запрос поиска варианты - отправляем их
		chat.send_message('Select '+place_type+':', suggests)
	else:
		# Если ничего не нашли, отправляем, что ничего не нашли
		chat.send_message('Nothing found')

def send_guide(chat):
	'''
	метод для отправки подсказки пользователю о том, что мы от него сейчас ждем
	'''
	# если переменная капчи не пуста, отправляем, что хотим капчу
	if chat.captcha is not None:
		chat.send_message('Please, submit the captcha.')

	# если переменная настраиваемой подписки не пуста, отправляем, что хотим интервал для этой подписки
	elif chat.setting_subscription is not None:
		chat.send_message('Send subscription interval in hours. Or /cancel to cancel subscription setting.')

	# если нет места отправления, отправляем, что пользователь должен ввести имя места для поиска вариантов
	elif chat.params.origin is None:
		chat.send_message('Send origin name or it\'s part.')

	# то же самое для места назначения
	elif chat.params.destination is None:
		chat.send_message('Send destination name or it\'s part.')

	# если нет даты, отправляем, что пользователь должен ввести дату для поиска
	elif chat.params.date is None:
		chat.send_message('Send date in format dd.mm.yyyy')

	# если все предыдущие проверки оказались False, отправляем сообщение с настроенными параметрами поиска и кнопкой "Search"
	else:
		send_search_button(chat)


def on_message(msg):
	'''
	ловим сообщения от телеги
	'''

	# даем питону знать, что tg - глобальная переменная
	global tg
	# получаем чат, для которого пришло сообщение msg
	chat = FlightsChat.get_chat(msg.chatId, tg)

	# если текст сообщения такой
	if msg.text == "/start": 
		# сбрасываем параметры чата
		chat.reset()
		# отправляем приветствие
		chat.send_message("Hello, I can search avia tickets. Send /start again to reset search.")
		# отправляем гайд
		send_guide(chat)

	# иначе если текст сообщения такой
	elif msg.text == "/cancel":
		# если мы ждали интервал для какой-то подписки chat.setting_subscription
		if chat.setting_subscription is not None:
			# сбрасываем ожидание интервала
			chat.setting_subscription = None
			chat.send_message('Setting subscription cancelled.')

	elif msg.text == "/subs":
		# отправляем пользователю список его подписок
		chat.send_subscriptions()

	# если ждем капчу
	elif chat.captcha is not None:
		# отправляем капчу яндексу
		yandexAvia.submit_captcha(chat.captcha, msg.text)
		# вытаскиваем параметры поиска, с которыми эта капча вылезла
		params = chat.captcha['search_parameters']
		# сбрасываем ожидание капчи
		chat.captcha = None
		# запускаем поиск с теми параметрами еще раз (асинхронный - в новом потоке)
		async_start_search(chat, params)

	# если мы ждем интервал для подписки
	elif chat.setting_subscription is not None:
		# парсим число из текста сообщения
		interval = tools.try_parse_int(msg.text)
		# если получилось распарсить число
		if interval is not None:
			# создаем подписку
			if chat.subscribe(chat.setting_subscription, interval):
				# сбрасываем ожидание интервала подписки
				chat.setting_subscription = None
		else:
			# если не получилось распарсить, говорим пользователю, что это не число
			chat.send_message('This is not an integer number')

	# если не назначено место отправления
	elif chat.params.origin is None:
		# ищем места по тексту сообщения
		send_suggests(chat, msg.text, 'origin')

	# если не назначено место назначения
	elif chat.params.destination is None:
		# ищем места по тексту сообщения
		send_suggests(chat, msg.text, 'destination')

	# если не назначена дата
	elif chat.params.date is None:
		try:
			# пытаемся распарсить дату в локальную переменную
			date = datetime.strptime(msg.text, '%d.%m.%Y') # 2017-12-21
			# если получилось распарсить (не выкинуло экзепшен)
			# проверяем, не прошедшая ли это дата
			if date < datetime.now():
				# если прошедшая, сбрасываем локальную переменную в None
				date = None
				# отправляем пользователю сообщение
				chat.send_message("Please, send a future date.")
			# значение локальной переменной пихаем в параметры поиска чата
			chat.params.date = date
		except Exception as ex:
			# словили экзепшен (не смогли распарсить дату)
			# None пихаем в дату параметров поиска чата
			chat.params.date = None
			# говорим о экзепшене пользователю
			chat.send_message("Bad date format: "+str(ex))
		# отправляем гайд
		send_guide(chat)


def on_callback(chatId, data, callback_query_id):
	'''
	ловим callback'и от телеги
	'''

	global tg

	chat = FlightsChat.get_chat(chatId, tg)

	# получаем массив строк, разбивая текст данных callback'a 
	# 		пример: была строка data "1 2 лул ", words будет массив ['1', '2', 'лул', '']
	words = data.split(' ')

	# если первое слово origin
	if 'origin' == words[0]:
		# значит нажали кнопку выбора места отправления
		# пример строки data - 'origin c213 @Санкт-Петербург'
		
		# отвечаем телеге, что кнопка нажата, и мы что-то сделали
		if chat.params.destination == words[1]:
			# если выбираем место, которое уже выбрано местом назначения
			tg.answerCallbackQuery(callback_query_id, 'Origin and destination should be different')
		else:
			# тут все ок, как раз таки вытаскиваем то, что после символа @ в строке data, чтобы оповестить пользователя
			tg.answerCallbackQuery(callback_query_id, 'Origin set to '+data.split('@')[1])

			# берем место отправления из второго слова
			chat.params.origin = words[1]
		# отправляем гайд
		send_guide(chat)

	elif 'destination' == words[0]:
		# значит нажали кнопку выбора места назначения
		# пример строки data - 'destination c213 @Санкт-Петербург'

		# отвечаем телеге, что кнопка нажата, и мы что-то сделали
		if chat.params.origin == words[1]:
			# если выбираем место, которое уже выбрано местом назначения
			tg.answerCallbackQuery(callback_query_id, 'Origin and destination should be different')
		else:
			# тут все ок, как раз таки вытаскиваем то, что после символа @ в строке data, чтобы оповестить пользователя
			tg.answerCallbackQuery(callback_query_id, 'Destination set to '+data.split('@')[1])

			# берем место отправления из второго слова
			chat.params.destination = words[1]
		# отправляем гайд
		send_guide(chat)

	elif 'search' == words[0]:
		# значит нажали кнопку "Search"
		# создаем параметры поиска из части строки data, выкидывая из нее начало 'search '
		chat.params = SearchParameters(data.split('search ')[1])
		# запускаем поиск для этих параметров (в новом потоке)
		async_start_search(chat, callback_query_id = callback_query_id)

	elif 'sub' == words[0]:
		# значит нажали кнопку "Subscribe"
		# отвечаем телеге, что кнопка нажата, и мы что-то сделали
		tg.answerCallbackQuery(callback_query_id, 'Choose interval')
		# вытаскиваем строку параметров поиска из части строки data, выкидывая из нее начало 'sub '
		query_str = data.split('sub ')[1]
		# запоминаем строку параметров поиска query_str, чтобы ждать интервал для подписки
		chat.setting_subscription = query_str
		# отправляем гайд
		send_guide(chat)

	elif 'unsub' == words[0]:
		# значит нажали кнопку "Unsubscribe"
		# отвечаем телеге, что кнопка нажата, и мы что-то сделали
		tg.answerCallbackQuery(callback_query_id, 'Unsubscribed')
		query_str = data.split('unsub ')[1]
		chat.unsubscribe(query_str)

	elif 'change' == words[0]:
		# значит нажали кнопку "Change ..." а что именно менять будет вторым словом
		if words[1] == 'origin':
			# сбрасываем место отправления
			chat.params.origin = None
		elif words[1] == 'destination':
			# сбрасываем место назначения
			chat.params.destination = None
		else:
			# сбрасываем дату
			chat.params.date = None
		# отвечаем телеге, что кнопка нажата, и мы что-то сделали
		tg.answerCallbackQuery(callback_query_id)
		# отправляем гайд
		send_guide(chat)


def send_search_button(chat):
	'''
	метод для отправки кнопки поиска с инфой о параметрах поиска
	'''

	# если параметры не готовы для поиска, ничего не делаем
	if not chat.params.is_ready_for_search():
		return

	# создаем клавиатуру с кнопкой поиска
	inline_keyboard = tg.inlineKeyboard([
		[{
			'text': 'Search',
			# callback_data - это то, что придет нам в метод on_callback в аргументе data при нажатии кнопки
			'callback_data': 'search '+chat.params.query_str()
		}]
	])

	# отправляем пользователю сообщение с клавиатурой (с кнопкой Search)
	chat.send_message(chat.params.formatted_str(), inline_keyboard)

def flight_format_str(f):
	'''
	метод для получения строки информации о каком-то перелете
		тут просто вытаскиваем всякие штуки из дикшинари переданном как аргумент f
		и делаем в итоге из всего этого строку, которую возвращаем
	'''

	arrival_time = datetime.strptime(f['arrival']['local'], '%Y-%m-%dT%H:%M:%S').strftime('%H:%M (%d %b)')
	arrival_code = f['to']['code']
	arrival_title = f['to']['title']
	arrival_city = f['to']['settlement']['title']

	departure_time = datetime.strptime(f['departure']['local'], '%Y-%m-%dT%H:%M:%S').strftime('(%d %b) %H:%M')
	departure_code = f['from']['code']
	departure_title = f['from']['title']
	departure_city = f['from']['settlement']['title']

	flight = f['number']
	company_logo = f['company']['logoSvg']
	company_title = f['company']['title']

	return departure_time + " - " + arrival_time + "\n" + departure_city + " (" + departure_code + ") - " + arrival_city + " (" + arrival_code + ")\n" + flight + "    " + company_title


def search_done(chat, data, query_str, searching_message_id = None):
	'''
	метод этот вызовется когда поиск завершится
	data - массив вариантов билетов
	query_str - строка параметров поиска
	searching_message_id - айди сообщения о начале поиска, чтобы на него сделать reply (для удобства пользователя)
	'''

	if data is None:
		chat.searching_now = False
		return False

	if len(data) == 0:
		# говорим, что ничего не нашли
		chat.send_message('Sorry, no flights found. :(')
		chat.searching_now = False
		return True

	# количество вариантов, которые мы отправим пользователю, из всех найденных
	count = 5
	# по всем вариантам билетов пробегаемся
	for var in data:
		msg = ""
		for f in var['flights']:
			# получаем строку о каждом полете в var - данном варианте билета 
			# и дописываем ее в строку msg
			msg += flight_format_str(f) + "\n\n"

		# строка цены
		price = str(var['price']['tariff']['value'])
		# валюта
		currency = var['price']['tariff']['currency']
		
		# отправляем информацию о всех перелетах данного варианта, его цену и валюту
		chat.send_message(msg + price + ' ' + currency)

		# минусуем счетчик
		count -= 1
		# если сколько хотели отправили, выходим из цикла
		if count == 0:
			break


	# после отправки всех вариантов билетов получаем подписки этого чата
	subs = Subscriptions.get_for(chat)

	# если это подписка, то сообщение = вы подписаны на этот поиск раз в столько-то часов
	# если не подписка, то сообщение = можете подписаться
	message = 'You can subscribe for results of this search' if query_str not in subs else ('Subscribed: Every '+str(subs[query_str]['interval'])+' hours')
	# кнопочки делаем
	params = tg.inlineKeyboard([
			[{
				# в зависимости от того, подписка ли, отправляем кнопку "подписаться"/"отписаться"
				'text':'Subscribe' if query_str not in subs else 'Unsubscribe',
				# callback соответствующий
				'callback_data':('sub ' if query_str not in subs else 'unsub ')+query_str
			}],
			# и еще кнопочки для смены параметров
			[{
				'text':'Change origin',
				'callback_data':'change origin'
			}],
			[{
				'text':'Change destination',
				'callback_data':'change destination'
			}],
			[{
				'text':'Change date',
				'callback_data':'change date'
			}]
		])
	# добавляем параметр для ответа на сообщение о начале поиска
	params['reply_to_message_id'] = searching_message_id
	# отправляем все это пользователя
	chat.send_message(message, params)
	
	chat.searching_now = False

	return True

def on_search_started(callback_query_id, chat, params):
	'''
	этот метод вызывается, когда поиск успешно начался (без капчи или других ошибок)
	'''
	# кидаем колбэк на нажатие кнопки, что поиск начался
	tg.answerCallbackQuery(callback_query_id, 'Searching...')
	# try чтобы бот не упал, если что-то пойдет не так с отправкой сообщения
	try:
		# отправляем сообщение о начале поиска с его параметрами и запоминаем айди отправленного сообщения
		params.searching_message_id = chat.send_message("Searching...\n"+params.formatted_str())['result']['message_id']
	except:
		pass

def async_start_search(chat, params = None, caption = None, callback_query_id = None):
	'''
	метод для асинхронного запуска поиска
	'''
	# создаем новый поток для метода start_search с аргументами (chat, params, caption, callback_query_id)
	thread = Thread(target = start_search, args = (chat, params, caption, callback_query_id))
	# запускаем поток
	thread.start()

def start_search(chat, params = None, caption = None, callback_query_id = None):
	'''
	метод для запуска поиска
	'''

	# если ждем капчу, не запускаем поиск
	if chat.captcha is not None:
		return False

	# если поиск уже идет, то говорим пользователю, что это так и не запускаем новый
	if chat.searching_now:
		# если есть на что отвечать, если кнопку нажали и колбэк пришел, 
		# 	айди которого передано в callback_query_id, то отвечаем на него
		if callback_query_id is not None:
			global tg
			tg.answerCallbackQuery(callback_query_id, 'Another search is performing')

		if caption is not None:
			# значит поиск был запущен из Subscription
			# ждем, пока текущий поиск завершится
			while chat.searching_now:
				time.sleep(1)
		else:
			# не запускаем поиск
			return False

	# ставим флаг, что сейчас идет поиск
	chat.searching_now = True

	# если конкретных параметров не передали, подтягиваем параметры чата
	if params is None:
		params = chat.params

	# запоминаем строку параметров поиска
	query_str = params.query_str()

	# если с параметрами что-то не так, говорим об этом пользователю
	if not params.is_ready_for_search():
		chat.send_message("Configure search parameters first.")
		# поиск завершился без результатов
		return search_done(chat, None, query_str)

	# если что-то там хотим отправить перед поиском, то отправляем (caption - просто строка)
	if caption is not None:
		chat.send_message(caption)


	data = None
	try:
		# пытаемся получить результаты поиска в переменную data
		data = yandexAvia.get_flights(params.origin, 
			params.destination, 
			params.date_for_search(), 
			on_search_started=on_search_started, 
			on_search_started_args=(callback_query_id, chat, params))
	except Exception as ex:
		# логаем экзепшен, если он вылез
		tools.log("EXCEPTION:\n",ex)

	# если yandexAvia.get_flights() вернул None или был какой-то экзепшен
	if data is None:
		# говорим пользователю, что что-то не так пошло
		chat.send_message("For some mysterious reasons I couldn't start search.")
		tools.log("COULDN'T START SEARCH")
		# поиск завершился без результатов
		return search_done(chat, None, query_str)

	# если yandexAvia.get_flights() вернул что-то типа { 'captcha' : { ... } }
	if 'captcha' in data:
		# запоминаем капчу для этого чата 
		chat.captcha = data['captcha']
		# докидываем в объект капчи строку параметров поиска, для которого она вылезла
		chat.captcha['search_parameters'] = params
		# отправляем картиночку капчи пользователю с просьбой разгадать ее
		url = chat.captcha['src']
		tg.sendPhoto(chat.chatId, url, 'I\'m sorry for this but you have to submit captcha')
		# поиск завершился без результатов
		return search_done(chat, None, query_str)

	if not data: # equals to empty dict
		# поиск завершен с пустыми результатами
		return search_done(chat, {}, query_str)

	# трансформируем структуру данных, которые вернул яндекс, в структуру, которую хотим видеть мы
	# fares - массив билетов (каждый билет может содержать несколько перелетов)
	fares = data['variants']['fares']
	# каждый из вариантов билетов трансформируем
	formatted = [format_fare(f, data) for f in fares]
	
	#закоменчен фильтр для поиска только прямых рейсов (с одним полетом)
	#formatted = filter(lambda x: len(x['flights']) == 1, formatted)

	# сортируем билеты по возрастанию цены
	formatted = sorted(formatted, key=lambda elem:elem['price']['tariff']['value'])

	# сохраним то, что получилось в файлик, чтобы можно было посмотреть при желании
	tools.save_to_json(formatted, '_formatted.json')
	# вызываем метод о завершении поиска
	return search_done(chat, formatted, query_str, params.searching_message_id)

	'''
	formatted - массив объектов вида:


	{
        "flights": [
            {
                "arrival": {
                    "local": "2017-12-20T07:00:00",
                    "offset": 180,
                    "tzname": "Europe/Minsk"
                },
                "company": {
                    "alliance": null,
                    "color": "#312782",
                    "id": 7,
                    "logoSvg": "//yastatic.net/rasp/media/data/company/svg/belavia.svg",
                    "title": "Белавиа",
                    "url": "http://www.belavia.by/"
                },
                "companyTariff": {
                    "baggageAllowed": true,
                    "baggageNorm": 20,
                    "carryon": true,
                    "carryonNorm": 8,
                    "id": 82,
                    "published": true
                },
                "departure": {
                    "local": "2017-12-20T05:40:00",
                    "offset": 180,
                    "tzname": "Europe/Moscow"
                },
                "from": {
                    "code": "DME",
                    "id": 9600216,
                    "phraseFrom": "Домодедово",
                    "phraseIn": "Домодедово",
                    "phraseTo": "Домодедово",
                    "settlement": 213,
                    "stationType": {
                        "prefix": "а/п",
                        "title": "аэропорт"
                    },
                    "tType": "plane",
                    "title": "Домодедово"
                },
                "number": "B2 954",
                "to": {
                    "code": "MSQ",
                    "id": 9600368,
                    "phraseFrom": "Минск-2",
                    "phraseIn": "Минск-2",
                    "phraseTo": "Минск-2",
                    "settlement": 157,
                    "stationType": {
                        "prefix": "а/п",
                        "title": "аэропорт"
                    },
                    "tType": "plane",
                    "title": "Минск-2"
                }
            },
            ...
        ],
        "price": {
            "baggage": [
                [                         #for first flight
                    "1d1d20d",
                    "1d1d20d"
                ],
                []
            ],
            "partner": {
                "logoSvg": "https://avatars.mds.yandex.net/get-avia/233213/2a0000015a8053771eaa4e15a06f99f3f855/svg",
                "title": "Supersaver"
            },
            "tariff": {
                "currency": "RUR",
                "value": 9093
            }
        }
    }

	'''

def format_fare(f, data):
	'''
	метод для трансформирования данных об одном билете в нужный нам вид
	(немного магии)
	'''
	fare = {
		'price':f['prices'][0],
		'route':f['route'][0] #array of flight ids
	}

	flights = [ ]
	for flightid in f['route'][0]:
		info = dict(data['reference']['flights'][flightid])

		if info['company'] is not None:
			info['company'] = data['reference']['companies'][str(info['company'])]
		if info['companyTariff'] is not None:
			info['companyTariff'] = data['reference']['companyTariffs'][str(info['companyTariff'])]
		info['from'] = dict(data['reference']['stations'][str(info['from'])])
		info['to'] = dict(data['reference']['stations'][str(info['to'])])
		info['from']['settlement'] = data['reference']['settlements'][str(info['from']['settlement'])]
		info['to']['settlement'] = data['reference']['settlements'][str(info['to']['settlement'])]

		flights.append(info)

	fare['flights'] = flights


	fare['price']['partner'] = data['reference']['partners'][fare['price']['partnerCode']]

	# возвращаем инфу о билете в том виде, который нам нужен
	return fare
	'''
	fare['price'] - дикшинари вида:

	{
		"baggage": [
	        [
	            "1d1d23d"
	        ],
	        []
	    ],
	    "fromCompany": true,
	    "partnerCode": "dohop_1165",
	    "queryTime": 2,
	    "tariff": {
	        "currency": "RUR",
	        "value": 3254
	    }
	}
	'''

def get_suggests_as_inline(name, callback_type = 'origin'):
	'''
	метод для получения параметра HTTP запроса к телеграму, который прицепит к сообщению кнопки с названиями мест
	'''
	# собственно получаем варианты мест с именем похожим на name
	suggests = yandexAvia.get_suggests(name)

	# если ничего не нашли возвращаем None
	if len(suggests) == 0:
		return None

	# иначе возвращаем клавиатурку
	return tg.inlineKeyboard([
		[{
			'text': format_place(x),
			'callback_data': callback_type+' '+x['info']['point_key']+' @'+x['name']
		}] for x in suggests
	])

# инициализируем подписки (передаем туда не async_start_search, так как подписки и так чекаются в другом потоке)
Subscriptions.init(tg, start_search)
# добавляем метод on_message как листенер при приходе сообщения боту
tg.addMessageListener(on_message)
# добавляем метод on_callback как листенер при приходе колбэка боту
tg.addCallbackDataListener(on_callback)

# запускаем в главном потоке работу класса Telegram
tg.work()