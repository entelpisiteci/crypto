import MetaTrader5 as mt5
from dotenv import load_dotenv
import os
import time
from datetime import datetime, timedelta
import logging
import ta
import pandas as pd
import numpy as np
import telebot
from xgboost import XGBRegressor
from sklearn.preprocessing import MinMaxScaler
import requests
from typing import Optional, Dict, List
from transformers import pipeline, AutoTokenizer, TFAutoModelForSequenceClassification
from arabert.preprocess import ArabertPreprocessor
import asyncio
from lightgbm import LGBMRegressor
from sklearn.metrics import mean_squared_error
import optuna
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from tensorflow.keras.models import Model
from tensorflow.keras.layers import LSTM, Dense, Dropout, Input
from tensorflow.keras.optimizers import Adam

# ==================== Initialize Logger ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
load_dotenv()

# ==================== CONST Configuration ====================
SYMBOL = "XAUUSD"
TELEGRAM_BOT_TOKEN = "TG-TOKEN"
TELEGRAM_CHAT_ID = "TG-CHAT-ID"
NEWS_API_KEYS = os.getenv("NEWS_API_KEYS", "").split(",")  # List of API keys
CURRENT_API_KEY_INDEX = int(os.getenv("CURRENT_API_KEY_INDEX", "0"))  # Current API key index
THRESHOLD_WIDESPREAD_NEWS = 0.9
NEWS_PERCENT = 0.002
STOP_LOSS_NEWS_PERCENT = 0.008
RISK_PERCENT = 1
MT5_LOGIN = 123456789  # Restored MT5 account number
MT5_PASSWORD = "QWERTY"  # Restored MT5 password
MT5_SERVER = "EquitiSecurities-Live"  # Restored broker's server name

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
START_DATE = datetime(2019, 1, 1)
END_DATE = datetime.now()

# ==================== MT5 Initialization ====================
def initialize_mt5():
    """Initialize MetaTrader 5 connection."""
    if not mt5.initialize(login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
        logger.error("MT5 Initialization Failed, error code = %s", mt5.last_error())
        quit()
    logger.info("MT5 Initialized: %s", mt5.terminal_info())
    logger.info("MT5 Version: %s", mt5.version())

initialize_mt5()

# ==================== Model Functions ====================
def preprocess_data(df: pd.DataFrame, column: str, window_size: int = 60):
    """Preprocess the data for training or prediction."""
    scaler = MinMaxScaler()
    data = df[column].values
    data = scaler.fit_transform(data.reshape(-1, 1))

    X, y = [], []
    for i in range(window_size, len(data)):
        X.append(data[i - window_size:i, 0])
        y.append(data[i, 0])

    X, y = np.array(X), np.array(y)
    X = np.reshape(X, (X.shape[0], X.shape[1], 1))
    y = np.reshape(y, (-1, 1))
    
    return X, y, scaler

def build_lstm_model(window_size: int):
    """Build and compile the LSTM model."""
    input1 = Input(shape=(window_size, 1))
    x = LSTM(units=64, return_sequences=True)(input1)
    x = Dropout(0.2)(x)
    x = LSTM(units=64, return_sequences=True)(x)
    x = Dropout(0.2)(x)
    x = LSTM(units=64)(x)
    x = Dropout(0.2)(x)
    x = Dense(32, activation='softmax')(x)
    output = Dense(1)(x)
    
    model = Model(inputs=input1, outputs=output)
    model.compile(loss='mean_squared_error', optimizer=Adam())
    
    return model

def train_lstm_model(df: pd.DataFrame, column: str, window_size: int = 60):
    """Train the LSTM model."""
    X, y, scaler = preprocess_data(df, column, window_size)
    model = build_lstm_model(window_size)
    model.fit(X, y, epochs=150, batch_size=32, validation_split=0.1, verbose=1)
    
    return model, scaler

# ==================== News Fetching and Sentiment Analysis ====================
async def fetch_news(query: str, language: str = "en") -> List[Dict]:
    """Fetch financial news asynchronously."""
    global CURRENT_API_KEY_INDEX
    yesterday = (datetime.today() - timedelta(days=1)).strftime('%Y-%m-%d')
    today = datetime.today().strftime('%Y-%m-%d')
    api_key = NEWS_API_KEYS[CURRENT_API_KEY_INDEX]
    url = f"https://newsapi.org/v2/everything?q={query}&language={language}&from={yesterday}&to={today}&apiKey={api_key}"
    
    try:
        response = await asyncio.to_thread(requests.get, url)
        response.raise_for_status()
        articles = response.json().get("articles", [])
        return [article for article in articles if "gold" in article.get("title", "").lower()]
    except requests.exceptions.HTTPError as e:
        if response.status_code == 429:  # Rate limit exceeded
            logger.warning(f"Rate limit exceeded. Switching API key.")
            CURRENT_API_KEY_INDEX = (CURRENT_API_KEY_INDEX + 1) % len(NEWS_API_KEYS)
            return await fetch_news(query, language)
        else:
            logger.error(f"HTTPError: {str(e)}")
            return []
    except Exception as e:
        logger.error(f"Failed to fetch financial news: {str(e)}")
        return []

def analyze_sentiment(articles: List[Dict], language: str = "en") -> dict:
    """Analyze sentiment of news articles."""
    try:
        tokenizer, model = None, None
        if language == "ar":
            preprocessor = ArabertPreprocessor(model_name="aubmindlab/bert-base-arabertv2")
            tokenizer = AutoTokenizer.from_pretrained("aubmindlab/bert-base-arabertv2")
            model = TFAutoModelForSequenceClassification.from_pretrained("aubmindlab/bert-base-arabertv2")
        else:
            tokenizer = AutoTokenizer.from_pretrained("ProsusAI/finbert")
            model = TFAutoModelForSequenceClassification.from_pretrained("ProsusAI/finbert")
        
        sentiment_pipeline = pipeline("sentiment-analysis", model=model, tokenizer=tokenizer)
        sentiments = [sentiment_pipeline(article["title"] + " " + article["description"]) for article in articles]

        positive_count = sum(1 for sentiment in sentiments if sentiment[0]['label'] == 'positive')
        negative_count = sum(1 for sentiment in sentiments if sentiment[0]['label'] == 'negative')
        
        total = len(sentiments)
        sentiment_score = {
            "positive": positive_count / total if total else 0,
            "negative": negative_count / total if total else 0
        }
        
        return sentiment_score
    except Exception as e:
        logger.error(f"Error in sentiment analysis: {str(e)}")
        return {"positive": 0, "negative": 0}

# ==================== Order Placement ====================
def check_real_time_price(symbol: str, target_price: float, order_type: int, timeout: int = 60 * 13) -> bool:
    """Monitor real-time ask/bid prices and return True if the price matches or approaches the target."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        symbol_info = mt5.symbol_info_tick(symbol)
        ask_price = symbol_info.ask
        bid_price = symbol_info.bid
        
        if order_type == mt5.ORDER_TYPE_BUY and ask_price >= target_price - 0.5:
            logger.info(f"BUY Order: Ask price {ask_price} matches target price {target_price}.")
            return True
        elif order_type == mt5.ORDER_TYPE_SELL and bid_price <= target_price + 0.5:
            logger.info(f"SELL Order: Bid price {bid_price} matches target price {target_price}.")
            return True
        
        time.sleep(5)
    
    logger.warning(f"Timeout reached. Price didn't reach target {target_price}.")
    return False

def place_order(symbol: str, target_price: float, lot_size: float, order_type: int, slippage: float = 0.5):
    """Place a market order with specified parameters."""
    symbol_info = mt5.symbol_info(symbol)
    
    if not symbol_info:
        logger.error(f"Symbol {symbol} not found.")
        return
    
    price = mt5.symbol_info_tick(symbol).ask if order_type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(symbol).bid
    price += slippage if order_type == mt5.ORDER_TYPE_BUY else -slippage
    
    order = mt5.ORDER_TYPE_BUY if order_type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_SELL
    deviation = 20  # Maximum allowed price deviation in pips
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot_size,
        "type": order,
        "price": price,
        "slippage": deviation,
        "magic": 234000,
        "comment": "Python trading",
        "type_filling": mt5.ORDER_FILLING_IOC,
        "type_time": mt5.ORDER_TIME_GTC,
    }
    
    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        logger.error(f"Error in order send: {result.retcode}")
    else:
        logger.info(f"Order placed successfully. Order ID: {result.order}")

# ==================== Main function ====================
def main():
    """Main function to orchestrate trading logic."""
    symbol = SYMBOL
    df = pd.read_csv('historical_data.csv')  # Load historical data for training
    model, scaler = train_lstm_model(df, "close")  # Train LSTM model for prediction
    
    while True:
        try:
            # Fetch sentiment and news
            news = asyncio.run(fetch_news("gold"))
            sentiment_score = analyze_sentiment(news, language="en")
            logger.info(f"Sentiment score: {sentiment_score}")
            
            # Additional logic to place orders based on the analysis goes here...
            
            time.sleep(60)  # Sleep before next execution
        except Exception as e:
            logger.error(f"An error occurred: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()
