#!/usr/bin/env python
# -*- coding: utf-8 -*-

import requests
import json
#импорт из модуля bs4 класса BeautifulSoup
from bs4 import BeautifulSoup
from urllib.parse import urlencode, quote_plus
import time
import tools
from datetime import datetime
import codecs

avia_url = 'https://avia.yandex.ru'

# HTTP сессия для сохранения состояния cookies между HTTP запросами
# (в пределах кода в этом файле)
s = requests.Session()
places = tools.load_from_json('placesCache.json',{})

def place_for_key(key):
	if key in places:
		return places[key]
	return 'Unknown ('+key+')'

def submit_captcha(captcha, rep):
	'''
	метод для отправки капчи яндексу
	captcha - объектик, который мы формировали когда-то в get_flights
	'''
	# GET запрос по url'у с нужными параметрами
	url = avia_url+'/checkcaptcha?'+urlencode({'key':captcha['key']})+'&'+urlencode({'retpath':captcha['retpath']})+'&'+urlencode({'rep':rep})
	r = s.get(url)

def get_flights(fromId=None, toId=None, date=None, on_search_started=None, on_search_started_args=(), max_results=5):
	'''
	Примеры аргументов:
	fromId = c213, toId = c2, date = 2017-12-21

	Либо:
	search_url = 'url'
	'''
	searchurl = avia_url+'/search/?fromId='+fromId+'&toId='+toId+'&when='+date
	
	# логаем searchUrl
	tools.log(searchurl)
	# получаем html страничку по адресу searchUrl
	html_doc = s.get(searchurl).text
	# парсим ее штукой под названием BeautifulSoup
	soup = BeautifulSoup(html_doc, 'html.parser')

	# теперь ищем в супе html тэг img у которого атрибут class равен form__captcha
	captcha = soup.find("img", { "class" : "form__captcha" })
	# если он есть на странице
	if captcha is not None:
		# возвращаем дикшинари такой
		return { 
			'captcha': {
				# ket и retpath - идентификаторы капчи
				'key':soup.find("input", { "name" : "key" })['value'],
				'retpath':soup.find("input", { "name" : "retpath" })['value'],
				# src - url на картинку самой капчи
				'src':captcha['src']
			}
		}

	# тут значит капчи нет, значит поиск на серваке яндекса успешно начался
	# вытаскиваем с html страницы json, который хранит данные о поиске
	data_options = soup.find("div", { "class" : "_preloader" })['data-options']
	data = json.loads(data_options)

	# вытаскиваем из этих данных updateUrl, по которому будет запрашивать обновления результатов поиска у яндекса
	updateUrl = data['options']['settings']['updateUrl']
	# логаем его
	tools.log(updateUrl)

	# это метод, который мы вызываем, когда поиск успешно начался с соответсвующими аргументами
	if on_search_started is not None:
		# * просто разворачивает штуку вида "(1, 2, кек)" в "1, 2, кек" - кавычки - не строка, просто границы выражений
		on_search_started(*on_search_started_args)

	# запускаем опрос яндекса на обновление результатов поиска
	return start_polling(updateUrl, max_results)

def start_polling(updateUrl, max_results):
	data = s.get(avia_url+updateUrl).json()

	# время на опрос, если больше этого количества секунд пройдет, просто вернем то, что уже есть
	time_to_polling = 10
	# хитрая магия - на самом деле просто разжевываем, что нам яндекс ответил
	while (data == None or int(data['progress']['current']) < int(data['progress']['all'])) and (time_to_polling > 0) and (int(data['progress']['current']) < max_results):
		#2017-12-02T19:35:07
		form = '%Y-%m-%dT%H:%M:%S'
		timeobj = { 'time' : datetime.now().strftime(form) }
		# превращаем timeobj в строку вида 'time=2017-12-02T19%3A35%3A07'
		timeobj = urlencode(timeobj, quote_via=quote_plus)
		# склеиваем url для запроса (почему так? - так яндекс хочет)
		url = avia_url+updateUrl+'?'+timeobj+'&cont=1'
		try:
			# делаем запрос, пытаемся распарсить json
			data = s.get(url).json()
		except:
			# в случае экзепшена ничего не делаем, живем дальше
			pass
		tools.log(data['progress']['current'],'from',data['progress']['all'])

		# интервал запросов к яндексу для обновления результатов поиска в секундах
		polling_interval = 1
		# спим столько секунд
		time.sleep(polling_interval)
		# уменьшаем оставшееся время
		time_to_polling -= polling_interval

	# если в итоге у нас ничего не получилось получить от яндекса в качестве результатов поиска,
	# или там что-то странное и нет поля 'progress'
	# то просто возвращаем None
	if data is None or 'progress' not in data:
		tools.log('SEARCH ENDED WITH EMPTY RESULTS OR EXCEPTION')
		return None

	# для отладки сохраняем то, что нам яндекс вернул, как результаты поиска
	tools.save_to_json(data, '_data.json')

	# если по каким-то причинам не нашлось билетов, то вернем пустой dictionary
	if data['progress'] == 0:
		return { }

	return data

def get_suggests(query):
	# пример: из объекта {'query':'мос'} получится строка 'query=%D0%BC%D0%BE%D1%81'
	q = urlencode({'query':query}, quote_via=quote_plus)
	# код языка, на котором будут подсказки
	lang_code = 'en'
	# url для запроса подсказок мест по имени
	url = 'https://suggests.avia.yandex.ru/v2/avia?format=tickets&lang='+lang_code+'&national_version=ru&avia=true&need_country=true&have_airport_field=true&hidden_field=true&'+q

	# GET запрос, сразу парсим json в объект
	data = s.get(url).json()
	# для отладки сохраняли когда-то ответ сервера в файлик
	#tools.save_to_json(data, '_suggests.json')

	# трансформируем эту штуку, полученную от яндекса в массив дикшинари вида
	res = [{
		'name':x[1],
		'info':x[2]
	} for x in data[1]]

	# кэшируем места по их point_key в дикшинари places
	for p in res:
		places[p['info']['point_key']] = p

	# тут же сохраняем places в файл
	tools.save_to_json(places, 'placesCache.json')

	'''
	каждый объект массива res перед return'ом это такой дикшинари
	{
		'name': 'Домодедово', 
		'info': {
			'country_title': 'Россия', 
			'point_code': 'DME', 
			'city_title': 'Москва', 
			'hidden': 0, 
			'have_airport': 1, 
			'point_key': 's9600216', 
			'added': 0, 
			'region_title': 
			'Москва и Московская область', 
			'missprint': 0
		}
	}
	''' 

	# возвращаем только три первых подсказки из массива
	return res[:3]