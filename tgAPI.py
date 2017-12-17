#!/usr/bin/env python
# -*- coding: utf-8 -*-

#импорт модуля, который умеет работать с HTTP запросами
import requests
#импорт модуля, который умеет парсить json строки в питоновские объекты (dict/list)
import json
#импорт модуля tools - одного из наших файлов
import tools

'''
	документация Telegram Bot API
	https://core.telegram.org/bots/api
'''

class Message:
	'''
	класс, который несет в себе информацию о сообщении, пришедшем боту
	'''
	def __init__(self, message):
		'''
		конструктор класса, в который передается дикшинари message

		message в данном случае - дикшинари,
		#соответствующий типу Message в документации "Telegram Bot API"
		'''
		#переменной chatId текущего экземпляра класса присваиваем айди чата, в котором пришло сообщение
		self.chatId = str(message['chat']['id'])
		#переменной текст присваиваем текст сообщения, если он был в нашем message, а иначе - пустую строку
		self.text = message['text'] if 'text' in message else ''

class User:
	'''
	информация о пользователе телеграмма
	'''
	def __init__(self, user):
		'''
		user - объект как тип User в документации "Telegram Bot API"
		'''
		#вытаскиваем айди юзера в переменную класса
		self.id = str(user['id'])
		#self.first_name = user['first_name'] if 'first_name' in user else ''
		#self.last_name = user['last_name'] if 'last_name' in user else ''
		#self.username = user['username'] if 'username' in user else None

class Telegram:
	'''
	класс, который умеет общаться с сервером telegram'a соответсвенно документации

	телеграм возвращает апдейты по нашему запросу пачками,
	каждый апдейт это дикшинари вида https://core.telegram.org/bots/api#update

	offset - номер апдейта, который мы обработали последним
		при запросах мы передаем этот offset телеграму, 
		чтобы он не возвращал нам еще раз те апдейты,
		которые мы уже обрабатывали
	URL - просто URL адресс для запросов к телеге
	TOKEN - наш токен бота, который по сути является для него логином и паролем одновременно

	'''
	offset = 0
	URL = 'https://api.telegram.org/bot'
	#в папке data должен быть файлик tg.auth с содержимым вида
	#	{"token":"<token>"}
	#если не сможем считать из этого файла объект с токеном, 
	#то представляем, что считали именно объект {'token':'none'}
	TOKEN = tools.load_from_json('tg.auth', {'token':'none'})['token']
	#массив ссылок на методы, которые будут вызываться при получении апдейтов от телеги
	#	экземпляр класса Message, соответствующий апдейту, будет передан аргументом в эти методы
	listeners = []
	#то же самое, только для callback'ов, они приходят, когда юзер нажал кнопку, которую мы ему раньше отправляли
	# 	chatId, callback_data, callback_id - параметры, которые будут переданы в эти методы
	callback_listeners = []

	def __init__(self):
		'''
		пустой конструктор
		'''
		#ниче не делаем
		pass

	def inlineKeyboard(self, rowsOfButtons):
		'''
		возвращает дикшинари, который мы потом прицепим к нашему сообщению,
		чтобы прикрепить в чате к этому сообщению кнопки, переданные как rowsOfButtons
		
		rowsOfButtons - массив массивов кнопок (массив строк, в каждой строке - массив кнопок),
		их надо формировать в соответствии с документацией
		сам reply_markup:
		https://core.telegram.org/bots/api#inlinekeyboardmarkup
		каждая кнопка:
		https://core.telegram.org/bots/api#inlinekeyboardbutton
		'''
		#ensure_ascii = False, оставляет неASCII символы (при сериализации в json строку) нетронутыми
		return { 'reply_markup': json.dumps({ 'inline_keyboard': rowsOfButtons }, ensure_ascii=False)}

	def addMessageListener(self, listener):
		'''
		передаем сюда метод как listener откуда-нибудь, 
		чтобы этот метод вызывался при получении ботом сообщений

		экземпляр класса Message, соответствующий сообщению, будет передан аргументом в этот методы
		'''
		#просто пихаем ссылку на метод (т.е. listener) в массив listeners
		self.listeners.append(listener)

	def addCallbackDataListener(self, listener):
		'''
		listener - какой-то метод для вызова при получении callback'ов
		
		(chatId, callback_data, callback_id) - аргументы, которые будут переданы в этот метод
		'''
		self.callback_listeners.append(listener)

	def onUpdate(self, update):
		'''
		обрабатываем Update 
		https://core.telegram.org/bots/api#update
		'''
		if 'message' in update:
			msg = Message(update['message'])
			#каждый метод в listeners вызываем, как надо
			for l in self.listeners:
				l(msg)

		#если же это callback, каждый метод в callback_listeners вызываем, как надо
		if 'callback_query' in update:
			for l in self.callback_listeners:
				l(update['callback_query']['message']['chat']['id'], update['callback_query']['data'], update['callback_query']['id'])

	def doMethod(self, methodName, data):
		'''
		делаем HTTP запрос для какого-то имени метода methodName из документации телеграма
		'''
		try:
			#POST-HTTP запрос с данными data
			request = requests.post(self.URL+self.TOKEN+'/'+methodName, data=data)
		except:
			#что-то пошло не так - логаем, возвращаем None, мол, нет результата запроса
			tools.log('Send message error; data:',data)
			return None

		#если код ответа сервера на наш запрос не 200 (т.е. успешно),
		#	то возвращаем None, мол, нет результата запроса
		if not request.status_code == 200:
			try:
				# пробуем из ответа сервера вытащить описание по ключу description, но его
				# может не оказаться, может вывалиться экзепшен при преобразовании ответа сервера в json,
				# поэтому тут try-except есть
				tools.log(methodName,' >> TG REQUEST ERROR: ',request.json()['description'])
			except:
				# pass - пустышка для блока except, она ничего не делает
				pass
			return None

		# возвращаем результат запроса - ответ сервера, 
		# предварительно превращая его из json строки в dictionary методом .json()
		return request.json()

	def sendPhoto(self, chatId, url, caption = None):
		'''
		отправляем url фотки в чат с айдишником chatId, 
		опционально указываем подпись к фотке - caption
		'''
		# data согласно докам
		# https://core.telegram.org/bots/api#sendphoto
		data = {
			'chat_id': int(chatId),
			'photo': url
		}

		# если подпись все-таки есть, добавляем ее в наш дикшинари data
		if caption is not None:
			data['caption'] = caption

		# очевидно
		return self.doMethod('sendPhoto', data)

	def sendMessage(self, chatId, text, params = None):
		'''
		отправляем в чат с айдишником chatId и текстом text,
		дополнительные параметры - дикшинари params
		'''
		data = {
			'chat_id': int(chatId),
			'text':text,
			'parse_mode':'HTML'
		}

		if params is not None:
			#для каждого ключа и значения в params
			for k,v in params.items():
				#добавляем этот ключ и значение в data
				data[k] = v

		return self.doMethod('sendMessage', data)

	def answerCallbackQuery(self, callback_query_id, text = None):
		'''
		отвечаем на callback,
		если хотим - передаем сюда text, который увидит пользователь во всплывающем окошке в диалоге
		'''
		data = {
			'callback_query_id':callback_query_id
		}

		if text is not None:
			data['text'] = text

		return self.doMethod('answerCallbackQuery', data)

	def check_updates(self):
		# данные запроса
		# https://core.telegram.org/bots/api#getupdates
		data = {'offset': self.offset+1, 'limit': 0, 'timeout': 1}
		response_obj = self.doMethod('getUpdates', data)

		if response_obj and 'result' in response_obj:
			for update in response_obj['result']:
				self.offset = update['update_id']
				self.onUpdate(update)

	def work(self):
		'''
		бесконечно запрашиваем апдейты у телеграма
		'''
		while True:
			self.check_updates()
