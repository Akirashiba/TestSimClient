# -*- coding:utf-8 -*-
from multiprocessing import Process
import datetime
import random
import os
import sys
import time
import django


pathname = (os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, pathname)
sys.path.insert(0, os.path.abspath(os.path.join(pathname, '..')))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "star.settings")

django.setup()
from management.models import Order, GuessSizeSetting, User, Play, \
    MoneyLimit, Cycle                                                # noqa
from services.utils import get_logger, utc_timezone, utc_timestamp, \
    timezone_to_timestamp                                            # noqa


logger = get_logger("SimClient")


class SimClient():

    ActiveStatus = 1                                     # 开启状态
    BlockStatus = 2                                      # 阻塞状态
    UserOrderOType = 1                                   # 缓存单

    SimNameStart = "SimName"                             # 用来识别模拟数据

    SimSettingObject = GuessSizeSetting                  # 模拟客户端的玩法
    SimOrderInterval = 0.5                               # 模拟生成订单的间隔
    SimProtectTime = 10                                  # 模拟Schedule的缓冲时间
    SimAutoStart = 1                                     # 一轮结束自动开始

    SimUserLimit = 1000                                  # 模拟用户总数
    SimUserBasePhone = 13000100860                       # 模拟用户电话号码基数
    SimUserPreAmount = 100000                            # 模拟用户账户初始金额

    SimPlayCode = "guesssize"                            # 模拟玩法名字

    SimMoneyLimits = [10, 25, 50, 100, 200]              # 模拟供选择的下单金额

    SimCycle = 1                                         # 模拟Cycle的计时周期
    SimCycleType = 1                                     # 模拟Cycle的计时类型
    SimCycleSteps = [2, 5, 10]                           # 模拟Cycle供选择的步长
    SimCycleName = "SimCycleRound"                       # 模拟Cycle的name字段开头
    CycleTypeRate = {
        1: lambda x: datetime.timedelta(minutes=x),      # 分钟
        2: lambda x: datetime.timedelta(hours=x),        # 小时
        3: lambda x: datetime.timedelta(days=x),         # 天
    }

    SimMaxPrice = 100                                    # 模拟下单货币对的最大价格

    MarginTypes = [0, 1]                                 # 模拟供选择的MarginType
    MarginRates = [10, 20, 50]                           # 模拟供选择的杠杆率
    ExchangeMarginRate = 20                              # 模拟交易所杠杆率
    Symbols = ["ETH/BTC", "ETH/USDT", "BTC/USDT"]        # 模拟供选择的下单货币对

    def __init__(self):
        if not self.users_exists():
            self.create_users()          # 生成模拟用户
        if not self.play_exists():
            self.create_play()           # 生成玩法(默认为GuessSize)
        if not self.limit_exists():
            self.create_limit()          # 生成供选择的下单金额
        if not self.cycle_exists():
            self.create_cycle()          # 生成供选择的固定时长的cycle

    def create_users(self):
        # 创建模拟用户
        for i in range(self.SimUserLimit):
            phone = str(self.SimUserBasePhone + i)
            username = self.SimNameStart + str(i)
            pin =  phone[-6:]
            sim_user = User.objects.create(
                username=username,
                phone=phone,
                pin=pin,
                amount=self.SimUserPreAmount
            )
            sim_user.save()
        logger.info("{} SimUsers Created".format(self.SimUserLimit))

    def users_exists(self):
        # 是否存在模拟用户
        return User.objects.filter(pin__startswith=self.SimNameStart).exists()

    def get_users(self):
        # 获取所有模拟用户
        return User.objects.filter(pin__startswith=self.SimNameStart)

    def create_play(self):
        # 创建模拟Play
        sim_play = Play.objects.create(
            code=self.SimPlayCode,
            name=self.SimNameStart + self.SimPlayCode
        )
        sim_play.save()
        logger.info("SimPlay(ID={}) Created".format(sim_play.id))

    def play_exists(self):
        # 是否存在模拟Play
        return Play.objects.filter(name__startswith=self.SimNameStart).exists()

    def get_play(self):
        # 获取模拟Play
        return Play.objects.get(
            name__startswith=self.SimNameStart,
            code=self.SimPlayCode
        )

    def create_limit(self):
        # 创建模拟MoneyLimit
        for moneylimit in self.SimMoneyLimits:
            limit_name = self.SimNameStart + str(moneylimit)
            sim_limit = MoneyLimit.objects.create(
                amount=moneylimit,
                name=limit_name
            )
            sim_limit.save()
            logger.info("MoneyLimit(ID={}) Created".format(sim_limit.id))

    def limit_exists(self):
        # 是否存在模拟MoneyLimit
        return MoneyLimit.objects.filter(
            name__startswith=self.SimNameStart
        ).exists()

    def get_limit(self):
        # 获取所有模拟MoneyLimit
        return MoneyLimit.objects.filter(
            name__startswith=self.SimNameStart
        )

    def create_cycle(self):
        # 创建模拟Cycle
        for step in self.SimCycleSteps:
            cycle_name = self.SimNameStart + str(step)
            cycle = Cycle.objects.create(
                name=cycle_name,
                timing_type=self.SimCycleType,
                timing_step=step,
                timimg_cycle=self.SimCycle
            )
            cycle.save()
            logger.info("NewCycle(ID={}) Created".format(cycle.id))

    def cycle_exists(self):
        # 是否存在模拟Cycle
        return Cycle.objects.filter(
            name__startswith=self.SimNameStart
        ).exists()

    def get_cycle(self):
        # 获取所有模拟Cycle
        return Cycle.objects.filter(name__startswith=self.SimNameStart)

    def random_cycle(self):
        # 随机获取模拟Cycle
        return random.choice(list(self.get_cycle()))

    def create_order(self, user_id, expired_time):
        # 模拟用户创建模拟订单
        serial_id = timezone_to_timestamp(expired_time)
        if Order.objects.filter(user_id=user_id, serial_id=serial_id).exists():
            logger.info("User Order Repeated In The Same Schedule")
            return False

        play = self.get_play()
        symbol = self.random_symbol()
        base, quote = symbol.split("/")
        fiat_rate = self.get_fiat_rate()
        amount = self.random_amount()
        amount_fiat = float(amount) * fiat_rate

        date_time = utc_timezone()
        exchange_margin_rate = self.get_exchange_rate()
        close_est_price = self.get_close_est_price()
        price = self.get_price(symbol, utc_timestamp())

        new_order = Order.objects.create(
            user_id=user_id,
            play_id=play.id,
            serial_id=serial_id,
            otype=self.UserOrderOType,
            margin_type=self.random_type(),
            margin_rate=self.random_rate(),
            amount=amount,
            amount_fiat=amount_fiat,
            coin_code=base,
            quote_code=quote,
            price=price,
            close_est_price=close_est_price,
            close_est_time=expired_time,
            exchange_margin_rate=exchange_margin_rate,
            user_create_time=date_time,
        )
        new_order.save()
        logger.info("NewOrder(ID={}) Created".format(new_order.id))

        return False

    def create_schedule(self):
        # 创建模拟Schedule
        cycle = self.random_cycle()
        cycle_span = self.CycleTypeRate[cycle.timimg_cycle](cycle.timing_step)
        last_expired = self.get_last_expired()
        expired_time = last_expired + cycle_span
        moneylimit = self.get_limit()
        schedule_name = self.SimNameStart + str(cycle.id)
        schedule = self.SimSettingObject.objects.create(
            name=schedule_name,
            expired_time=expired_time,
            protect_time=self.SimProtectTime,
            auto_start=self.SimAutoStart,
            cycle_id=cycle.id,
            reward=0,
            margin_type=1,
        )
        schedule.moneyLimits.add(*[ml for ml in list(moneylimit)])
        schedule.save()
        logger.info("NewSchedule(ID={}) Created".format(schedule.id))

        return schedule

    def get_exchange_rate(self):
        # TODO
        return self.ExchangeMarginRate

    def get_close_est_price(self):
        # TODO
        return 1

    def get_fiat_rate(self):
        # TODO
        return 1

    def get_price(self, symbol, timestamp):
        # TODO
        return "%.2f" % (self.SimMaxPrice * random.random())

    def get_last_expired(self):
        # 获取上一轮的截止时间
        schedules = self.SimSettingObject.objects.filter(
            status=self.BlockStatus).order_by("-expired_time")
        if schedules:
            return schedules[0].expired_time
        else:
            return utc_timezone()

    def random_amount(self):
        # 随机下单金额
        return random.choice(self.SimMoneyLimits)

    def random_type(self):
        # 随机下单MarginType
        return random.choice(self.MarginTypes)

    def random_rate(self):
        # 随机杠杆率
        return random.choice(self.MarginRates)

    def random_symbol(self):
        # 随机下单货币对
        return random.choice(self.Symbols)


class SimOrderWorker(SimClient, Process):

    def __init__(self, expired):
        super().__init__()
        super(SimClient, self).__init__()
        self.expired = expired

    def run(self):
        users = list(self.get_users())
        while True:
            if self.expired["value"]:
                user = random.choice(users)
                expired_time = self.expired["value"]
                self.create_order(user.id, expired_time)
                time.sleep(self.SimOrderInterval)
            else:
                time.sleep(1)


class SimScheduleWorker(SimClient, Process):

    def __init__(self, sendpipe, recvpipe, expired):
        super().__init__()
        super(SimClient, self).__init__()
        self.sendpipe = sendpipe
        self.recvpipe = recvpipe
        self.expired = expired

    def run(self):
        schedule = self.create_schedule()
        self.sendpipe.send(schedule.id)
        self.expired["value"] = schedule.expired_time
        while True:
            self.recvpipe.recv()
            schedule = self.create_schedule()
            self.sendpipe.send(schedule.id)
            self.expired["value"] = schedule.expired_time


if __name__ == "__main__":
    sss = GuessSizeSetting.objects.all()
    for ss in sss:
        print(timezone_to_timestamp(ss.expired_time))
