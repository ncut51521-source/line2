import os, re, requests, urllib3, datetime
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

# ========= 設定區 (請確認這兩項正確) =========
LINE_ACCESS_TOKEN = "zGojeXY7W+OOc+H+hpbohy6c2ZVw352Tr7V4iWm7luvYkFOqOZhjdqA4aVAU6X3fhAsy8C1Bhr0r8uuFEP312UlZI5JP2GrqeFGIb70r3ZxCW6mOW2S1k/2wuiLsE4u1UwhNQPKKRfXExBz0i/T5rAdB04t89/1O/w1cDnyilFU="
LINE_HANDLER_SECRET = "f3187d1658e4e7f172cd19fddda08a36" 

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_HANDLER_SECRET)

def get_kline_url(sid):
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        # 1. 抓取資料 (只抓最近一個月，最快)
        today = datetime.date.today().strftime("%Y%m01")
        url = f"https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date={today}&stockNo={sid}"
        res_raw = requests.get(url, headers=headers, timeout=10, verify=False)
        
        # 檢查是否為 JSON
        try:
            res = res_raw.json()
        except:
            return "❌ 證交所 API 忙碌中，請稍後再試。"

        if res.get("stat") != "OK": return f"❌ 找不到股票 {sid} 的資料"
        
        # 2. 處理資料
        df = pd.DataFrame([row[:9] for row in res["data"]], columns=["date","cap","tur","open","high","low","close","chg","tra"])
        df["date"] = df["date"].apply(lambda d: f"{int(d.split('/')[0])+1911}-{d.split('/')[1]}-{d.split('/')[2]}")
        df = df.rename(columns={"date":"Date","open":"Open","high":"High","low":"Low","close":"Close","cap":"Volume"})
        df["Date"] = pd.to_datetime(df["Date"])
        for col in ["Open","High","Low","Close","Volume"]:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(",",""), errors='coerce')
        df = df.sort_values("Date").set_index("Date")

        # 3. 繪圖 (完全不使用中文字體，避免 0x2 錯誤)
        mc = mpf.make_marketcolors(up='#E74C3C', down='#2ECC71', edge='inherit', wick='inherit', volume='inherit')
        s = mpf.make_mpf_style(marketcolors=mc, gridstyle='--', gridcolor='#f0f0f0')

        tmp_path = "/tmp/stock_plot.png"
        fig, axes = mpf.plot(df.tail(25), type='candle', style=s, volume=True, figsize=(8, 6),
                             returnfig=True, datetime_format='%m/%d')
        
        # 標題使用純英文代碼
        fig.text(0.1, 0.9, f"STOCK: {sid}", fontsize=20, weight='bold')
        fig.savefig(tmp_path, dpi=80, bbox_inches='tight')
        plt.close(fig)

        # 4. 上傳到 Postimages (匿名免 Key 上傳)
        with open(tmp_path, "rb") as f:
            # 這是 Postimages 的匿名上傳介面邏輯
            files = {'file': ('stock.png', f, 'image/png')}
            data = {'optsize': '0', 'expire': '0', 'session': 'anonymous'}
            up_res = requests.post("https://postimages.org/json/rr", files=files, data=data, timeout=20)
            
            if up_res.status_code == 200:
                # 取得直接圖片連結
                return up_res.json().get('url')
            else:
                return f"⚠️ 圖片傳失敗，狀態碼: {up_res.status_code}"

    except Exception as e:
        return f"⚠️ 系統異常: {str(e)}"

# --- Webhook 與 Line 訊息處理 ---
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
        img_url = get_kline_url(sid)
        if img_url and img_url.startswith("http"):
            line_bot_api.reply_message(event.reply_token, ImageSendMessage(original_content_url=img_url, preview_image_url=img_url))
        else:
            line_bot_api.reply_message(event.reply_token, TextMessage(text=img_url))

def create_kline_panel(sid):
    return FlexSendMessage(
        alt_text=f"股票 {sid} 選單",
        contents={
          "type": "bubble",
          "body": {
            "type": "box", "layout": "vertical", "contents": [
              {"type": "text", "text": f"查詢代碼: {sid}", "weight": "bold", "size": "xl"},
              {"type": "button", "style": "primary", "margin": "md", "color": "#28a745", "action": {"type": "message", "label": "生成 K 線圖", "text": f"{sid} 日線"}}
            ]
          }
        }
    )

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
