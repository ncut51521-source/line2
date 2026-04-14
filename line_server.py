import os, re, requests, urllib3, datetime, base64
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

# ========= 設定區 (請確認這些資料正確) =========
LINE_ACCESS_TOKEN = "zGojeXY7W+OOc+H+hpbohy6c2ZVw352Tr7V4iWm7luvYkFOqOZhjdqA4aVAU6X3fhAsy8C1Bhr0r8uuFEP312UlZI5JP2GrqeFGIb70r3ZxCW6mOW2S1k/2wuiLsE4u1UwhNQPKKRfXExBz0i/T5rAdB04t89/1O/w1cDnyilFU="
LINE_HANDLER_SECRET = "f3187d1658e4e7f172cd19fddda08a36" 
IMGBB_API_KEY = "9473f1d3a5a7df4937227c2f689f7f4d" # 使用 ImgBB 繞過 Imgur 429 限制

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_HANDLER_SECRET)

def get_kline_url(sid):
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        # 抓取最近 2 個月的資料，確保夠畫 K 線
        today = datetime.date.today().strftime("%Y%m01")
        url = f"https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date={today}&stockNo={sid}"
        res = requests.get(url, headers=headers, timeout=10, verify=False).json()
        
        if res.get("stat") != "OK": return f"TWSE Error: {res.get('stat')}"
        
        df = pd.DataFrame([row[:9] for row in res["data"]], columns=["date","cap","tur","open","high","low","close","chg","tra"])
        df["date"] = df["date"].apply(lambda d: f"{int(d.split('/')[0])+1911}-{d.split('/')[1]}-{d.split('/')[2]}")
        df = df.rename(columns={"date":"Date","open":"Open","high":"High","low":"Low","close":"Close","cap":"Volume"})
        df["Date"] = pd.to_datetime(df["Date"])
        for col in ["Open","High","Low","Close","Volume"]:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(",",""), errors='coerce')
        df = df.sort_values("Date").set_index("Date")

        # 樣式設定
        mc = mpf.make_marketcolors(up='#E74C3C', down='#2ECC71', edge='inherit', wick='inherit', volume='inherit')
        s = mpf.make_mpf_style(marketcolors=mc, gridstyle='--', gridcolor='#f0f0f0')

        # 儲存圖片
        tmp_path = "/tmp/stock_img.png"
        mpf.plot(df.tail(30), type='candle', style=s, volume=True, figsize=(8, 6),
                 savefig=dict(fname=tmp_path, dpi=80, bbox_inches='tight'))

        # 上傳到 ImgBB
        with open(tmp_path, "rb") as file:
            url = "https://api.imgbb.com/1/upload"
            payload = {
                "key": IMGBB_API_KEY,
                "image": base64.b64encode(file.read()),
            }
            res = requests.post(url, payload, timeout=20).json()
            
            if res.get("success"):
                return res["data"]["url"]
            else:
                return f"ImgBB Error: {res.get('error', {}).get('message')}"

    except Exception as e:
        return f"System Error: {str(e)}"

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
    if re.match(r'^\d{4}$', msg):
        line_bot_api.reply_message(event.reply_token, create_kline_panel(msg))
    elif "日線" in msg:
        sid = msg.split(" ")[0]
        result_url = get_kline_url(sid)
        if result_url.startswith("http"):
            line_bot_api.reply_message(event.reply_token, ImageSendMessage(original_content_url=result_url, preview_image_url=result_url))
        else:
            line_bot_api.reply_message(event.reply_token, TextMessage(text=f"⚠️ {result_url}"))

def create_kline_panel(sid):
    return FlexSendMessage(
        alt_text=f"股票 {sid} 選單",
        contents={
          "type": "bubble",
          "body": {
            "type": "box", "layout": "vertical", "contents": [
              {"type": "text", "text": f"查詢代碼: {sid}", "weight": "bold", "size": "xl"},
              {"type": "button", "style": "primary", "margin": "md", "action": {"type": "message", "label": "查看日線圖", "text": f"{sid} 日線"}}
            ]
          }
        }
    )

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
