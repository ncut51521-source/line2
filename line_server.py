import os, re, requests, urllib3, datetime
import matplotlib
matplotlib.use('Agg') 
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
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

# 中文字體處理
FONT_PATH = "NotoSansTC-Regular.otf"
if not os.path.exists(FONT_PATH):
    r = requests.get("https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/TraditionalChinese/NotoSansTC-Regular.otf")
    with open(FONT_PATH, "wb") as f: f.write(r.content)
my_font = fm.FontProperties(fname=FONT_PATH)

def get_stock_info(sid):
    try:
        res = requests.get(f"https://www.twse.com.tw/zh/api/codeQuery?query={sid}", verify=False).json()
        return res["suggestions"][0] if res.get("suggestions") else sid
    except: return sid

def get_kline_url(sid, period):
    headers = {'User-Agent': 'Mozilla/5.0'}
    all_rows = []
    # 抓取較長數據以支援週/月線計算
    months_to_fetch = 12 if period in ['週線', '月線'] else 5
    today = datetime.date.today()
    
    try:
        for i in range(months_to_fetch):
            target_date = (today - datetime.timedelta(days=i*30)).strftime("%Y%m01")
            url = f"https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date={target_date}&stockNo={sid}"
            res = requests.get(url, headers=headers, timeout=10, verify=False).json()
            if res.get("stat") == "OK": all_rows.extend(res["data"])
        
        if not all_rows: return "找不到資料"

        df = pd.DataFrame([row[:9] for row in all_rows], columns=["date","cap","tur","open","high","low","close","chg","tra"])
        df["date"] = df["date"].apply(lambda d: f"{int(d.split('/')[0])+1911}-{d.split('/')[1]}-{d.split('/')[2]}")
        df = df.rename(columns={"date":"Date","open":"Open","high":"High","low":"Low","close":"Close","cap":"Volume"})
        df["Date"] = pd.to_datetime(df["Date"])
        for col in ["Open","High","Low","Close","Volume"]:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(",",""), errors='coerce')
        df = df.sort_values("Date").drop_duplicates("Date").set_index("Date")

        # 根據選擇週期進行重採樣 (Resampling)
        if period == '週線':
            df = df.resample('W-FRI').agg({'Open':'first', 'High':'max', 'Low':'min', 'Close':'last', 'Volume':'sum'})
        elif period == '月線':
            df = df.resample('ME').agg({'Open':'first', 'High':'max', 'Low':'min', 'Close':'last', 'Volume':'sum'})
        
        df = df.dropna()
        last_item = df.iloc[-1]
        prev_close = df['Close'].iloc[-2]
        current_price = last_item['Close']
        diff = current_price - prev_close
        diff_pct = (diff / prev_close) * 100
        main_color = '#E74C3C' if diff >= 0 else '#2ECC71'

        # 圖表風格
        mc = mpf.make_marketcolors(up='#E74C3C', down='#2ECC71', edge='inherit', wick='inherit', volume='inherit')
        s = mpf.make_mpf_style(marketcolors=mc, gridstyle='--', gridcolor='#f0f0f0', y_on_right=True, facecolor='white')

        tmp = "/tmp/kline.png"
        # 繪圖並設定日期格式為 yyyy/mm/dd
        fig, axes = mpf.plot(df.tail(40), type='candle', style=s, volume=True, 
                             mav=(5, 20), returnfig=True, figsize=(10, 8),
                             tight_layout=True, datetime_format='%Y/%m/%d',
                             volume_panel=1, panel_ratios=(6, 2))
        
        # 左上角：名稱(代碼)
        full_name = get_stock_info(sid)
        fig.text(0.05, 0.93, f"{full_name}({sid})", fontproperties=my_font, fontsize=24, weight='bold', color='#2c3e50')
        
        # 右上角：價格與漲跌幅 (ha='right' 靠右對齊)
        sign = "+" if diff > 0 else ""
        price_text = f"{current_price:g}"
        diff_text = f"{sign}{diff:g} ({sign}{diff_pct:.2f}%)"
        fig.text(0.95, 0.93, price_text, fontsize=32, color=main_color, weight='bold', ha='right')
        fig.text(0.95, 0.88, diff_text, fontsize=18, color=main_color, ha='right')

        fig.savefig(tmp, dpi=120, bbox_inches='tight')
        plt.close(fig)

        with open(tmp, "rb") as f:
            r = requests.post("https://api.imgur.com/3/image", 
                              headers={"Authorization": f"Client-ID {IMGUR_CLIENT_ID}"}, 
                              files={"image": f}, verify=False).json()
        return r["data"]["link"] if r.get("success") else "上傳失敗"
    except Exception as e: return str(e)

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
    elif re.match(r'^(\d{4})\s+(日線|週線|月線)$', msg):
        sid, period = re.match(r'^(\d{4})\s+(日線|週線|月線)$', msg).groups()
        url = get_kline_url(sid, period)
        if url.startswith("http"):
            line_bot_api.reply_message(event.reply_token, ImageSendMessage(original_content_url=url, preview_image_url=url))
        else:
            line_bot_api.reply_message(event.reply_token, TextMessage(text=f"❌ 錯誤: {url}"))

def create_kline_panel(sid):
    return FlexSendMessage(
        alt_text=f"股票 {sid} 週期選擇",
        contents={
          "type": "bubble",
          "body": {
            "type": "box", "layout": "vertical", "spacing": "md",
            "contents": [
              {"type": "text", "text": f"📊 查詢股票: {sid}", "weight": "bold", "size": "xl"},
              {"type": "box", "layout": "horizontal", "spacing": "sm", "contents": [
                {"type": "button", "style": "primary", "color": "#E74C3C", "action": {"type": "message", "label": "日線", "text": f"{sid} 日線"}},
                {"type": "button", "style": "primary", "color": "#3498DB", "action": {"type": "message", "label": "週線", "text": f"{sid} 週線"}},
                {"type": "button", "style": "primary", "color": "#F1C40F", "action": {"type": "message", "label": "月線", "text": f"{sid} 月線"}}
              ]}
            ]
          }
        }
    )

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
