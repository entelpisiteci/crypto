import json
import websocket as wb
import mysql.connector
import time

# Change the pair you want to save klines
pair = "btcfdusd"
BINANCE_SOCKET = "wss://stream.binance.com:9443/stream?streams=" + pair + "@kline_1s/" + pair + "@depth20@100ms"

mydb = mysql.connector.connect(host="localhost", user="root", database="cryptocurrency")
cur = mydb.cursor()

def on_open(ws):
    print("connection opened")

def on_close(ws):
    print("closed connection")

def on_error(ws, error):
    print(error)

def on_message(ws, message):
    message = json.loads(message)
    stream = message["stream"]
    if "kline" in stream:
        message = message["data"]["k"]
        try:
            sql = "INSERT INTO klines(start_time, close_time, symbol, interval_length, open_price, close_price, high_price, low_price, base_asset_volume, number_of_trades, is_closed, quote_asset_volume, taker_buy_base_asset, taker_buy_quote_asset, recordTime) VALUES (" \
                + str(message["t"]) + "," + str(message["T"]) + "," + "'" + message["s"] + "',"  + "'" + message["i"] + "',"\
                + "'" + message["o"] + "'," + "'" + message["c"] + "'," + "'" + message["h"] + "'," + "'" + message["l"] + "',"\
                + "'" + message["v"] + "'," + str(message["n"]) + "," + str(message["x"]) + "," + "'" + message["q"] + "',"\
                + "'" + message["V"] + "','" + message["Q"] + "',"  + str(time.time()) + ")"
            cur.execute(sql)
            mydb.commit()
        except Exception as oerr:
            print(err)
    elif "depth" in stream:
        try:
            message = message["data"]
            sql = "INSERT INTO order_book_asks(symbol, time, lastUpdateId, ask_level_1,ask_quantity_1,ask_level_2,ask_quantity_2,ask_level_3,ask_quantity_3,ask_level_4,ask_quantity_4,ask_level_5,ask_quantity_5,ask_level_6,ask_quantity_6,ask_level_7,ask_quantity_7,ask_level_8,ask_quantity_8,ask_level_9,ask_quantity_9,ask_level_10,ask_quantity_10,ask_level_11,ask_quantity_11,ask_level_12,ask_quantity_12,ask_level_13,ask_quantity_13,ask_level_14,ask_quantity_14,ask_level_15,ask_quantity_15,ask_level_16,ask_quantity_16,ask_level_17,ask_quantity_17,ask_level_18,ask_quantity_18,ask_level_19,ask_quantity_19,ask_level_20,ask_quantity_20) VALUES(" + \
                "\"BTCFDUSD\"," + str(time.time()) + "," + str(message["lastUpdateId"])
            for level_no in range(1, 21):
                sql = sql + "," + message["asks"][level_no-1][0] + "," + message["asks"][level_no-1][1]
            sql = sql + ")"
            cur.execute(sql)
            mydb.commit()
            sql = "INSERT INTO order_book_bids(symbol, time, lastUpdateId, bid_level_1,bid_quantity_1,bid_level_2,bid_quantity_2,bid_level_3,bid_quantity_3,bid_level_4,bid_quantity_4,bid_level_5,bid_quantity_5,bid_level_6,bid_quantity_6,bid_level_7,bid_quantity_7,bid_level_8,bid_quantity_8,bid_level_9,bid_quantity_9,bid_level_10,bid_quantity_10,bid_level_11,bid_quantity_11,bid_level_12,bid_quantity_12,bid_level_13,bid_quantity_13,bid_level_14,bid_quantity_14,bid_level_15,bid_quantity_15,bid_level_16,bid_quantity_16,bid_level_17,bid_quantity_17,bid_level_18,bid_quantity_18,bid_level_19,bid_quantity_19,bid_level_20,bid_quantity_20) VALUES(" + \
                "\"BTCFDUSD\"," + str(time.time()) + "," + str(message["lastUpdateId"])
            for level_no in range(1, 21):
                sql = sql + "," + \
                    message["bids"][level_no-1][0] + "," + message["bids"][level_no-1][1]
            sql = sql + ")"
            cur.execute(sql)
            mydb.commit()
        except Exception as err:
            print(err)

ws = wb.WebSocketApp(BINANCE_SOCKET, on_open=on_open,
                     on_close=on_close,
                     on_error=on_error,
                     on_message=on_message)
ws.run_forever()
