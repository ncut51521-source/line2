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

# ========= 設定區 =========
LINE_ACCESS_TOKEN = "zGojeXY7W+OOc+H+hpbohy6c2ZVw352Tr7V4iWm7luvYkFOqOZhjdqA4aVAU6X3fhAsy8C1Bhr0r8uuFEP312UlZI5JP2GrqeFGIb70r3ZxCW6mOW2S1k/2wuiLsE4u1UwhNQPKKRfXExBz0i/T5rAdB04t89/1O/w1cDnyilFU="
LINE_HANDLER_SECRET = "f3187d1658e4e7f172cd19fddda08a36" 
IMGUR_CLIENT_ID = "54d96d74494c8e7"

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_HANDLER_SECRET)

def get_kline_url(sid, label):
    headers = {'User-Agent': 'Mozilla/5.0'}
    all_rows = []
    try:
        # 抓取近三個月資料以計算長波段均線
        today = datetime.date.today()
        for i in range(3):
            target_date = (today - datetime.timedelta(days=i*30)).strftime("%Y%m01")
            url = f"https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date={target_date}&stockNo={sid}"
            res = requests.get(url, headers=headers, timeout=10, verify=False).json()
            if res.get("stat") == "OK": all_rows.extend(res["data"])
        
        if not all_rows: return "ERR_DATA: 找不到資料"

        # 資料處理與格式轉換
        df = pd.DataFrame([row[:9] for row in all_rows], 
                          columns=["date","cap","tur","open","high","low","close","chg","tra"])
        df["date"] = df["date"].apply(lambda d: f"{int(d.split('/')[0])+1911}-{d.split('/')[1]}-{d.split('/')[2]}")
        df = df.rename(columns={"date":"Date","open":"Open","high":"High","low":"Low","close":"Close","cap":"Volume"})
        df["Date"] = pd.to_datetime(df["Date"])
        for col in ["Open","High","Low","Close","Volume"]:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(",",""), errors='coerce')
        df = df.sort_values("Date").drop_duplicates("Date").set_index("Date")

        # 取得最後一筆資訊用於標題欄
        last_price = df['Close'].iloc[-1]
        last_chg = df['Open'].iloc[-1] - last_price # 簡略計算漲跌
        chg_pct = (last_chg / df['Open'].iloc[-1]) * 100

        # 設定台股紅漲綠跌風格
        mc = mpf.make_marketcolors(up='red', down='green', edge='inherit', wick='inherit', volume='inherit')
        s = mpf.make_mpf_style(marketcolors=mc, gridstyle='--', y_on_right=True)

        # 繪圖並手動增加資訊文字
        tmp = "/tmp/kline.png"
        fig, axes = mpf.plot(df.tail(60), type='candle', style=s, volume=True, 
                             mav=(5, 20, 60), returnfig=True, figsize=(10, 8),
                             tight_layout=True, datetime_format='%m/%d')
        
        # 在最上方加入股票資訊 (模仿 App 標題欄)
        color = 'red' if last_chg >= 0 else 'green'
        fig.text(0.1, 0.94, f"股票 {sid}", fontsize=24, weight='bold')
        fig.text(0.1, 0.90, f"{last_price:.2f}", fontsize=32, color=color, weight='bold')
        fig.text(0.3, 0.90, f"{'+' if last_chg >= 0 else ''}{last_chg:.2f} ({chg_pct:.2f}%)", 
                 fontsize=18, color=color)
        
        # 加入均線數值標示
        fig.text(0.1, 0.86, f"5MA: {df['Close'].tail(5).mean():.2f}", color='blue', fontsize=10)
        fig.text(0.25, 0.86, f"20MA: {df['Close'].tail(20).mean():.2f}", color='orange', fontsize=10)
        fig.text(0.4, 0.86, f"60MA: {df['Close'].tail(60).mean():.2f}", color='green', fontsize=10)

        # 儲存圖片並去除所有邊框
        fig.savefig(tmp, dpi=120, bbox_inches='tight', pad_inches=0.1)
        plt.close(fig)

        # 上傳 Imgur
        with open(tmp, "rb") as f:
            r = requests.post("https://api.imgur.com/3/image", 
                              headers={"Authorization": f"Client-ID {IMGUR_CLIENT_ID}"}, 
                              files={"image": f}, verify=False).json()
        return r["data"]["link"] if r.get("success") else f"ERR_IMGUR: {r.get('data', {}).get('error')}"
    except Exception as e:
        return f"ERR_SYSTEM: {str(e)}"

# --- 以下保留原本的 LINE Bot 邏輯 ---
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
        line_bot_api.reply_message(event.reply_token, FlexSendMessage(
            alt_text=f"股票 ({msg}) 選單",
            contents={
              "type": "bubble",
              "header": {"type": "box", "layout": "vertical", "backgroundColor": "#2c3e50", "contents": [{"type": "text", "text": f"📈 查詢代碼: {msg}", "weight": "bold", "size": "xl", "color": "#ffffff"}]},
              "body": {"type": "box", "layout": "vertical", "contents": [{"type": "button", "style": "primary", "color": "#E74C3C", "action": {"type": "message", "label": "查看日線圖", "text": f"{msg} 日線"}}]}
            }
        ))
    elif re.match(r'^(\d{4})\s+(.*)$', msg):
        sid, label = re.match(r'^(\d{4})\s+(.*)$', msg).groups()
        result = get_kline_url(sid, label)
        if result.startswith("http"):
            line_bot_api.reply_message(event.reply_token, ImageSendMessage(original_content_url=result, preview_image_url=result))
        else:
            line_bot_api.reply_message(event.reply_token, TextMessage(text=f"❌ 錯誤: {result}"))

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
