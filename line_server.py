import os, re, requests, urllib3
import matplotlib
# 必須在所有 import 之前強制指定使用 Agg 模式，否則在 Render 執行繪圖時會崩潰
matplotlib.use('Agg') 
import matplotlib.pyplot as plt
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, ImageSendMessage, FlexSendMessage
import pandas as pd
import mplfinance as mpf

# 隱藏 SSL 未驗證的警告訊息
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# ========= 設定區 (請確認資料是否正確) =========
# 1. Channel Access Token
LINE_ACCESS_TOKEN = "zGojeXY7W+OOc+H+hpbohy6c2ZVw352Tr7V4iWm7luvYkFOqOZhjdqA4aVAU6X3fhAsy8C1Bhr0r8uuFEP312UlZI5JP2GrqeFGIb70r3ZxCW6mOW2S1k/2wuiLsE4u1UwhNQPKKRfXExBz0i/T5rAdB04t89/1O/w1cDnyilFU="
# 2. Channel Secret
LINE_HANDLER_SECRET = "f3187d1658e4e7f172cd19fddda08a36" 
# 3. Imgur Client ID
IMGUR_CLIENT_ID = "54d96d74494c8e7"

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_HANDLER_SECRET)

def create_kline_panel(sid):
    """建立 K 線按鈕選單 (Flex Message)"""
    return FlexSendMessage(
        alt_text=f"股票 ({sid}) 選單",
        contents={
          "type": "bubble",
          "header": {
            "type": "box", "layout": "vertical", "backgroundColor": "#2c3e50",
            "contents": [{"type": "text", "text": f"📈 查詢代碼: {sid}", "weight": "bold", "size": "xl", "color": "#ffffff"}]
          },
          "body": {
            "type": "box", "layout": "vertical",
            "contents": [
              {"type": "text", "text": "請選擇週期查看 K 線圖", "margin": "md", "size": "sm", "color": "#666666"},
              {"type": "box", "layout": "horizontal", "margin": "lg", "spacing": "sm",
                "contents": [
                  {"type": "button", "style": "primary", "color": "#E74C3C", "action": {"type": "message", "label": "1分K", "text": f"{sid} 1分K"}},
                  {"type": "button", "style": "primary", "color": "#3498DB", "action": {"type": "message", "label": "5分K", "text": f"{sid} 5分K"}}
                ]
              },
              {"type": "box", "layout": "horizontal", "margin": "sm", "spacing": "sm",
                "contents": [
                  {"type": "button", "style": "secondary", "color": "#95A5A6", "action": {"type": "message", "label": "日線", "text": f"{sid} 日線"}},
                  {"type": "button", "style": "secondary", "color": "#95A5A6", "action": {"type": "message", "label": "週線", "text": f"{sid} 週線"}}
                ]
              }
            ]
          }
        }
    )

def get_kline_url(sid, label):
    """抓取證交所資料、繪圖並上傳至 Imgur"""
    headers = {'User-Agent': 'Mozilla/5.0'}
    url = f"https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&stockNo={sid}"
    try:
        # 重點修正：加入 verify=False 徹底解決 Log 中的 SSL 驗證失敗問題
        res = requests.get(url, headers=headers, timeout=10, verify=False).json()
        
        if res.get("stat") != "OK":
            print(f"!!! 證交所資料抓取失敗: {res.get('stat')} !!!")
            return None
        
        # 資料處理
        df = pd.DataFrame(res["data"], columns=["date","cap","tur","open","high","low","close","chg","tra"])
        df["date"] = df["date"].apply(lambda d: f"{int(d.split('/')[0])+1911}-{d.split('/')[1]}-{d.split('/')[2]}")
        df = df.rename(columns={"date":"Date","open":"Open","high":"High","low":"Low","close":"Close","cap":"Volume"})
        df["Date"] = pd.to_datetime(df["Date"])
        for col in ["Open","High","Low","Close","Volume"]:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(",",""), errors='coerce')
        
        # 繪製 K 線圖
        tmp = "/tmp/kline.png"
        mpf.plot(df.set_index("Date").tail(60), type='candle', style='yahoo', volume=True, mav=(5,20), 
                 title=f"Stock {sid} ({label})", savefig=dict(fname=tmp, dpi=100))
        
        # 上傳至 Imgur
        with open(tmp, "rb") as f:
            r = requests.post("https://api.imgur.com/3/image", 
                              headers={"Authorization": f"Client-ID {IMGUR_CLIENT_ID}"}, 
                              files={"image": f}).json()
        
        if r.get("success"):
            return r["data"]["link"]
        else:
            print(f"!!! Imgur 上傳失敗: {r.get('data', {}).get('error')} !!!")
            return None
    except Exception as e:
        print(f"!!! 發生繪圖或連線錯誤: {e} !!!")
        return None

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text.strip()
    
    # 輸入 4 位數字代碼噴出選單
    if re.match(r'^\d{4}$', msg):
        line_bot_api.reply_message(event.reply_token, create_kline_panel(msg))
        return

    # 處理點擊按鈕後的邏輯
    match = re.match(r'^(\d{4})\s+(.*)$', msg)
    if match:
        sid, label = match.groups()
        url = get_kline_url(sid, label)
        if url:
            line_bot_api.reply_message(event.reply_token, [
                TextMessage(text=f"📊 已生成 {sid} 的 {label} 圖表"),
                ImageSendMessage(original_content_url=url, preview_image_url=url)
            ])
        else:
            line_bot_api.reply_message(event.reply_token, TextMessage(text="❌ 暫時無法生成圖表，請稍後再試或檢查 Log。"))

if __name__ == "__main__":
    # 使用 Render 預設的 Port 10000
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
