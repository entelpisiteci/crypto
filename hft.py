import json
import requests
import websocket as wb
import helper_functions as fk
import numpy as np
import pandas as pd
import math
import datetime
import time

API_KEY = "<API_KEY>"
API_SECRET = "<API_SECRET"

url = 'https://api.binance.com/api/v1/userDataStream'
LISTEN_KEY = requests.post(url, headers={'X-MBX-APIKEY': API_KEY})
LISTEN_KEY = LISTEN_KEY.content.decode("utf-8").split('"')[3]

BINANCE_SOCKET = "wss://stream.binance.com:9443/stream?streams=btcfdusd@kline_1s/btcfdusd@depth20@100ms/" + LISTEN_KEY

price = .0
FREE_BTC = .0
FREE_FDUSD = .0
ALIS_VERILEBILIR = True
ORDER_LIST = {}
BASLANGIC_ZAMANI = time.time()

exchangeInfos, totalWeightUsed = fk.getExchangeSymbols()

rateLimits = pd.DataFrame(exchangeInfos["rateLimits"])
exchangeSymbols = pd.DataFrame(exchangeInfos["symbols"])
exchangeSymbolsFilters = pd.DataFrame(exchangeSymbols["filters"].iloc[0])

filters = pd.DataFrame(exchangeSymbols[(exchangeSymbols["symbol"] == "BTCFDUSD")]["filters"].iloc[0])
priceFilter = int(-1 * math.log10(float(filters[filters["filterType"] == "PRICE_FILTER"]["tickSize"].iloc[0])))
lotSize = int(-1 * math.log10(float(filters[filters["filterType"] == "LOT_SIZE"]["stepSize"].iloc[0])))


result, global_asks, global_bids, totalWeightUsed = fk.getOrderDepths(fk.parametreler.IZLENEN_CIFT, fk.parametreler.ALIM_SATIM_MAX_DERINLIK)
global_asks = np.asarray(global_asks, dtype=np.double)
global_bids = np.asarray(global_bids, dtype=np.double)
global_max_ask = np.max(global_asks[:, 0])
global_min_bid = np.min(global_bids[:, 0])

wallet, totalWeightUsed = fk.getWallet()
wallet = pd.DataFrame(wallet)
print(wallet.to_string().replace("\n", "\n\t"))

FREE_FDUSD = float(wallet["FDUSD"]["free"])
FREE_BTC = float(wallet["BTC"]["free"])
START_TIME = time.time()

def on_open(ws):
    global FREE_BTC
    global FREE_FDUSD
    global START_TIME
    try:
        fk.cancelAllOrders("BTCFDUSD")
    except Exception as hata:
        print(hata)
    try:
        fk.putOrder(symbol="BTCFDUSD", side="SELL", orderType="MARKET", timeInForce="GTC",
                    quantity=FREE_BTC, price=80000, priceFilter=priceFilter, lotSize=lotSize)
    except Exception as hata:
        print(hata)
    wallet, totalWeightUsed = fk.getWallet()
    wallet = pd.DataFrame(wallet)
    print(wallet.to_string().replace("\n", "\n\t"))

    FREE_FDUSD = float(wallet["FDUSD"]["free"])
    FREE_BTC = float(wallet["BTC"]["free"])
    START_TIME = time.time()


def on_close(ws):
    print("closed connection")


def on_error(ws, error):
    print(error)


def on_message(ws, message):
    global global_asks
    global global_bids
    global global_max_ask
    global global_min_bid
    global price
    global FREE_BTC
    global FREE_FDUSD
    global ALIS_VERILEBILIR
    global ORDER_LIST
    global START_TIME

    if len(ORDER_LIST) > 0:
        now_time = datetime.datetime.now()
        for key, value in ORDER_LIST.items():
            time_diff = (now_time - value["time"]).seconds
            if time_diff > 5:
                cancelOrderResult, totalWeightUsed = fk.cancelOrder(
                    symbol="BTCFDUSD", orderId=value["orderId"], origClientOrderId=value["clientOrderId"])
                print("CANCEL ORDER RESULT:" + cancelOrderResult)
                ORDER_LIST.pop(key)
    now_time = time.time()
    if (now_time - START_TIME) > 180:
        START_TIME = time.time()
        openOrders, totalWeightUsed = fk.getOpenOrders()
        openOrders = pd.DataFrame(openOrders)
        openOrders = pd.DataFrame(openOrders)
        openOrders = openOrders[openOrders["side"] == "SELL"]
        if len(openOrders) > 0:
            openOrders.reset_index(inplace=True, drop=True)
            if (now_time * 1000 - openOrders["updateTime"].min())/60000 > 3:
                try:
                    fk.cancelAllOrders("BTCFDUSD")
                except Exception as hata:
                    print(hata)
                wallet, totalWeightUsed = fk.getWallet()
                wallet = pd.DataFrame(wallet)
                FREE_FDUSD = float(wallet["FDUSD"]["free"])
                FREE_BTC = float(wallet["BTC"]["free"])

                try:
                    fk.putOrder(symbol="BTCFDUSD", side="SELL", orderType="MARKET", timeInForce="GTC",
                                quantity=FREE_BTC, price=80000,
                                priceFilter=priceFilter, lotSize=lotSize)
                except Exception as hata:
                    print(hata)

                wallet, totalWeightUsed = fk.getWallet()
                wallet = pd.DataFrame(wallet)

                FREE_FDUSD = float(wallet["FDUSD"]["free"])
                FREE_BTC = float(wallet["BTC"]["free"])

    message = json.loads(message)
    stream = message["stream"]
    if LISTEN_KEY in stream:
        message = message["data"]
        eventType = message[fk.parametreler.ws_event_type]
        match eventType:
            case "outboundAccountPosition":
                eventTime = message[fk.parametreler.ws_event_time]
                message = message[fk.parametreler.ws_balancesArray]
                for m in message:
                    asset = m[fk.parametreler.ws_asset]
                    free = m[fk.parametreler.ws_free]
                    locked = m[fk.parametreler.ws_lock]
                    if asset == "BTC":
                        FREE_BTC = float(free)
                    elif asset == "FDUSD":
                        FREE_FDUSD = float(free)
            case "executionReport":
                side = message[fk.parametreler.ws_side]
                symbol = message[fk.parametreler.ws_symbol]
                currentStatus = message[fk.parametreler.ws_status]
                orderId = message[fk.parametreler.ws_orderId]
                orderPrice = message[fk.parametreler.ws_orderPrice]
                cumulativeFilledQuantity = message[fk.parametreler.ws_cumulativeFilledQuantity]
                transactionTime = message[fk.parametreler.ws_transactionTime]
                orderCreationTime = message[fk.parametreler.ws_orderCreationTime]
                lastExecutedPrice = message[fk.parametreler.ws_lastExecutedPrice]
                lastExecutedQuantity = message[fk.parametreler.ws_lastExecutedQuantity]
                if (side == "BUY") and (currentStatus in ["FILLED", "TRADE", "PARTIALLY_FILLED"]):
                    ORDER_LIST.pop(orderId)
                    try:
                        result, totalWeightUsed = fk.putOcoOrder(symbol="BTCFDUSD",
                                                                 side="SELL",
                                                                 timeInForce="GTC",
                                                                 quantity=float(lastExecutedQuantity),
                                                                 targetPrice=float(lastExecutedPrice) + 1,
                                                                 trigerPrice=float(lastExecutedPrice) - 298,
                                                                 limitPrice=float(lastExecutedPrice) - 300,
                                                                 priceFilter=priceFilter,
                                                                 lotSize=lotSize)
                        print(result)
                    except Exception as hata:
                        print(hata)
                        fk.putOrder(symbol="BTCFDUSD", side="SELL", orderType="LIMIT", timeInForce="GTC",
                                    quantity=float(cumulativeFilledQuantity), price=float(lastExecutedPrice) + 1,
                                    priceFilter=priceFilter, lotSize=lotSize)

    if "kline" in stream:
        message = message["data"]
        message = message["k"]
    elif "depth" in stream:
        try:
            message = message["data"]
            global_asks = np.asarray(message["asks"], dtype=np.double)
            global_bids = np.asarray(message["bids"], dtype=np.double)
            price = global_bids[0, 0]
            if FREE_FDUSD > 5:
                avg_ask_m = np.average(global_asks[:, 0] - global_asks[0,0], weights=global_asks[:,1])
                avg_bid_m = np.average(global_bids[:, 0] - global_bids[0,0], weights=global_bids[:,1])
                
                avg_ask = np.average(global_asks[:, 0], weights=global_asks[:,1])
                avg_bid = np.average(global_bids[:, 0], weights=global_bids[:,1])
                
                std_ask = np.average((global_asks[:, 0]-avg_ask)**2, weights=global_asks[:,1])
                std_bid = np.average((global_bids[:, 0]-avg_bid)**2, weights=global_bids[:,1])
                
                skew_ask_sum = np.inner(global_asks[:,1].T , ((global_asks[:, 0] - avg_ask)/std_ask)**3)
                skew_bid_sum = np.inner(global_bids[:,1].T , ((global_bids[:, 0] - avg_bid)/std_bid)**3)
                
                skew_ask = skew_ask_sum / np.sum(global_asks[:,1])
                skew_bid = skew_bid_sum / np.sum(global_bids[:,1])
                
                if (skew_bid > 0) and (skew_ask > 0) and (avg_ask > avg_bid):
                    try:
                        result, totalWeightUsed = fk.putOrder(symbol="BTCFDUSD",
                                                              side="BUY",
                                                              orderType="LIMIT",
                                                              timeInForce="GTC",
                                                              quantity=FREE_FDUSD,
                                                              price=price,
                                                              priceFilter=priceFilter,
                                                              lotSize=lotSize)
                        orderId = result["orderId"]
                        clientOrderId = result["clientOrderId"]
                        ORDER_LIST[orderId] = {"time": datetime.datetime.now(), "orderId": orderId, "clientOrderId": clientOrderId}
                    except Exception as hata:
                        print(hata)

        except Exception as hata:
            print(hata)
    elif "depths" in stream:
        try:
            message = message["data"]
            asks = np.asarray(message[fk.parametreler.ws_orderbook_asks], dtype=np.double)
            bids = np.asarray(message[fk.parametreler.ws_orderbook_bids], dtype=np.double)

            for ask in asks:
                index = np.where(global_asks[:, 0] == ask[0])[0]
                if index.size:
                    global_asks = np.append(
                        global_asks, ask.reshape(1, -1), axis=0)
                else:
                    global_asks[index, 1] = ask[1]

            for bid in bids:
                index = np.where(global_bids[:, 0] == bid[0])[0]
                if index.size:
                    global_bids = np.append(
                        global_bids, bid.reshape(1, -1), axis=0)
                else:
                    global_bids[index, 1] = bid[1]

            global_asks = np.delete(
                global_asks, np.where(global_asks[:, 1] == 0), 0)
            global_bids = np.delete(
                global_bids, np.where(global_bids[:, 1] == 0), 0)

            if FREE_FDUSD > 5:
                ratio = np.sum(global_asks[np.where(global_asks[:, 0] <= global_asks[0, 0] + 10), 1]) / \
                    np.sum(global_bids[np.where(
                        global_bids[:, 0] >= global_bids[0, 0] - 10), 1])

                if (3 * ratio < 1) and (ratio > 0):
                    try:
                        result, totalWeightUsed = fk.putOrder(symbol="BTCFDUSD",
                                                              side="BUY",
                                                              orderType="LIMIT",
                                                              timeInForce="GTC",
                                                              quantity=FREE_FDUSD,
                                                              price=price,
                                                              priceFilter=priceFilter,
                                                              lotSize=lotSize)
                        orderId = result["orderId"]
                        clientOrderId = result["clientOrderId"]
                        ORDER_LIST[orderId] = {
                            "time": datetime.datetime.now(), "clientOrderId": clientOrderId}
                    except Exception as hata:
                        print(hata)

        except Exception as hata:
            print(hata)
    elif "bookTicker" in stream:
        message = message["data"]
        price = float(message["b"])

        if (price < global_min_bid + 10) or (price > global_max_ask - 10):
            result, global_asks, global_bids, totalWeightUsed = fk.getOrderDepths(
                fk.parametreler.IZLENEN_CIFT, fk.parametreler.ALIM_SATIM_MAX_DERINLIK)
            global_asks = np.asarray(global_asks, dtype=np.double)
            global_bids = np.asarray(global_bids, dtype=np.double)
            global_max_ask = np.max(global_asks[:, 0])
            global_min_bid = np.min(global_bids[:, 0])
    elif "aggTrade" in stream:
        message = message["data"]

ws = wb.WebSocketApp(BINANCE_SOCKET, on_open=on_open,
                     on_close=on_close,
                     on_error=on_error,
                     on_message=on_message)
ws.run_forever()
