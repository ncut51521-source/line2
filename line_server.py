import os, re, datetime
import matplotlib
matplotlib.use('Agg')  # 必備：確保在伺服器環境下繪圖不會出錯
import matplotlib.pyplot as plt
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, ImageSendMessage, FlexSendMessage
import pandas as pd
import mplfinance as mpf
import twstock
import cloudinary
import cloudinary.uploader

app = Flask(__name__)

# ========= 核心設定 (請確認與你的 LINE/Cloudinary 後台一致) =========
LINE_ACCESS_TOKEN = "yl+8P+/NQEAvmculw5AgfS3cIQ51yV63NOeHujxxBFgZKWME6Xa0Vs/eBQw7M8/thAsy8C1Bhr0r8uuFEP312UlZI5JP2GrqeFGIb70r3ZxygFDmgyyrqYg7kaZoLsZP6q8PdJPIKnESlz2LDNI4aAdB04t89/1O/w1cDnyilFU="
LINE_HANDLER_SECRET = "a479ce8e693bd35d0dd5541964945456" 

# Cloudinary 配置 (使用你最後提供的 dzip2nboe 帳號)
cloudinary.config( 
  cloud_name = "dzip2nboe", 
  api_key = "124438874888122", 
  api_secret = "X71kcLFVNKX-XYjKHCbCnMFAzCw" 
)

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_HANDLER_SECRET)

def get_kline_url(sid):
    try:
        plt.switch_backend('Agg')
        
        # --- 核心邏輯：使用 twstock 避開 Yahoo IP 封鎖 ---
        stock = twstock.Stock(sid)
        raw_data = stock.fetch_31()  # 抓取最近 31 筆交易資料
        
        if not raw_data or len(raw_data) < 5:
            # 如果抓不到，嘗試更新代碼表後再抓一次
            twstock.__update_codes()
            raw_data = stock.fetch_31()
            if not raw_data:
                return "交易所目前連線繁忙，請稍後再試"

        # 轉換成 DataFrame
        df = pd.DataFrame(raw_data)
        # twstock 欄位順序: Date, Capacity, Turnover, Open, High, Low, Close, Change, Transaction
        df.columns = ['Date', 'Capacity', 'Turnover', 'Open', '
