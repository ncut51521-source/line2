import os, re, requests, urllib3
import matplotlib
# 必須在所有 import 之前強制指定使用 Agg 模式，避免 Render 繪圖崩潰
matplotlib.use('Agg') 
import matplotlib.pyplot as plt
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, ImageSendMessage, FlexSendMessage
import pandas as pd
import mplfinance as mpf

# 隱藏 SSL 未驗證警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# ========= 設定區 (請確保這些資料與你的 LINE/Imgur 後台一致) =========
LINE_ACCESS_TOKEN = "zGojeXY7W+OOc+H+hpbohy6c2ZVw352Tr7V4iWm7luvYkFOqOZhjdqA4aVAU6X3fhAsy8C1Bhr0r8uuFEP312UlZI5JP2GrqeFGIb70r3ZxCW6mOW2S1k/2wuiLsE4u1UwhNQPKKRfXExBz0i/T5rAdB04t89/1O/w1cDnyilFU="
LINE_HANDLER_SECRET = "f3187d1658e4e7f172cd19fddda08a36" 
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
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Referer': 'https://www.twse.com.tw/'
    }
    url = f"https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&stockNo={sid}"
    
    try:
        # 1. 抓取資料 (verify=False 解決 SSL 問題)
        res = requests.get(url, headers=headers, timeout=15, verify=False).json()
        
        if res.get("stat") != "OK":
            return f"ERR_DATA: {res.get('stat')}"
        
        # 2. 資料處理：修正 10 欄位對齊問題
        raw_data = res["data"]
        # 強制只取前 9 欄，確保對齊 columns 定義
        df = pd.DataFrame([row[:9] for row in raw_data], 
                          columns=["date","cap","tur","open","high","low","close","chg","tra"])
        
        # 日期與數值格式轉換
        df["date"] = df["date"].apply(lambda d: f"{int(d.split('/')[0])+1911}-{d.split('/')[1]}-{d.split('/')[2]}")
        df = df.rename(columns={"date":"Date","open":"Open","high":"High","low":"Low","close":"Close","cap":"Volume"})
        df["Date"] = pd.to_datetime(df["Date"])
        for col in ["Open","High","Low","Close","Volume"]:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(",",""), errors='coerce')
        
        # 3. 繪製 K 線圖
        tmp = "/tmp/kline.png"
        if os.path.exists(tmp): os.remove(tmp)
        
        mpf.plot(df.set_index("Date").tail(60), type='candle', style='yahoo', volume=True, mav=(5,20), 
                 title=f"Stock {sid} ({label})", savefig=dict(fname=tmp, dpi=100))
        
        # 4. 上傳至 Imgur (加強報錯版本)
        with open(tmp, "rb") as f:
            r = requests.post(
                "https://api.imgur.com/3/image", 
                headers={"Authorization": f"Client-ID {IMGUR_CLIENT_ID}"}, 
                files={"image": f},
                verify=False # 確保 Imgur 連線不會因憑證失敗
            ).json()
        
        if r.get("success"):
            return r["data"]["link"]
        else:
            # 讓錯誤詳情不再顯示 None
            err_detail = r.get('data', {}).get('error', 'Imgur 拒絕連線')
            print(f"!!! Imgur 詳細錯誤: {r} !!!")
            return f"ERR_IMGUR: {err_detail}"
            
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
    
    # 偵測 4 位股票代碼
    if re.match(r'^\d{4}$', msg):
        line_bot_api.reply_message(event.reply_token, create_kline_panel(msg))
        return

    # 處理週期按鈕
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
            # 直接把內部錯誤噴在 LINE 上面方便偵錯
            line_bot_api.reply_message(event.reply_token, TextMessage(text=f"❌ 錯誤詳情：{result}"))

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
