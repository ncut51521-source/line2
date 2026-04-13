import os, re, requests, urllib3
import matplotlib
# 必須在最前面強制指定 Agg 模式
matplotlib.use('Agg') 
import matplotlib.pyplot as plt
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, ImageSendMessage, FlexSendMessage
import pandas as pd
import mplfinance as mpf

# 徹底禁用 SSL 警告
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
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    url = f"https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&stockNo={sid}"
    
    try:
        # 第一關：抓取資料 (強行跳過 SSL)
        res_raw = requests.get(url, headers=headers, timeout=15, verify=False)
        res = res_raw.json()
        
        if res.get("stat") != "OK":
            return f"ERR_DATA: {res.get('stat')}"
        
        # 資料處理 (修正欄位對齊)
        raw_data = res["data"]
        df = pd.DataFrame([row[:9] for row in raw_data], 
                          columns=["date","cap","tur","open","high","low","close","chg","tra"])
        
        df["date"] = df["date"].apply(lambda d: f"{int(d.split('/')[0])+1911}-{d.split('/')[1]}-{d.split('/')[2]}")
        df = df.rename(columns={"date":"Date","open":"Open","high":"High","low":"Low","close":"Close","cap":"Volume"})
        df["Date"] = pd.to_datetime(df["Date"])
        for col in ["Open","High","Low","Close","Volume"]:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(",",""), errors='coerce')
        
        # 繪圖
        tmp = "/tmp/kline.png"
        if os.path.exists(tmp): os.remove(tmp)
        mpf.plot(df.set_index("Date").tail(60), type='candle', style='yahoo', volume=True, mav=(5,20), 
                 title=f"Stock {sid} ({label})", savefig=dict(fname=tmp, dpi=100))
        
        # 第二關：上傳至 Imgur (強行跳過 SSL 並加強報錯)
        with open(tmp, "rb") as f:
            r_raw = requests.post(
                "https://api.imgur.com/3/image", 
                headers={"Authorization": f"Client-ID {IMGUR_CLIENT_ID}"}, 
                files={"image": f},
                verify=False
            )
            r = r_raw.json()
        
        if r.get("success"):
            return r["data"]["link"]
        else:
            # 解決 ERR_IMGUR: None 的問題
            err = r.get('data', {}).get('error', 'Imgur 拒絕連線')
            if isinstance(err, dict): err = err.get('message', '未知錯誤')
            return f"ERR_IMGUR: {err}"
            
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
        result = get_kline_url(sid, label)
        
        if result and result.startswith("http"):
            line_bot_api.reply_message(event.reply_token, [
                TextMessage(text=f"📊 已生成 {sid} 的 {label} 圖表"),
                ImageSendMessage(original_content_url=result, preview_image_url=result)
            ])
        else:
            line_bot_api.reply_message(event.reply_token, TextMessage(text=f"❌ 錯誤詳情：{result}"))

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
