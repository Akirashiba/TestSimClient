# -*- coding:utf-8 -*-
from collections import defaultdict
from multiprocessing import Process
from django_redis import get_redis_connection
from websocket import create_connection
from django.db import transaction
from functools import wraps
import os
import sys
import time
import datetime
import django
import random
import requests
import json


pathname = (os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, pathname)
sys.path.insert(0, os.path.abspath(os.path.join(pathname, '..')))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "star.settings")

django.setup()
from management.models import Order, User                            # noqa
from services.utils import get_logger, utc_timestamp, \
    timezone_to_timestamp, utc_timezone                              # noqa
from star.celery import app                                          # noqa
from django.conf import settings                                     # noqa
from services.apiconfig import ApiManager                            # noqa


logger = get_logger("OrderRunner")
schedule_logger = get_logger("ScheduleRunner")


def func_timer(function):
    @wraps(function)
    def function_timer(*args, **kwargs):
        logger.info('[Function: {name} start...]'.format(name=function.__name__))
        t0 = time.time()
        result = function(*args, **kwargs)
        t1 = time.time()
        logger.info('[Function: {name} finished, spent time: {time:.2f}s]'.format(name=function.__name__, time=t1 - t0))
        return result
    return function_timer


class OrderRunner:

    def __init__(self, order_id=None):

        for key, value in ApiManager.items():
            setattr(self, key, value)

        self.order_id = order_id

        self.sr = get_redis_connection("default")
        self.token = self.sr.get(self.tokenKey)
        if not self.token:
            self.login()

        self.init_web_socket()

    @func_timer
    def login(self):
        requestInfo = self.requestInfo["user_login"]
        login_data = {
            "login_token": self.AgentLoginToken,
            "password": self.AgentPassWord
        }
        login_url = self.baseUrl + requestInfo["endpoint"]
        request_method = getattr(requests, requestInfo["method"].lower())
        response = request_method(login_url, data=login_data)
        response = json.loads(response.text)
        self.sr.set(self.tokenKey, response["token"])
        self.token = response["token"]

    @func_timer
    def init_web_socket(self, retry=0):
        if retry > 1:
            raise Exception("Fail To Init WebSocket")
        self.ws = create_connection(
            "ws://{}/ws?user_id={}&group_name=user&token={}"
            "".format(settings.WEBSOCKETHOST, self.Recommended, self.token),
        )
        if not self.ws.connected:
            self.login()
            self.init_web_socket(retry + 1)

    @func_timer
    def order_init(self, order_id):
        try:
            if isinstance(order_id, (str, int)):
                self.order = Order.objects.get(id=order_id)
            else:
                self.order = order_id
        except Exception:
            logger.error("Order[ID={}] Not Found".format(order_id))
            raise Exception("Order[ID={}] Not Found".format(order_id))

    @func_timer
    def win_or_lose(self):
        upordown = float(self.closed_price) < float(self.order.price)
        return upordown ^ self.order.margin_type

    @func_timer
    def settlements(self, order_id):
        # 用户订单奖励清算
        self.order_init(order_id)
        reward = self.figure_out_reward()

        self.order.close_act_price = self.closed_price
        self.order.close_act_time = utc_timezone()
        self.order.profit = reward

        self.user_gain_reward(reward)
        self.result_feedback()
        self.close()

    @func_timer
    @transaction.atomic
    def user_gain_reward(self, reward):
        user = User.objects.select_for_update().get(id=self.order.user_id)
        if self.win_or_lose():
            total_reward = float(self.order.amount) + float(reward)
            user.amount = float(user.amount) + total_reward
            user.save()

        logger_params = {
            "username": user.username,
            "gainorlose": "Gain" if self.win_or_lose() else "Lose",
            "reward": reward if self.win_or_lose() else self.order.amount,
            "coin": self.rewardCoin,
        }

        logger.info(
            "User {username} {gainorlose} {reward} {coin} "
            "".format(**logger_params)
        )

    @func_timer
    def figure_out_reward(self):
        if not self.win_or_lose():
            return -self.order.amount
        else:
            return self.order.amount * (float(self.order.margin_rate) / 100)

    @func_timer
    def current_price(self):
        key = "PRICE_" + self.Symbol.replace("/", "_").upper()
        return self.sr.hget(key, "price")

    @func_timer
    def result_feedback(self):
        feedback_msg = {
            "win_or_lose": "win" if self.win_or_lose() else "lose",
            "profit": self.order.profit,
            "user_id": self.order.user_id,
            "order_id": self.order.id,
        }
        send_params = {
            "message_type": "notification",
            "send_type": "private",
            "message": "system",
            "args": {
                "send_user_id": self.order.user_id,
                "send_group_name": "user",
                "title": "order_result",
                "content": feedback_msg,
            }
        }
        self.ws.send(json.dumps(send_params))

    def run(self):
        self.closed_price = float(self.current_price())
        self.settlements(self.order_id)
        self.ws.close()

    @func_timer
    def close(self):
        # 关闭Order
        self.order.status = 3
        self.order.save()
        logger.info("Order[ID: {}] Closed".format(self.order.id))


class ScheduleRunner(OrderRunner):

    expiredTimeLimit = datetime.timedelta(minutes=10)

    def __init__(self):

        super(ScheduleRunner, self).__init__()
        self.closed_price = self.current_price()
        self.serial_time = datetime.datetime.utcnow()
        self.expired_time = self.serial_time - self.expiredTimeLimit
        self.serial_id = self.serial_time.strftime("%Y%m%d%H%M")
        self.expired_info = {
            "normal": self.expired_time.strftime("%Y%m%d%H%M%S"),
            "schedule": self.expired_time.strftime("%Y%m%d%H%M")
        }

    def run(self):
        try:
            schedule_logger.info("Schedule[SerialId={}] Start".format(self.serial_id))
            orders = Order.objects.filter(serial_id=self.serial_id)
            schedule_logger.info("{} Orders Found In Schedule".format(len(orders)))
            for order in orders:
                schedule_logger.info("Order[ID={}] Start".format(order.id))
                self.settlements(order)
                schedule_logger.info("Order[ID={}] Finished".format(order.id))
            self.ws.close()

            for play_code, expired_id in self.expired_info.items():
                expired_orders = Order.objects.filter(serial_id__lte=expired_id, play_code=play_code, status=1)
                for order in expired_orders:
                    schedule_logger.info("ExpiredOrder[ID={} PlayCode={}] Start".format(order.id, order.play_code))
                    self.expired_feedback(order)
                    schedule_logger.info("ExpiredOrder[ID={} PlayCode={}] Finished".format(order.id, order.play_code))

        except Exception as e:
            schedule_logger.error(e)

    @transaction.atomic
    def expired_feedback(self, order):
        user = User.objects.select_for_update().get(id=order.user_id)
        user.amount = float(user.amount) + float(order.amount)
        user.save()

        logger_params = {
            "amount": order.amount,
            "username": user.username,
            "order_id": order.id,
            "coin": self.rewardCoin,
        }

        logger.info(
            "Return {amount} {coin} To User {username} "
            "Due To ExpiredOrder[ID={order_id}]".format(**logger_params)
        )


@app.task
def order_settlement(order_id):
    order_runner = OrderRunner(order_id)
    order_runner.run()


@app.task
def schedule_settlement():
    schedule_runner = ScheduleRunner()
    schedule_runner.run()


if __name__ == "__main__":
    pass
