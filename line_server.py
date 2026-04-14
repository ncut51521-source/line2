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

# 禁用 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# ========= 設定區 =========
LINE_ACCESS_TOKEN = "zGojeXY7W+OOc+H+hpbohy6c2ZVw352Tr7V4iWm7luvYkFOqOZhjdqA4aVAU6X3fhAsy8C1Bhr0r8uuFEP312UlZI5JP2GrqeFGIb70r3ZxCW6mOW2S1k/2wuiLsE4u1UwhNQPKKRfXExBz0i/T5rAdB04t89/1O/w1cDnyilFU="
LINE_HANDLER_SECRET = "f3187d1658e4e7f172cd19fddda08a36" 
IMGUR_CLIENT_ID = "54d96d74494c8e7"

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_HANDLER_SECRET)

def get_stock_name(sid):
    """從證交所 API 抓取股票名稱"""
    try:
        query_url = f"https://www.twse.com.tw/zh/api/codeQuery?query={sid}"
        res = requests.get(query_url, verify=False, timeout=5).json()
        if res.get("suggestions"):
            # 格式通常是 "2330 台積電"
            full_name = res["suggestions"][0]
            return full_name
        return sid # 抓不到就回傳代碼
    except:
        return sid

def get_kline_url(sid, label):
    headers = {'User-Agent': 'Mozilla/5.0'}
    all_rows = []
    
    # 取得股票完整名稱
    stock_full_name = get_stock_name(sid)
    
    try:
        today = datetime.date.today()
        for i in range(3):
            target_date = (today - datetime.timedelta(days=i*30)).strftime("%Y%m01")
            url = f"https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date={target_date}&stockNo={sid}"
            res = requests.get(url, headers=headers, timeout=10, verify=False).json()
            if res.get("stat") == "OK": all_rows.extend(res["data"])
        
        if not all_rows: return "ERR_DATA: 找不到該股票資料"

        df = pd.DataFrame([row[:9] for row in all_rows], 
                          columns=["date","cap","tur","open","high","low","close","chg","tra"])
        df["date"] = df["date"].apply(lambda d: f"{int(d.split('/')[0])+1911}-{d.split('/')[1]}-{d.split('/')[2]}")
        df = df.rename(columns={"date":"Date","open":"Open","high":"High","low":"Low","close":"Close","cap":"Volume"})
        df["Date"] = pd.to_datetime(df["Date"])
        for col in ["Open","High","Low","Close","Volume"]:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(",",""), errors='coerce')
        df = df.sort_values("Date").drop_duplicates("Date").set_index("Date")

        last_item = df.iloc[-1]
        prev_close = df['Close'].iloc[-2]
        current_price = last_item['Close']
        diff = current_price - prev_close
        diff_pct = (diff / prev_close) * 100
        main_color = '#E74C3C' if diff >= 0 else '#2ECC71' # 紅漲綠跌

        ma5 = df['Close'].rolling(5).mean().iloc[-1]
        ma20 = df['Close'].rolling(20).mean().iloc[-1]
        ma60 = df['Close'].rolling(60).mean().iloc[-1]

        mc = mpf.make_marketcolors(up='#E74C3C', down='#2ECC71', edge='inherit', wick='inherit', volume='inherit')
        s = mpf.make_mpf_style(marketcolors=mc, gridstyle='--', gridcolor='#f0f0f0', y_on_right=True, facecolor='white')

        tmp = "/tmp/kline.png"
        fig, axes = mpf.plot(df.tail(45), type='candle', style=s, volume=True, 
                             mav=(5, 20, 60), returnfig=True, figsize=(10, 10),
                             tight_layout=True, datetime_format='%m/%d',
                             volume_panel=1, panel_ratios=(6, 2))
        
        # 標題改為：代碼 + 名稱 (例如 2330 台積電)
        fig.text(0.05, 0.95, stock_full_name, fontsize=28, weight='bold', color='#2c3e50')
        
        # 價格與漲跌資訊
        fig.text(0.05, 0.89, f"{current_price:g}", fontsize=48, color=main_color, weight='bold')
        sign = "+" if diff > 0 else ""
        fig.text(0.35, 0.89, f"{sign}{diff:g} ({sign}{diff_pct:.2f}%)", fontsize=22, color=main_color)
        
        # 均線數值
        fig.text(0.05, 0.85, f"5MA {ma5:.1f}", color='#3498DB', fontsize=12, weight='bold')
        fig.text(0.25, 0.85, f"20MA {ma20:.1f}", color='#F39C12', fontsize=12, weight='bold')
        fig.text(0.45, 0.85, f"60MA {ma60:.1f}", color='#2ECC71', fontsize=12, weight='bold')

        fig.savefig(tmp, dpi=120, bbox_inches='tight', pad_inches=0.1, facecolor='white')
        plt.close(fig)

        with open(tmp, "rb") as f:
            r = requests.post("https://api.imgur.com/3/image", 
                              headers={"Authorization": f"Client-ID {IMGUR_CLIENT_ID}"}, 
                              files={"image": f}, verify=False).json()
        
        return r["data"]["link"] if r.get("success") else f"ERR_IMGUR: {r.get('data', {}).get('error')}"
    except Exception as e:
        return f"ERR_SYSTEM: {str(e)}"

# --- 以下邏輯維持不變 ---
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
    elif re.match(r'^(\d{4})\s+(.*)$', msg):
        sid, label = re.match(r'^(\d{4})\s+(.*)$', msg).groups()
        result = get_kline_url(sid, label)
        if result.startswith("http"):
            line_bot_api.reply_message(event.reply_token, ImageSendMessage(original_content_url=result, preview_image_url=result))
        else:
            line_bot_api.reply_message(event.reply_token, TextMessage(text=f"❌ {result}"))

def create_kline_panel(sid):
    return FlexSendMessage(
        alt_text=f"股票 {sid} 選單",
        contents={
          "type": "bubble",
          "body": {
            "type": "box", "layout": "vertical", "spacing": "md",
            "contents": [
              {"type": "text", "text": f"📈 股票查詢: {sid}", "weight": "bold", "size": "xl"},
              {"type": "button", "style": "primary", "color": "#E74C3C", "action": {"type": "message", "label": "查看日線 K 線圖", "text": f"{sid} 日線"}}
            ]
          }
        }
    )

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
