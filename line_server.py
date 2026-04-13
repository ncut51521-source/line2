import os, re, requests, urllib3
import matplotlib
# 強制指定使用 Agg 模式
matplotlib.use('Agg') 
import matplotlib.pyplot as plt
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, ImageSendMessage, FlexSendMessage
import pandas as pd
import mplfinance as mpf

# 隱藏 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# ========= 設定區 =========
LINE_ACCESS_TOKEN = "zGojeXY7W+OOc+H+hpbohy6c2ZVw352Tr7V4iWm7luvYkFOqOZhjdqA4aVAU6X3fhAsy8C1Bhr0r8uuFEP312UlZI5JP2GrqeFGIb70r3ZxCW6mOW2S1k/2wuiLsE4u1UwhNQPKKRfXExBz0i/T5rAdB04t89/1O/w1cDnyilFU="
LINE_HANDLER_SECRET = "f3187d1658e4e7f172cd19fddda08a36" 
IMGUR_CLIENT_ID = "54d96d74494c8e7"

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_HANDLER_SECRET)

def create_kline_panel(sid):
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
    # 1. 強化 Headers
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Referer': 'https://www.twse.com.tw/zh/page/trading/exchange/STOCK_DAY.html'
    }
    url = f"https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&stockNo={sid}"
    
    try:
        # 抓取資料
        res = requests.get(url, headers=headers, timeout=15, verify=False).json()
        
        if res.get("stat") != "OK":
            return f"ERR_DATA: {res.get('stat')}"
        
        # 資料處理
        df = pd.DataFrame(res["data"], columns=["date","cap","tur","open","high","low","close","chg","tra"])
        df["date"] = df["date"].apply(lambda d: f"{int(d.split('/')[0])+1911}-{d.split('/')[1]}-{d.split('/')[2]}")
        df = df.rename(columns={"date":"Date","open":"Open","high":"High","low":"Low","close":"Close","cap":"Volume"})
        df["Date"] = pd.to_datetime(df["Date"])
        for col in ["Open","High","Low","Close","Volume"]:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(",",""), errors='coerce')
        
        # 繪圖
        tmp = "/tmp/kline.png"
        if os.path.exists(tmp): os.remove(tmp) # 確保舊圖被刪除
        
        mpf.plot(df.set_index("Date").tail(60), type='candle', style='yahoo', volume=True, mav=(5,20), 
                 title=f"Stock {sid} ({label})", savefig=dict(fname=tmp, dpi=100))
        
        # 2. 上傳至 Imgur
        with open(tmp, "rb") as f:
            r = requests.post("https://api.imgur.com/3/image", 
                              headers={"Authorization": f"Client-ID {IMGUR_CLIENT_ID}"}, 
                              files={"image": f}).json()
        
        if r.get("success"):
            return r["data"]["link"]
        else:
            return f"ERR_IMGUR: {r.get('data', {}).get('error')}"
            
    except Exception as e:
        return f"ERR_SYSTEM: {str(e)}"

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
    
    if re.match(r'^\d{4}$', msg):
        line_bot_api.reply_message(event.reply_token, create_kline_panel(msg))
        return

    match = re.match(r'^(\d{4})\s+(.*)$', msg)
    if match:
        sid, label = match.groups()
        # 呼叫並取得結果
        result = get_kline_url(sid, label)
        
        # 根據回傳結果進行判斷
        if result.startswith("http"):
            line_bot_api.reply_message(event.reply_token, [
                TextMessage(text=f"📊 已生成 {sid} 的 {label} 圖表"),
                ImageSendMessage(original_content_url=result, preview_image_url=result)
            ])
        else:
            # 3. 直接在 LINE 噴出詳細錯誤原因
            line_bot_api.reply_message(event.reply_token, TextMessage(text=f"❌ 錯誤詳情：{result}"))

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
