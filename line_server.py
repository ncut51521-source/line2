import os, re, requests
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, ImageSendMessage
import pandas as pd
import mplfinance as mpf

app = Flask(__name__)

# ========= 設定區 =========
# 填入你從 LINE Developers 取得的資訊
LINE_ACCESS_TOKEN = "zGojeXY7W+OOc+H+hpbohy6c2ZVw352Tr7V4iWm7luvYkFOqOZhjdqA4aVAU6X3fhAsy8C1Bhr0r8uuFEP312UlZI5JP2GrqeFGIb70r3ZxCW6mOW2S1k/2wuiLsE4u1UwhNQPKKRfXExBz0i/T5rAdB04t89/1O/w1cDnyilFU=" #
LINE_HANDLER_SECRET = "f3187d1658e4e7f172cd19fddda08a36" #
# Imgur 用於存放 K 線圖網址 (LINE 規定必須使用 https 圖片連結)
IMGUR_CLIENT_ID = "54d96d74494c8e7" 

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_HANDLER_SECRET)

def get_stock_kline(sid):
    """雲端抓取證交所資料並繪圖"""
    headers = {'User-Agent': 'Mozilla/5.0'}
    url = f"https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&stockNo={sid}"
    
    try:
        res = requests.get(url, headers=headers, timeout=10).json()
        if res.get("stat") != "OK": return None
        
        # 整理資料
        df = pd.DataFrame(res["data"], columns=["date","cap","tur","open","high","low","close","chg","tra"])
        df["date"] = df["date"].apply(lambda d: f"{int(d.split('/')[0])+1911}-{d.split('/')[1]}-{d.split('/')[2]}")
        df = df.rename(columns={"date":"Date","open":"Open","high":"High","low":"Low","close":"Close","cap":"Volume"})
        df["Date"] = pd.to_datetime(df["Date"])
        for col in ["Open","High","Low","Close","Volume"]:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(",",""), errors='coerce')
        
        # 繪圖並存成暫存檔 (Render 環境需存於 /tmp)
        tmp_img = "/tmp/kline.png"
        mpf.plot(df.set_index("Date").tail(60), type='candle', style='yahoo', volume=True, savefig=tmp_img)
        
        # 上傳到 Imgur 取得網址
        with open(tmp_img, "rb") as f:
            img_res = requests.post(
                "https://api.imgur.com/3/image", 
                headers={"Authorization": f"Client-ID {IMGUR_CLIENT_ID}"}, 
                files={"image": f}
            ).json()
        
        return img_res["data"]["link"] if img_res.get("success") else None
    except:
        return None

https://line2-xxh5.onrender.com/callback
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text.strip()
    
    # 正則表達式：判斷是否為 4 位數字的股票代碼
    if re.match(r'^\d{4}$', msg):
        img_url = get_stock_kline(msg)
        if img_url:
            line_bot_api.reply_message(
                event.reply_token,
                ImageSendMessage(original_content_url=img_url, preview_image_url=img_url)
            )
        else:
            line_bot_api.reply_message(event.reply_token, TextMessage(text=f"抱歉，無法取得代碼 {msg} 的股價圖表。"))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)