#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# A simple chat client for matrix.
# This sample will allow you to connect to a room, and send/recieve messages.
# Args: host:port username password room
# Error Codes:
# 1 - Unknown problem has occured
# 2 - Could not find the server.
# 3 - Bad URL Format.
# 4 - Bad username/password.
# 11 - Wrong room format.
# 12 - Couldn't find room.

import sys
import logging
import time
import datetime
import json
import os
import pickle
import re
import threading
import random
import requests
import traceback
import ujson
import wget
import youtube_dl_api
import audio_utils as audio

from matrix_client.client import MatrixClient
from matrix_client.api import MatrixRequestError
from requests.exceptions import MissingSchema
import config as conf

client = None
log = None
data={}
lock = None

vk_threads = {}

vk_dialogs = {}

VK_API_VERSION = '5.95'
VK_POLLING_VERSION = '3'

currentchat = {}

def get_exception_traceback_descr(e):
  tb_str = traceback.format_exception(etype=type(e), value=e, tb=e.__traceback__)
  result=""
  for msg in tb_str:
    result+=msg
  return result

def process_command(user,room,cmd,formated_message=None,format_type=None,reply_to_id=None,file_url=None,file_type=None):
  global client
  global log
  global data
  try:
    log.debug("=start function=")
    answer=None
    room_settings=None
    user_settings=None

    if reply_to_id!=None and format_type=="org.matrix.custom.html" and formated_message!=None:
      # разбираем, чтобы получить исходное сообщение и ответ
      source_message=re.sub('<mx-reply><blockquote>.*<\/a><br>','', formated_message)
      source_message=re.sub('</blockquote></mx-reply>.*','', source_message)
      source_cmd=re.sub(r'.*</blockquote></mx-reply>','', formated_message.replace('\n',''))
      log.debug("source=%s"%source_message)
      log.debug("cmd=%s"%source_cmd)
      cmd="> %s\n%s"%(source_message,source_cmd)

    if re.search('^@%s:.*'%conf.username, user.lower()) is not None:
      # отправленное нами же сообщение - пропускаем:
      log.debug("skip our message")
      return True


    log.debug("try lock() before access global data()")
    with lock:
      log.debug("success lock() before access global data")
      if user not in data["users"]:
        data["users"][user]={}
      if "settings" not in data["users"][user]:
        data["users"][user]["settings"]={}
        data["users"][user]["settings"]["enable"]=True
      if room not in data["rooms"]:
        data["rooms"][room]={}
        data["rooms"][room]["settings"]={}
        data["rooms"][room]["jobs"]=[]
        data["rooms"][room]["settings"]["enable"]=True

      room_settings=data["rooms"][room]["settings"]
      user_settings=data["users"][user]["settings"]
    log.debug("release lock() after access global data")

    log.debug("user=%s send command=%s"%(user,cmd))

    # Комната управления:
    # в любом состоянии отмена - всё отменяет:
    if re.search('^%s '%conf.bot_command, cmd.lower()) is not None:
      # команда нам:
      # берём команду:
      command=re.sub('^%s '%conf.bot_command, '', cmd.lower()).strip()

      # help
      if re.search('^help$', command) is not None:
        answer="""%(bot_command)s help - this help
  %(bot_command)s off - switch off bot voice to text translation in this room
  %(bot_command)s on - switch on bot voice to text translation in this room
  %(bot_command)s my off - switch off translations of my voice messages for all my rooms
  %(bot_command)s my on - switch on translations of my voice messages for all my rooms
  %(bot_command)s ping - check voice api status
  %(bot_command)s status - show current settings
        """ % {"bot_command":conf.bot_command}
        return send_notice(room,answer)

      # off
      if re.search('^off$', command) is not None:
        log.debug("try lock() before access global data()")
        with lock:
          log.debug("success lock() before access global data")
          room_settings["enable"]=False
          save_data(data)
        log.debug("release lock() after access global data")
        answer="""disable translate your voice to text for this room"""
        return send_notice(room,answer)

      # on
      if re.search('^on$', command) is not None:
        log.debug("try lock() before access global data()")
        with lock:
          log.debug("success lock() before access global data")
          room_settings["enable"]=True
          save_data(data)
        log.debug("release lock() after access global data")
        answer="""enable translate your voice messages to text for this room"""
        return send_notice(room,answer)

      # my on
      if re.search('^my on$', command) is not None:
        log.debug("try lock() before access global data()")
        with lock:
          log.debug("success lock() before access global data")
          user_settings["enable"]=True
          save_data(data)
        log.debug("release lock() after access global data")
        answer="""enable translate your voice to text for all your (%s) rooms"""%user
        return send_notice(room,answer)

      # my off
      if re.search('^my off$', command) is not None:
        log.debug("try lock() before access global data()")
        with lock:
          log.debug("success lock() before access global data")
          user_settings["enable"]=False
          save_data(data)
        log.debug("release lock() after access global data")
        answer="""disable translate your voice to text for all your (%s) rooms"""%user
        return send_notice(room,answer)

    # если бот включён в этой комнате:
    if re.search("^http",cmd)!=None:
      # пришла url-ссылка пробуем её обработать (скачать и сконвертировать в звук)
      filename=youtube_dl_api.video2ogg(log,cmd)
      if filename==None:
        result_string="error convert url '%s' to ogg"%cmd
        log.error(result_string)
        if send_notice(room,result_string)==False:
          log.error("send_notice(%s)"%room)
        return False

      # ========= begin translate ===========
      log.info("send converted file to user")
      oggdata=open(conf.store_tmp_path+'/'+filename,"rb").read()
      if send_audio_to_matrix(room,filename,oggdata) == False:
        message="error send voice to room"
        log.error(message)
        send_notice(room,message)
        return False
      return True
      #=======================================

  except Exception as e:
    log.error(get_exception_traceback_descr(e))
    log.error("exception process_command(): %s"%e)
    return False
  return True

def debug_dump_json_to_file(filename, data):
  global log
  log.debug("=start function=")
  json_text=json.dumps(data, indent=4, sort_keys=True,ensure_ascii=False)
  f=open(filename,"w+")
  f.write(json_text)
  f.close()
  return True
  
def leave_room(room_id):
  global log
  global client
  global lock
  global data
  log.debug("=start function=")

  try:
    # Нужно выйти из комнаты:
    log.info("Leave from room: '%s'"%(room_id))
    response = client.api.leave_room(room_id)
  except:
    log.error("error leave room: '%s'"%(room_id))
    return None
  try:
    # И забыть её:
    log.info("Forgot room: '%s'"%(room_id))
    response = client.api.forget_room(room_id)
  except:
    log.error("error forgot room: '%s'"%(room_id))

  log.debug("Try remove room: '%s' from data"%room_id)
  log.debug("try lock() before access global data()")
  with lock:
    log.debug("success lock() before access global data")
    if "rooms" in data:
      if room_id in data["rooms"]:
        # удаляем запись об этой комнате из данных:
        log.info("Remove room: '%s'"%room_id)
        del data["rooms"][room_id]
        log.info("save state data on disk")
        save_data(data)
      else:
        log.warning("room %s not in list rooms"%room_id)
    else:
      log.warning("rooms not in data")
  log.debug("release lock() after access global data")

  log.info("success leave from room '%s'"%room_id)
  return True
              
def save_data(data):
  global log
  log.debug("=start function=")
  data_path=conf.var_path+'/data.json'
  log.debug("save to data_file:%s"%data_path)
  try:
    data_file=open(data_path,"wb")
  except:
    log.error("open(%s) for writing"%data_path)
    return False
    
  try:
    pickle.dump(data,data_file)
    data_file.close()
  except:
    log.error("pickle.dump to '%s'"%conf.data_file)
    return False
  return True

def load_data():
  global log
  log.debug("=start function=")
  tmp_data_file=conf.var_path+'/data.json'
  reset=False
  if os.path.exists(tmp_data_file):
    log.debug("Загружаем файл промежуточных данных: '%s'" % tmp_data_file)
    data_file = open(tmp_data_file,'rb')
    try:
      data=pickle.load(data_file)
      data_file.close()
      log.debug("Загрузили файл промежуточных данных: '%s'" % tmp_data_file)
    except:
      log.warning("Битый файл сессии - сброс")
      reset=True
    if not "users" in data:
      log.warning("Битый файл сессии - сброс")
      reset=True
  else:
    log.warning("Файл промежуточных данных не существует")
    reset=True
  if reset:
    log.warning("Сброс промежуточных данных")
    data={}
    data["users"]={}
    data["rooms"]={}
    save_data(data)
  #debug_dump_json_to_file("debug_data_as_json.json",data)
  return data

def send_html(room_id,html):
  global client
  global log
  log.debug("=start function=")

  room=None
  try:
    room = client.join_room(room_id)
  except MatrixRequestError as e:
    print(e)
    if e.code == 400:
      log.error("Room ID/Alias in the wrong format")
      return False
    else:
      log.error("Couldn't find room.")
      return False
  try:
    room.send_html(html)
  except:
    log.error("Unknown error at send message '%s' to room '%s'"%(html,room_id))
    bot_system_message(user,'Не смог отправить сообщение в комнату: %s'%room_id)
    return False
  return True

def get_file(mxurl):
  global client
  global log
  log.debug("=start function=")
  log.debug("get_file 1")
  ret=None
  # получаем глобальную ссылку на файл:
  try:
    log.debug("get_file file 2")
    full_url=client.api.get_download_url(mxurl)
    log.debug("get_file file 3")
  except MatrixRequestError as e:
    log.error(e)
    if e.code == 400:
      log.error("ERROR download file")
      return None
    else:
      log.error("Couldn't download file (unknown error)")
      return None
  # скачиваем файл по ссылке:
  try:
    response = requests.get(full_url, stream=True)
    data = response.content      # a `bytes` object
  except:
    log.error("fetch file data from url: %s"%full_url)
    return None
  return data

def send_message(room_id,message):
  global client
  global log
  log.debug("=start function=")

  #FIXME отладка парсера
  #print("message=%s"%message)
  #return True

  room=None
  try:
    room = client.join_room(room_id)
  except MatrixRequestError as e:
    print(e)
    if e.code == 400:
      log.error("Room ID/Alias in the wrong format")
      return False
    else:
      log.error("Couldn't find room.")
      return False
  try:
    room.send_text(message)
  except:
    log.error("Unknown error at send message '%s' to room '%s'"%(message,room_id))
    return False
  return True

def send_notice(room_id,message):
  global client
  global log
  log.debug("=start function=")
  room=None
  try:
    room = client.join_room(room_id)
  except MatrixRequestError as e:
    print(e)
    if e.code == 400:
      log.error("Room ID/Alias in the wrong format")
      return False
    else:
      log.error("Couldn't find room.")
      return False
  try:
    room.send_notice(message)
  except:
    log.error("Unknown error at send notice message '%s' to room '%s'"%(message,room_id))
    return False
  return True


# Called when a message is recieved.
def on_message(event):
  global client
  global log
  global lock
  log.debug("=start function=")
  formatted_body=None
  format_type=None
  reply_to_id=None
  file_url=None
  file_type=None

  print("new MATRIX message:")
  print(json.dumps(event, indent=4, sort_keys=True,ensure_ascii=False))
  if event['type'] == "m.room.member":
      # join:
      if event['content']['membership'] == "join":
          log.info("{0} joined".format(event['content']['displayname']))
      # leave:
      elif event['content']['membership'] == "leave":
          log.info("{0} leave".format(event['sender']))
          if len(client.rooms[event['room_id']]._members)==1:
            # в этой комнате только мы остались:
            # close room:
            if leave_room(event['room_id']) == False:
              log.warning("leave_room()==False")
      return True
  elif event['type'] == "m.room.message":
      if event['content']['msgtype'] == "m.text":
          reply_to_id=None
          if "m.relates_to" in  event['content']:
            # это ответ на сообщение:
            try:
              reply_to_id=event['content']['m.relates_to']['m.in_reply_to']['event_id']
            except:
              log.error("bad formated event reply - skip")
              log.error(event)
              return False
          formatted_body=None
          format_type=None
          if "formatted_body" in event['content'] and "format" in event['content']:
            formatted_body=event['content']['formatted_body']
            format_type=event['content']['format']

      elif event['content']['msgtype'] == "m.audio":
        try:
          file_url=event['content']['url']
          if "fileinfo" in event['content']['info']:
            file_type=event['content']['info']['fileinfo']['mimetype']
          if "audioinfo" in event['content']['info']:
            file_type=event['content']['info']['audioinfo']['mimetype']
          else:
            file_type=event['content']['info']['mimetype']
        except:
          log.error("bad formated event with file data - skip")
          log.error(event)
          return False

      log.debug("%s: %s"%(event['sender'], event['content']["body"]))
      if process_command(\
          event['sender'],\
          event['room_id'],\
          event['content']["body"],\
          formated_message=formatted_body,\
          format_type=format_type,\
          reply_to_id=reply_to_id,\
          file_url=file_url,\
          file_type=file_type\
        ) == False:
        log.error("error process command: '%s'"%event['content']["body"])
        return False

  else:
    print(event['type'])
  return True

def on_event(event):
  global log
  log.debug("=start function=")
  print("event:")
  print(event)
  print(json.dumps(event, indent=4, sort_keys=True,ensure_ascii=False))

def on_invite(room, event):
  global client
  global log
  global lock
  global data
  log.debug("=start function=")

  log.debug(json.dumps(event, indent=4, sort_keys=True,ensure_ascii=False))

  # Просматриваем сообщения:
  for event_item in event['events']:
    if event_item['type'] == "m.room.join_rules":
      if event_item['content']['join_rule'] == "invite":
        user=event_item["sender"]
        # проверка на разрешения:
        allow=False
        if len(conf.allow_domains)>0:
          for allow_domain in conf.allow_domains:
            if re.search('.*:%s$'%allow_domain.lower(), user.lower()) is not None:
              allow=True
              log.info("user: %s from allow domain: %s - allow invite"%(user, allow_domain))
              break
        if len(conf.allow_users)>0:
          for allow_user in conf.allow_users:
            if allow_user.lower() == user.lower():
              allow=True
              log.info("user: %s from allow users - allow invite"%user)
              break
        if len(conf.allow_domains)==0 and  len(conf.allow_users)==0:
          allow=True

        if allow == True:
          # Приглашение вступить в комнату:
          log.debug("try join to room: %s"%room)
          log.info("wait 3 second before join for bug https://github.com/matrix-org/synapse/issues/2367...")
          time.sleep(3)
          room_class = client.join_room(room)
          log.debug("success join to room: %s"%room)
          room_class.send_text("Спасибо за приглашение! Недеюсь быть Вам полезным. :-)")
          room_class.send_text("Для справки по доступным командам - неберите: '!vs help'")
          log.debug("success send 'hello' to room: %s"%room)
          log.info("User '%s' invite me to room: %s and I success join to room"%(user,room))
          # Прописываем системную группу для пользователя 
          # (группа, в которую будут сыпаться системные сообщения от бота и где он будет слушать команды):
          with lock:
            if "users" not in data:
              data["users"]={}
            if user not in data["users"]:
              data["users"][user]={}
            save_data(data)
          log.debug("release lock() after access global data")
        else:
          log.warning("not allowed invite from user: %s - ignore invite"%user)

def exception_handler(e):
  global client
  global log
  log.debug("=start function=")
  log.error("main MATRIX listener thread except. He must retrying...")
  print(e)
  log.info("wait 30 second before retrying...")
  time.sleep(30)

def main():
  global client
  global data
  global log
  global lock

  lock = threading.RLock()

  log.debug("try lock before main load_data()")
  with lock:
    log.debug("success lock before main load_data()")
    data=load_data()
  log.debug("release lock() after access global data")

  log.info("try init matrix-client")
  client = MatrixClient(conf.server)
  log.info("success init matrix-client")

  try:
      log.info("try login matrix-client")
      token = client.login(username=conf.username, password=conf.password,device_id=conf.device_id)
      log.info("success login matrix-client")
  except MatrixRequestError as e:
      print(e)
      log.debug(e)
      if e.code == 403:
          log.error("Bad username or password.")
          sys.exit(4)
      else:
          log.error("Check your sever details are correct.")
          sys.exit(2)
  except MissingSchema as e:
      log.error("Bad URL format.")
      print(e)
      log.debug(e)
      sys.exit(3)

  log.info("try init listeners")
  client.add_listener(on_message)
  client.add_ephemeral_listener(on_event)
  client.add_invite_listener(on_invite)
  client.start_listener_thread(exception_handler=exception_handler)
  log.info("success init listeners")

  try:
    x=0
    log.info("enter main loop")
    while True:
      time.sleep(3)
  except Exception as e:
    log.error(get_exception_traceback_descr(e))
    log.error("exception at main loop check jobs: %s"%e)
    sys.exit(1)

  log.info("exit main loop")

def send_audio_to_matrix(room,file_name,audio_data):
  global log
  log.debug("=start function=")
  size=0
  # TODO добавить определение типа:
  mimetype="audio/ogg"
  
  mxc_url=upload_file(audio_data,mimetype)
  if mxc_url == None:
    log.error("uload file to matrix server")
    return False
  log.debug("send file 1")

  if sender_name!=None:
    file_name=sender_name+' прислал песню: '+file_name

  if matrix_send_audio(room,mxc_url,file_name,mimetype,size,duration) == False:
    log.error("send file to room")
    return False
  return True

def matrix_send_audio(room_id,url,name,mimetype="audio/mpeg",size=0,duration=0):
  global log
  global client
  log.debug("=start function=")
  ret=None
  room=None
  try:
    room = client.join_room(room_id)
  except MatrixRequestError as e:
    print(e)
    if e.code == 400:
      log.error("Room ID/Alias in the wrong format")
      return False
    else:
      log.error("Couldn't find room.")
      return False
  audioinfo={}
  audioinfo["mimetype"]=mimetype
  audioinfo["size"]=size
  audioinfo["duration"]=duration
  try:
    log.debug("send file 2")
    #ret=room.send_image(url,name,imageinfo)
    ret=room.send_audio(url,name,audioinfo=audioinfo)
    log.debug("send file 3")
  except MatrixRequestError as e:
    print(e)
    if e.code == 400:
      log.error("ERROR send audio with mxurl=%s"%url)
      return False
    else:
      log.error("Couldn't send audio (unknown error) with mxurl=%s"%url)
      return False
  return True

def upload_file(content,content_type,filename=None):
  global log
  global client
  log.debug("=start function=")
  log.debug("upload file 1")
  ret=None
  try:
    log.debug("upload file 2")
    ret=client.upload(content,content_type)
    log.debug("upload file 3")
  except MatrixRequestError as e:
    print(e)
    if e.code == 400:
      log.error("ERROR upload file")
      return None
    else:
      log.error("Couldn't upload file (unknown error)")
      return None
  return ret

def get_name_of_matrix_room(room_id):
  global client
  global log
  log.debug("=start function=")
  name=client.api.get_room_name(room_id)["name"]
  log.debug(name)
  log.debug("name of %s = %s"%(room_id,name))
  return name

if __name__ == '__main__':
  log= logging.getLogger("voice2str")
  if conf.debug:
    log.setLevel(logging.DEBUG)
  else:
    log.setLevel(logging.INFO)

  # create the logging file handler
  fh = logging.FileHandler(conf.log_path)
  formatter = logging.Formatter('%(asctime)s - %(name)s - %(filename)s:%(lineno)d - %(funcName)s() %(levelname)s - %(message)s')
  fh.setFormatter(formatter)

  if conf.debug:
    # логирование в консоль:
    #stdout = logging.FileHandler("/dev/stdout")
    stdout = logging.StreamHandler(sys.stdout)
    stdout.setFormatter(formatter)
    log.addHandler(stdout)

  # add handler to logger object
  log.addHandler(fh)

  log.info("Program started")
  main()
  log.info("Program exit!")