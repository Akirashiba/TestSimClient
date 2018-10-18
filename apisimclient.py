# -*- coding:utf-8 -*-
from multiprocessing import Process
from websocket import create_connection
from django_redis import get_redis_connection
import certifi
import ssl
import aiohttp
import asyncio
import json
import math
import os
import sys
import random
import traceback
import time
import django
import datetime
import re


pathname = (os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, pathname)
sys.path.insert(0, os.path.abspath(os.path.join(pathname, '..')))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "star.settings")

django.setup()
from services.utils import get_logger, utc_timezone, utc_timestamp, \
    timezone_to_timestamp                                            # noqa
from services.apiconfig import ApiManager                            # noqa
from services.simclient import SimClient                             # noqa
from django.conf import settings                                     # noqa


logger = get_logger("ApiSimClient")


class ApiSimClient(SimClient):
    """docstring for OrderCreater"""

    clientId = 3
    SampleCapacity = 100
    orderLoggerKeys = ["Play_Code", "Amount", "Price", "User", "Margin_Rate"]
    symbol = "BTC/USDT"

    timeout = 60000
    rateLimit = 50
    rateLimitMaxTokens = 50 
    rateLimitTokens = 50
    rateLimitUpdateTime = time.monotonic()

    def __init__(self, enableRateLimit):
        self.enableRateLimit = enableRateLimit

        for key, value in ApiManager.items():
            setattr(self, key, value)

        self.asyncio_loop = asyncio.get_event_loop()
        self.session = aiohttp.ClientSession()

        self.sr = get_redis_connection("default")

        self.get_users_info()
        self.get_user_names()

        self.ws_group = {}

    def __del__(self):
        if self.session is not None:
            self.asyncio_loop.run_until_complete(self.session.close())

    def init_web_socket(self, user_id, token):
        headers = self.headers.copy()
        self.ws_group[user_id] = create_connection(
            "ws://{}/ws?user_id={}&group_name=user&token={}"
            "".format(settings.WEBSOCKETHOST, user_id, token),
            headers=headers
        )

    def current_ticker(self, user_id):
        ws = self.ws_group[user_id]
        ws_msg = {
            "message_type": "query",
            "message": "current_ticker",
            "send_type": "private",
            "args": {
                    "send_user_id": user_id,
                    "send_group_name": "user",
                    "coinpair": "BTC/USDT"
                }
        }
        ws.send(json.dumps(ws_msg))
        return eval(ws.recv())

    async def close(self):
        if self.session is not None:
            if self.own_session:
                await self.session.close()
            self.session = None

    async def wait_for_token(self):
        while self.rateLimitTokens <= 1:
            self.add_new_tokens()
            #seconds_delays = [0.001, 0.005, 0.022, 0.106, 0.5]
            seconds_delays = [0.001]
            delay = random.choice(seconds_delays)
            await asyncio.sleep(delay)
        self.rateLimitTokens -= 1

    def add_new_tokens(self):
        now = time.monotonic()
        time_since_update = now - self.rateLimitUpdateTime
        new_tokens = math.floor(
            (0.8 * 1000.0 * time_since_update) / self.rateLimit
        )
        if new_tokens > 1:
            self.rateLimitTokens = min(
                self.rateLimitTokens + new_tokens,
                self.rateLimitMaxTokens
            )
            self.rateLimitUpdateTime = now

    def get_user_names(self):
        self.usernames = []
        for i in range(self.SimUserLimit):
            self.usernames.append(self.SimNameStart + str(i))

    def get_users_info(self):
        self.user_info = self.sr.hget("LocalSimClient", "UserInfo")
        if self.user_info:
            self.user_info = eval(self.sr.hget("LocalSimClient", "UserInfo"))
        else:
            asyncio.get_event_loop().run_until_complete(self.create_users())

    def save_users_info(self):
        self.sr.hset("LocalSimClient", "UserInfo", self.user_info)

    def play_select_by_name(self, name):
        for play_info in self.play_list:
            if play_info["name"] == name:
                self.money_limits = play_info["moneyLimits"]
                self.play_id = int(play_info["id"])
                self.play_code = play_info["play_type"]
                self.expired_time = play_info["expired_time"]
                self.margin_rate = play_info["margin_rate"]
                self.protect_time = play_info["protect_time"]
                self.cycle_timing_cycle = int(play_info["cycle_timing_cycle"])
                self.cycle_timing_step = int(play_info["cycle_timing_step"])


    async def play_list(self):
        requestInfo = self.requestInfo["play_list"]
        username = random.choice(self.usernames)
        if 'token' not in self.user_info[username]:
            password = self.user_info[username]["password"]
            await self.user_login(username, password)

        request_params = {}
        request_params['url'] = self.baseUrl + requestInfo["endpoint"]
        request_params['method'] = requestInfo["method"]
        request_params["data"] = {
            "status": 1,
            "limit": 20,
            "page": 1,
        }
        request_params["Authorization"] = self.user_info[username]['token']

        response = await self.fetch(request_params)
        if isinstance(response, dict):
            self.play_list = response["results"]
        else:
            logger.error("Get Play List Fail: {} ".format(response))

    async def play_detail(self, play_id):
        requestInfo = self.requestInfo["play_detail"]
        username = random.choice(self.usernames)
        if 'token' not in self.user_info[username]:
            password = self.user_info[username]["password"]
            await self.user_login(username, password)

        request_params = {}
        request_params['url'] = self.baseUrl + requestInfo["endpoint"]
        request_params['method'] = requestInfo["method"]
        request_params["data"] = {
            "play_id": play_id,
        }
        request_params["Authorization"] = self.user_info[username]['token']

        response = await self.fetch(request_params)
        if isinstance(response, dict):
            self.money_limits = response["moneyLimits"]
            self.play_id = play_id
            self.play_code = response["play_type"]
            self.expired_time = response["expired_time"]
            self.margin_rate = response["margin_rate"]
            self.protect_time = response["protect_time"]
            self.cycle_timing_cycle = int(response["cycle_timing_cycle"])
            self.cycle_timing_step = int(response["cycle_timing_step"])
        else:
            logger.error(
                "Get Play ID:{} Detail Fail: {} ".format(play_id, response)
            )

    async def user_login(self, username, password):
        requestInfo = self.requestInfo["user_login"]

        request_params = {}
        request_params['url'] = self.baseUrl + requestInfo["endpoint"]
        request_params['method'] = requestInfo["method"]
        request_params["data"] = {}

        if username == self.AgentLoginToken:
            login_token = self.AgentLoginToken
            password = self.AgentPassWord
            client_id = 2
        else:
            login_token = self.user_info[username]["login_token"]
            password = self.user_info[username]["password"]
            client_id = 3

        request_params["data"]["client_id"] = client_id
        request_params["data"]["login_token"] = login_token
        request_params["data"]["password"] = password

        response = await self.fetch(request_params)
        if isinstance(response, dict):
            if username == self.AgentLoginToken:
                self.AgentToken = response["token"]
            else:
                self.user_info[username]["token"] = response["token"]
                self.user_info[username]["user_id"] = int(response["user_id"])
                self.user_info[username]["user_level"] = response["user_level"]
                self.save_users_info()
        else:
            raise Exception("User Login Fail: {} ".format(response))
            logger.error("User Login Fail: {} ".format(response))

    async def create_users(self):
        requestInfo = self.requestInfo["create_user"]

        if not hasattr(self, 'AgentToken'):
            response = await self.user_login(self.AgentLoginToken, self.AgentPassWord)
            if not hasattr(self, 'AgentToken'):
                raise Exception("Agent Login Error")

        for i in range(self.SimUserLimit):
            request_params = {}
            request_params['url'] = self.baseUrl + requestInfo["endpoint"]
            request_params['method'] = requestInfo["method"]
            request_params["token"] = self.AgentToken

            username = self.SimNameStart + str(i)  
            phone = str(self.SimUserBasePhone + i)
            request_params["data"] = {
                "username": username,
                "password": username,
                "recommended": self.Recommended,
                "pin": phone[-6:],
                "amount": self.SimUserPreAmount,
                "country": 1,
                "user_level_id": 1,
            }

            response = await self.fetch(request_params)
            if isinstance(response, dict):
                self.user_info[username] = {}
                self.user_info[username]["login_token"] = response["login_token"]
                self.user_info[username]["password"] = response["password"]
                self.user_info[username]["token"] = None
            else:
                logger.error("Create {} Fail: {} ".format(username, response))
        logger.info("{} Users Have Been Created".format(len(self.user_info)))
        self.save_users_info()

    async def create_order(self, user_name):
        # 模拟用户创建模拟订单
        requestInfo = self.requestInfo["create_order"]
        if "token" not in self.user_info[user_name] or not self.user_info[user_name]['token']:
            password = self.user_info[user_name]["password"]
            await self.user_login(user_name, password)

        user_id = self.user_info[user_name]['user_id']
        token = self.user_info[user_name]['token']
        if user_id not in self.ws_group:
            self.init_web_socket(user_id, token)
        symbol = self.symbol
        ticker = self.current_ticker(user_id)
        
        create_time = datetime.datetime.now()
        serial_id = re.sub('[\s\-:\.]', '', str(datetime.datetime.utcnow()))[:12]
        serial_id = int(serial_id) + int(self.cycle_timing_step)
        life_cycle = self.CycleTypeRate[self.cycle_timing_cycle]
        close_est_time = create_time + life_cycle(self.cycle_timing_step)
        request_params = {}
        request_params['url'] = self.baseUrl + requestInfo["endpoint"]
        request_params['method'] = requestInfo["method"]
        request_params['Authorization'] = token
        request_params["data"] = {
            'user': user_id,
            'serial_id': serial_id,
            'schedule_id': self.play_id,
            'play_code': self.play_code,
            'play': 1,
            'margin_type': self.random_type(),
            'margin_rate': self.margin_rate,
            'amount': random.choice(self.money_limits),
            'coinpair': symbol,
            'price': ticker["price"],
            'user_create_time': str(create_time)[:19],
            'close_est_time': str(close_est_time)[:19],
        }
        
        logger.info("Start Sending Create Order Requests")
        response = await self.fetch(request_params)
        if isinstance(response, dict):
            eq_format = lambda x: x + "=" + str(response[x.lower()])
            order_info = [eq_format(key) for key in self.orderLoggerKeys]
            logger.info("NewOrder({}) Created".format(", ".join(order_info)))
        else:
            if "token" in response:
                logger.error("{} Token Expired".format(user_name))
                self.user_info[user_name]['token'] = None
                await self.create_order(user_name)
            else:
                logger.error(
                    "{} Create Order Fail: {} ".format(user_name, response)
                )

        return False

    async def fetch(self, request_params):
        try:
            if self.enableRateLimit:
                await self.wait_for_token()
            method = request_params.pop("method")
            session_method = getattr(self.session, method.lower())
            request_params["timeout"] = self.timeout / 1000
            request_params["headers"] = self.headers.copy()
            if "token" in request_params:
                request_params["headers"]["token"] = request_params.pop("token")
            if "Authorization" in request_params:
                request_params["headers"]["Authorization"] = "Galaxy " + request_params.pop("Authorization")
            
            async with await session_method(**request_params) as response:
                text = await response.text()
                print(text)
                if response.status == 200:
                    res = json.loads(text)
                    if res["code"] in self.errorCodes:
                        if "context" in res:
                            return res["context"]
                        else:
                            return res["detail"]
                    else:
                        return res
                else:
                    return "Status[{}] 错误".format(response.status)

        except asyncio.TimeoutError:
            return "请求超时"

        except Exception as e:
            traceback.print_exc()
            return "未知异常: {}".format(str(e))


class SimOrderApiWorder(ApiSimClient):
    def __init__(self, enableRateLimit):
        super().__init__(enableRateLimit)

    def run(self):
        asyncio.get_event_loop().run_until_complete(self.play_list())
        self.play_select_by_name("sch_guess1")
        # asyncio.get_event_loop().run_until_complete(self.play_detail(play_id))
        while True:
            tasks = []
            usernames = random.sample(self.usernames, self.SampleCapacity)
            for username in usernames:
                task = asyncio.ensure_future(self.create_order(username))
                tasks.append(task)
            asyncio.get_event_loop().run_until_complete(asyncio.wait(tasks))
            time.sleep(self.SimOrderInterval)
            break


if __name__ == "__main__":
    ss = SimOrderApiWorder(False)
    ss.run()