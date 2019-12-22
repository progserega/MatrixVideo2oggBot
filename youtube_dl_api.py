#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
from __future__ import unicode_literals
import random
import json
import re
import sys
import time
import logging
import traceback
import subprocess
import config as conf
import youtube_dl

log=None
result_filename=None

def get_last_error_descr():
  global last_error_descr
  return last_error_descr

def get_exception_traceback_descr(e):
  tb_str = traceback.format_exception(etype=type(e), value=e, tb=e.__traceback__)
  result=""
  for msg in tb_str:
    result+=msg
  return result

def exec_cmd(cmd_params):
  #t = subprocess.Popen(("pwgen","-s" ,"8", "1"), stderr=subprocess.PIPE,stdout=subprocess.PIPE)
  # /usr/local/bin/youtube-dl --extract-audio --audio-format vorbis --audio-quality 64K https://youtu.be/XMNqRbHWEig
  t = subprocess.Popen(cmd_params, stderr=subprocess.PIPE,stdout=subprocess.PIPE)
  ret_code=t.wait()
  if ret_code!=0:
    return None
  t_stdout_list=t.stdout.readlines()
  return t_stdout_list[0].strip('\n')


class ydlLogger(object):
  def debug(self, msg):
    global log
    log.debug(msg)
  def warning(self, msg):
    global log
    log.warning(msg)
  def error(self, msg):
    global log
    log.error(msg)

def my_hook(d):
  global log
  global result_filename
  result_filename=None
  if d['status'] == 'finished':
    log.info('Done downloading, now converting ...')
    result_filename=re.sub('\.[a-zA-Z0-9]*$','.ogg',d["filename"])
    log.info('Converted filename=%s'%result_filename)

def video2ogg(log_system,url):
  global log
  global result_filename
  try:
    log=log_system
    log.debug("=start function=")

    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        #'preferredcodec': 'mp3',
        'preferredcodec': 'vorbis',
        'preferredquality': '64',
      }],
      #'logger': MyLogger(),
      'logger': log,
      'progress_hooks': [my_hook],
      'outtmpl': conf.store_tmp_path+'/'+'%(title)s.%(ext)s'
#      'outtmpl': '%(title)s'
    }
    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
      ydl.download([url])

  except Exception as e:
    log.error(get_exception_traceback_descr(e))
    log.error("unknown youtube_dl error: %s"%str(e))
    return None
  return result_filename


if __name__ == '__main__':
  log= logging.getLogger("youtube_dl_api")
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

  result_filename=video2ogg(log,'https://www.youtube.com/watch?v=BaW_jenozKc')
  if result_filename==None:
    log.error("error call testing function")
  else:
    log.info("success convert. result in file: '%s'"%result_filename)

  log.info("Program exit!")
