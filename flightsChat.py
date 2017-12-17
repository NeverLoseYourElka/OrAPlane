#!/usr/bin/env python
# -*- coding: utf-8 -*-

from datetime import datetime
#из модуля threading импорт класса Thread для создания потоков
from threading import Thread

# импортируем наши модули
import yandexAvia
import time
import tools

def format_place(x):
	'''
	метод, который делает строку вида 'Москва, Россия (MOW)' из дикшинари, 
	содержащего информацию о месте (такого, массив которых возвращает yandexAvia.get_suggests())
	'''
	return (x['name']+', '+x['info']['country_title']+' ('+x['info']['point_code']+')')

class Subscriptions:
	'''
	класс для управления подписками, сохранения и загрузки их из файла
	'''
	# формат даты и времени, в котором, мы ее храним в поле last_send у подписок
	datetime_format = '%Y-%m-%d %H:%M:%S.%f'
	# файл, в который сохраняем подписки
	filename = 'subscriptions.json'
	''' дикшинари с подписками, структуры
	{
		"<chatId>" : {
			"<query>" : {
				"interval" : <int>,
				"last_send" : "<datetime string>"
			}
		}
	}
	'''
	subscriptions = tools.load_from_json(filename, {})
	# ссылка на метод для старта поиска
	start_search = None

	def init(tg, start_search):
		'''
		метод, который вызывается, чтобы бот начал мониторить активные подписки
		'''
		# назначаем ссылку на переданный метод start_search
		Subscriptions.start_search = start_search
		# пробегаемся по чатам подписок, чтобы они инициализировались и началось слежение за подписками
		for chatId in Subscriptions.subscriptions:
			# внутри get_chat() если класса чата с айди chatId нет, то он создается и инициализируется мониторинг подписок
			FlightsChat.get_chat(chatId, tg)

	def save():
		# сохраняем в файлик подписки
		tools.save_to_json(Subscriptions.subscriptions, Subscriptions.filename)

	def get_for(chat):
		'''
		метод возвращает дикшинари подписок для чата (по ссылке, т.е. его можно изменять из вне)
		'''
		if not str(chat.chatId) in Subscriptions.subscriptions:
			# если нет дикшинари с подписками для чата chat, то создаем его пустым
			Subscriptions.subscriptions[str(chat.chatId)] = {} #{ queryStr: {'interval': intervalHours, 'last_send': datetime } }
		# возвращаем дикшинари
		return Subscriptions.subscriptions[str(chat.chatId)]

	def add_for(chat, query, interval):
		'''
		метод для добавления подписки чату с параметрами запроса query и интервалом interval
		'''
		# назначаем для чата и query параметры подписки
		Subscriptions.get_for(chat)[query] = {
			'interval': interval,
			'last_send': datetime.now().strftime(Subscriptions.datetime_format)
		}
		# сохраняем в файл сразу после изменений
		Subscriptions.save()
		# логаем, что добавили такую-то подписку
		tools.log('Added sub "',query,'" for ',chat.chatId)

	def del_for(chat, query):
		'''
		удаляем подписку с параметрами поиска query для чата chat
		'''
		# если такие параметры поиска (query) есть в подписках
		if query in Subscriptions.get_for(chat):
			# удаляем дикшинари с параметрами подписки по ключу query
			del Subscriptions.get_for(chat)[query]
			# сохраняем в файл измененные подписки
			Subscriptions.save()
			# возвращаем True, мол, удалили успешно
			return True
		# возвращаем False, мол, не удалили
		return False

class SearchParameters:
	'''
	класс для хранения параметров поиска авиабилетов
	'''

	def __init__(self, query_str = None):
		'''
		конструктор класса SearchParameters
		'''
		# формат даты и времени, который требует яндекс для запроса на старт поиска
		self.date_for_search_format = '%Y-%m-%d'
		# переменная для хранения айди сообщения о начале поиска
		# чтобы после завершения поиска сделать reply на него в чате
		self.searching_message_id = None

		# если в конструктор передавали запрос поиска, то парсим его и раскидываем по переменным
		if query_str is not None:
			words = query_str.split(' ')
			self.origin = words[0]
			self.destination = words[1]
			self.date = datetime.strptime(words[2], self.date_for_search_format)
		else:
			# иначе делаем все переменные пустыми
			self.date = None
			self.origin = None
			self.destination = None

	def is_ready_for_search(self):
		# можно ли с текущими параметрами начать поиск
		return self.date is not None and self.origin is not None and self.destination is not None

	def date_for_search(self):
		# возвращает дату для поиска в формате, который требует яндекс
		return None if self.date is None else self.date.strftime(self.date_for_search_format)

	def query_str(self):
		# возвращает строку, содержащую параметры поиска
		return self.origin+' '+self.destination+' '+self.date_for_search()

	def formatted_str(self):
		'''
		метод возвращает форматированную строку с параметрами поиска для показа пользователю
		'''

		# yandexAvia.place_for_key возвращает дикшинари с информацией о месте
		origin = format_place(yandexAvia.place_for_key(self.origin))
		destination = format_place(yandexAvia.place_for_key(self.destination))
		# строка даты в виде '21 Jan 2018'
		date = self.date.strftime('%d %b %Y')
		'''
		формат вывода

		'From: '
		'To:   '
		'Date: '

		'''
		return '<pre>From: ' + origin + '\nTo:   ' + destination + '\nDate: ' + date + '</pre>'

class FlightsChat:
	'''
	класс, который хранит инфу о каком-то конкретном чате
	'''

	# статическая переменная - дикшинари для экземпляров класса FlightsChat по айди чата
	chats = {}

	def __init__(self, chatId, tg):
		'''
		конструктор класса FlightsChat, которому нужен айди чата и ссылка на экземпляр класса Telegram
		'''
		# айди чата пихаем в переменную
		self.chatId = chatId
		# запоминаем ссылку на экземпляр класса Telegram
		self.tg = tg
		# запускаем вотчер для подписок этого чата
		self.start_watch_subscriptions()
		# устанавливаем некоторые переменные пустыми
		self.reset()

	def get_chat(chatId, tg):
		'''
		статический метод для получения класса FlightsChat с айдишником chatId
		'''
		if not str(chatId) in FlightsChat.chats:
			# если в chats нет ключа chatId, создаем экземпляр класса FlightsChat по ключу chatId
			FlightsChat.chats[str(chatId)] = FlightsChat(str(chatId), tg)
		# возвращаем, что должны
		return FlightsChat.chats[str(chatId)]

	def reset(self):
		# пустые параметры поиска
		self.params = SearchParameters()
		# пустая капча
		self.captcha = None
		# пустая настройка подписки
		self.setting_subscription = None
		# поиск на данный момент никакой не запущен
		self.searching_now = False

	def subscribe(self, query, interval_hours = 0):
		'''
		метод для подписки на поиск у чата
		'''
		min_interval = 1
		if interval_hours > min_interval:
			Subscriptions.add_for(self, query, interval_hours)
			self.send_message('Subscribed for every '+str(interval_hours)+' seconds.\n'+SearchParameters(query).formatted_str())
			return True
		
		self.send_message('Please choose interval greater than '+str(min_interval))
		return False

	def unsubscribe(self, query):
		'''
		метод для удаления подписки у чата
		'''
		if Subscriptions.del_for(self, query):
			self.send_message('Unsubscribed.')

	def send_message(self, text, params = None):
		'''
		обертка для метода sendMessage класса Telegram (для удобства)
		'''
		return self.tg.sendMessage(self.chatId, text, params)

	def send_subscriptions(self):
		'''
		метод для отправки списка подписок пользователю
		'''
		tools.log('send_subscriptions',Subscriptions.get_for(self))

		# если количество ключей подписок == 0
		if len(Subscriptions.get_for(self).items()) == 0:
			self.send_message('You have no subscriptions.')

		# пробегаемся по подпискам в этом чате
		for query,query_params in Subscriptions.get_for(self).items():
			# вытаскиваем интервал подписки
			interval = query_params['interval']
			# вытаскиваем форматировнный вид параметров поиска у этой подписки
			params_formatted_str = SearchParameters(query).formatted_str()
			# отправляем пользователю сообщение с информацией о подписке и кнопочкой "отписаться"
			self.send_message('Every '+str(interval)+' seconds:\n'+params_formatted_str,
				tg.inlineKeyboard([[{
						'text':'Unsubscribe',
						'callback_data':'unsub '+query
					}]]))

	def start_watch_subscriptions(self):
		# создаем поток для выполнения метода watch_subscriptions
		thread = Thread(target = self.watch_subscriptions)
		# запускаем его
		thread.start()

	def watch_subscriptions(self):
		# получаем объект подписок этого чата (по ссылке)
		mysubs = Subscriptions.get_for(self)
		tools.log('Started watch_subscriptions for',self.chatId)
		# бесконечно
		while True:
			# try тут нужен чтобы игнорировать экзепшены при изменении mysubs в другом потоке
			try:
				# пробегаемся по подпискам этого чата (по ключам дикшинари)
				for query in mysubs:
					# вытаскиваем параметры подписки с ключом (в то же время - строкой с параметрами поиска) query
					params = mysubs[query]
					# парсим время, когда эту подписку последний раз отправляли
					last_send = datetime.strptime(params['last_send'], Subscriptions.datetime_format)
					# считаем время, которое прошло с тех пор 
					elapsed_hours = (datetime.now() - last_send).total_seconds()#/3600 # раскоментить деление, чтобы были часы, а не секунды
					# если оно больше интервала подписки
					if elapsed_hours > params['interval']:
						# обновляем время отправки этой подписки
						params['last_send'] = datetime.now().strftime(Subscriptions.datetime_format)
						# сохраняем подписки в файлик т.к. изменили поле last_send 
						Subscriptions.save()
						# начинаем поиск с параметрами поиска query и предварительным сообщением 'Subscription:'
						Subscriptions.start_search(self, SearchParameters(query), 'Subscription:')
			except:
				pass
			# паузим поток на секунду
			time.sleep(1)





