# -*- coding:utf-8 -*-
import os
import sys
import time
from datetime import datetime
from datetime import timedelta
import logging
import logging.config
from slacker import Slacker

logger = logging.getLogger(__name__)
LOG_FILE_NAME = "log.txt"


class SlackLogGetter(object):
    def __init__(self, token):
        self.__client = Slacker(token)
        self.__channels = self.__get_channels()
        self.__users = self.__get_users()

    def __get_channels(self):
        channels = []
        rsp = self.__client.channels.list().body
        if self.__check_response(rsp):
            channels = dict((chan['id'], chan) for chan in rsp['channels'])
        return channels

    def __get_users(self):
        users = None
        rsp = self.__client.users.list().body
        if self.__check_response(rsp):
            users = dict((user['id'], user) for user in rsp['members'])
        return users

    @staticmethod
    def __check_response(data):
        if isinstance(data, dict):
            if "ok" in data:
                if data["ok"] is True:
                    return True
                else:
                    logger.debug(data["ok"])
        return False

    def __find_user_by_name(self, user_name):
        for user_id, user in self.__users.items():
            if user['name'] == user_name:
                return user
        raise Exception("User name:{} is not exists".format(user_name))

    def __find_user_by_id(self, user_id):
        for key, user in self.__users.items():
            if key == user_id:
                return user
        raise Exception("User id:{} is not exists".format(user_id))

    def __find_channel_by_name(self, room_name):
        for channel_id, channel in self.__channels.items():
            if channel['name'] == room_name:
                return channel
        raise Exception("Channel name:{} is not exists".format(room_name))

    def __send_dm(self, to_user_id, text):
        # open a direct message channel to user
        rsp = self.__client.im.open(to_user_id).body
        if self.__check_response(rsp):
            send_im_channel = rsp['channel']['id']
            
            with open(LOG_FILE_NAME, "w", encoding="utf-8") as f:
                f.write(text)
            self.__upload_file(os.path.abspath(LOG_FILE_NAME), LOG_FILE_NAME, "log",send_im_channel)
            os.remove(LOG_FILE_NAME)

    def __send_message(self, channel, text, as_user=True, attachments=None):
        rsp = self.__client.chat.post_message(channel=channel,
                                             text=text,
                                             as_user=as_user,
                                             attachments=attachments).body
        return self.__check_response(rsp)

    def __get_history(self, channel_id, oldest=0, latest=None, count=1000):
        rsp = self.__client.channels.history(channel=channel_id,
                                             count=count,
                                             oldest=oldest,
                                             latest=latest).body
        if self.__check_response(rsp):
            return rsp

    def __upload_file(self, filepath, filename, title, channels=None):
        # channels:Comma-separated list of channel names or IDs
        rsp = self.__client.files.upload(filepath,
                                         filename=filename,
                                         title=title,
                                         channels=channels).body
        return self.__check_response(rsp)

    def __make_log_text(self, channel_id, days_before):
        today = datetime.now()
        oldest = datetime(today.year, 
                          today.month, 
                          today.day,
                          0,0,0,0) - timedelta(days=days_before)
        oldest = time.mktime(oldest.timetuple())
        msg = ""
        readingflg = True
        while readingflg:
            data = self.__get_history(channel_id, oldest=oldest, count=1000)
            if len(data['messages']) == 1000:
                oldest = data['messages'][0]['ts']
            else:
                readingflg = False 

            # TODO 読みやすさ重視したけどjsonそのまま突っ込んだほうがいいかも
            for m in reversed(data['messages']):
                if m['type'] == "message":
                    name = 'no name'
                    try:
                        name = self.__find_user_by_id(m['user'])['name']
                    except (KeyError, TypeError):
                        if 'username' in m:
                            # 'bot_message'
                            name = m['username']
                        else:
                            continue
                    ts = datetime.fromtimestamp(float(m['ts']))
                    text = m['text']
                    # TODO:attachments pending 
                    #attachments = m['attachments']
                    msg += "\n{0}:{1}\n{2}\n".format(name, ts, text)
        return msg

    def send_dm_slack_logfile(self, channel_name, days_before,send_user_name):
        target_channel = self.__find_channel_by_name(channel_name)           
        msg = self.__make_log_text(target_channel['id'], days_before)
        if len(msg) > 0:
            send_user = self.__find_user_by_name(send_user_name)
            if not send_user or send_user['deleted']:
                raise Exception("Error:user {} is not exists.".format(send_user_name))
            self.__send_dm(send_user['id'], msg)
        else:
            logger.info("channel:#{} don't have log.".format(channel_name))

    def get_slack_logfile(self,channel_name, days_before):
        target_channel = self.__find_channel_by_name(channel_name)           
        msg = self.__make_log_text(target_channel['id'], days_before)
        if len(msg) > 0:
            with open(LOG_FILE_NAME, "w", encoding="utf-8") as f:
                f.write(msg)
        else:
            logger.info("channel:#{} don't have log.".format(channel_name))


if __name__ == "__main__":
    kw = {
        'format': '[%(asctime)s] %(message)s',
        'datefmt': '%m/%d/%Y %H:%M:%S',
        'level': logging.DEBUG,
        'stream': sys.stdout,
    }
    logging.basicConfig(**kw)
    logging.getLogger('requests.packages.urllib3.connectionpool').setLevel(logging.WARNING)

    import settings
    token         = settings.SLACK_TOKEN
    channels_name  = settings.CHANNELS_NAME
    days_before   = settings.DAYS_BEFORE
    send_user   = settings.SEND_DM_USER_NAME

    sh = SlackLogGetter(token)

    # ローカルにログファイルを作る
    for channel_name in channels_name:
        LOG_FILE_NAME = channel_name + ".log"
        sh.get_slack_logfile(channel_name, days_before) 

    # DMにログファイルを送る
    #sh.send_dm_slack_logfile(channel_name, days_before, send_user)