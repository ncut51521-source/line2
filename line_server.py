import os, re, requests, urllib3, datetime, json
import matplotlib
matplotlib.use('Agg') 
import matplotlib.pyplot as plt
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, ImageSendMessage, FlexSendMessage
import pandas as pd
import mplfinance as mpf

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# ========= 設定區 (請確保這些資料正確) =========
LINE_ACCESS_TOKEN = "zGojeXY7W+OOc+H+hpbohy6c2ZVw352Tr7V4iWm7luvYkFOqOZhjdqA4aVAU6X3fhAsy8C1Bhr0r8uuFEP312UlZI5JP2GrqeFGIb70r3ZxCW6mOW2S1k/2wuiLsE4u1UwhNQPKKRfXExBz0i/T5rAdB04t89/1O/w1cDnyilFU="
LINE_HANDLER_SECRET = "f3187d1658e4e7f172cd19fddda08a36" 
IMGUR_CLIENT_ID = "54d96d74494c8e7"

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_HANDLER_SECRET)

def get_kline_url(sid):
    headers = {'User-Agent': 'Mozilla/5.0'}
    all_rows = []
    
    try:
        # 只抓最近一個月，確保速度最快且不被封鎖
        today = datetime.date.today().strftime("%Y%m01")
        url = f"https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date={today}&stockNo={sid}"
        res = requests.get(url, headers=headers, timeout=10, verify=False).json()
        
        if res.get("stat") != "OK": return f"證交所回傳錯誤: {res.get('stat')}"
        all_rows = res["data"]

        df = pd.DataFrame([row[:9] for row in all_rows], columns=["date","cap","tur","open","high","low","close","chg","tra"])
        df["date"] = df["date"].apply(lambda d: f"{int(d.split('/')[0])+1911}-{d.split('/')[1]}-{d.split('/')[2]}")
        df = df.rename(columns={"date":"Date","open":"Open","high":"High","low":"Low","close":"Close","cap":"Volume"})
        df["Date"] = pd.to_datetime(df["Date"])
        for col in ["Open","High","Low","Close","Volume"]:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(",",""), errors='coerce')
        df = df.sort_values("Date").set_index("Date")

        # 繪圖優化：縮小尺寸以符合 Render 記憶體限制
        mc = mpf.make_marketcolors(up='#E74C3C', down='#2ECC71', edge='inherit', wick='inherit', volume='inherit')
        s = mpf.make_mpf_style(marketcolors=mc, gridstyle='--', gridcolor='#f0f0f0')

        tmp_path = "/tmp/stock.png"
        mpf.plot(df.tail(30), type='candle', style=s, volume=True, figsize=(8, 6),
                 savefig=dict(fname=tmp_path, dpi=80, bbox_inches='tight'))

        # 上傳到 Imgur 的加強版邏輯
        with open(tmp_path, "rb") as f:
            payload = {'image': f.read()}
            headers = {'Authorization': f'Client-ID {IMGUR_CLIENT_ID}'}
            r = requests.post("https://api.imgur.com/3/image", headers=headers, files=payload, timeout=15, verify=False)
            
            # 增加詳細錯誤紀錄
            if r.status_code != 200:
                return f"Imgur 上傳失敗碼: {r.status_code}, 內容: {r.text[:50]}"
            
            data = r.json()
            return data["data"]["link"] if data.get("success") else "Imgur 回傳 success 為假"

    except Exception as e:
        return f"程式執行錯誤: {str(e)}"

# --- Webhook 邏輯 ---
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)
    try: handler.handle(body, signature)
    except InvalidSignatureError: abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text.strip()
    # 只要輸入 4 位數字代碼
    if re.match(r'^\d{4}$', msg):
        line_bot_api.reply_message(event.reply_token, create_kline_panel(msg))
    # 點擊按鈕觸發的文字
    elif "日線" in msg:
        sid = msg.split(" ")[0]
        url = get_kline_url(sid)
        if url.startswith("http"):
            line_bot_api.reply_message(event.reply_token, ImageSendMessage(original_content_url=url, preview_image_url=url))
        else:
            line_bot_api.reply_message(event.reply_token, TextMessage(text=f"⚠️ {url}"))

def create_kline_panel(sid):
    return FlexSendMessage(
        alt_text=f"股票 {sid} 選單",
        contents={
          "type": "bubble",
          "body": {
            "type": "box", "layout": "vertical", "contents": [
              {"type": "text", "text": f"查詢代碼: {sid}", "weight": "bold", "size": "xl"},
              {"type": "button", "style": "primary", "margin": "md", "action": {"type": "message", "label": "查看日線 K 線圖", "text": f"{sid} 日線"}}
            ]
          }
        }
    )

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
