# -*- coding:utf-8 -*-

ApiManager = {
    "AgentLoginToken": "AgentLoginToken",
    "AgentPassWord": "AgentPassWord",
    "Recommended": 6,
    # "baseUrl": "http://198.2.196.225:80/",
    "baseUrl": "http://127.0.0.1:8000/",
    "SymbolSample": {
        "BTC": ["BTC/USDT", "BTC/USD", "BTC/ETH"]
    },
    "Symbol": "BTC/USDT",
    "tokenKey": "runnertoken",
    "rewardCoin": "Coin",

    "errorCodes": {
        400: "参数错误",
        401: "token错误",
        402: "用户名已存在",
        404: "资源不存在",
        406: "不允许下单",
        407: "余额不足",
        500: "未知错误",
    },

    "requestInfo": {
        "user_login": {
            "endpoint": "api/v1/user/scan-login/",
            "method": "post"
        },
        "create_user": {
            "endpoint": "api/v1/agent/register/",
            "method": "post",
        },
        "create_order": {
            "endpoint": "api/v1/order/new/",
            "method": "post",
        },
        "play_list": {
            "endpoint": "api/v1/play/all/",
            "method": "post",
        },
        "play_detail": {
            "endpoint": "api/v1/play/content/",
            "method": "post",
        }
    },

    "headers": {
        'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.71 Safari/537.36'
    }
}