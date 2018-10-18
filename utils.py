# -*- coding:utf-8 -*-
from asyncio import Queue, sleep, Future, ensure_future, get_event_loop
import datetime
import time
import os
import sys
import logging
import pytz

tz = pytz.timezone("Asia/Shanghai")


def get_logger(splider_name):
    logger = logging.getLogger()
    pathname = (os.path.dirname(os.path.abspath(__file__)))
    if not logger.handlers:
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)-8s]: %(message)s'
        )

        file_handler = logging.FileHandler(
            os.path.join(pathname, "logs/%s.log" % (splider_name))
        )
        file_handler.setFormatter(formatter)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.formatter = formatter

        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        logger.setLevel(logging.INFO)
    return logger


def utc_timezone():
    return datetime.datetime.now(pytz.utc)


def utc_timestamp():
    return timezone_to_timestamp(utc_timezone())


def timezone_to_timestamp(timezone):
    tz_str = str(timezone)[:19]
    return time.mktime(time.strptime(tz_str, '%Y-%m-%d %H:%M:%S'))


def timestamp_to_timezone(timestamp):
    dt = datetime.datetime.fromtimestamp(timestamp)
    return pytz.utc.localize(dt)


if __name__ == "__main__":
    pass
