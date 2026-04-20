import os, re, datetime
import matplotlib
matplotlib.use('Agg') 
import matplotlib.pyplot as plt
from matplotlib import font_manager
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, ImageSendMessage, FlexSendMessage
import pandas as pd
import mplfinance as mpf
import twstock
import cloudinary
import cloudinary.uploader

app = Flask(__name__)

# ========= 核心設定 (LINE & Cloudinary) =========
LINE_ACCESS_TOKEN = "yl+8P+/NQEAvmculw5AgfS3cIQ51yV63NOeHujxxBFgZKWME6Xa0Vs/eBQw7M8/thAsy8C1Bhr0r8uuFEP312UlZI5JP2GrqeFGIb70r3ZxygFDmgyyrqYg7kaZoLsZP6q8PdJPIKnESlz2LDNI4aAdB04t89/1O/w1cDnyilFU="
LINE_HANDLER_SECRET = "a479ce8e693bd35d0dd5541964945456" 

cloudinary.config( 
  cloud_name = "dzip2nboe", 
  api_key = "124438874888122", 
  api_secret = "X71kcLFVNKX-XYjKHCbCnMFAzCw" 
)

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_HANDLER_SECRET)

# ========= 名稱轉代碼邏輯 =========
def get_stock_id(name_or_id):
    name_or_id = name_or_id.upper().strip()
    if re.match(r'^\d{4,6}$', name_or_id):
        return name_or_id
    for sid, info in twstock.codes.items():
        if info.name == name_or_id:
            return sid
    return None

# ========= 核心 K 線圖生成函式 =========
def get_kline_url(sid, period='D'):
    try:
        plt.switch_backend('Agg')
        font_path = os.path.join(os.path.dirname(__file__), "NotoSansCJKtc-Regular.otf")
        my_font = font_manager.FontProperties(fname=font_path) if os.path.exists(font_path) else None

        # 1. 抓取 K 線歷史資料
        stock = twstock.Stock(sid)
        if period == 'D':
            raw_data = stock.fetch_31()
            title_tag = "日線"
        else:
            raw_data = stock.fetch(2024, 1) 
            title_tag = "週線" if period == 'W' else "月線"

        if not raw_data: return "查無資料"

        # 2. 抓取「即時」價格資訊 (顯示於圖片頂部)
        rt_data = twstock.realtime.get(sid)
        rt_price_text = ""
        rt_color = "black"
        if rt_data['success'] and rt_data['realtime']['latest_trade_price'] != '-':
            curr = float(rt_data['realtime']['latest_trade_price'])
            prev = float(rt_data['realtime']['open']) # 以開盤價計算當日漲跌幅
            diff = curr - prev
            diff_pct = (diff / prev) * 100
            rt_color = "red" if diff > 0 else ("green" if diff < 0 else "black")
            rt_price_text = f"目前價格: {curr} ({'+' if diff > 0 else ''}{diff:.2f}, {diff_pct:.2f}%)"

        # 3. 資料處理與週期轉換
        df = pd.DataFrame([{'Date': d.date, 'Open': d.open, 'High': d.high, 'Low': d.low, 'Close': d.close, 'Volume': d.capacity} for d in raw_data])
        df['Date'] = pd.to_datetime(df['Date'])
        df.set_index('Date', inplace=True)
        if period == 'W':
            df = df.resample('W').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna()
        elif period == 'M':
            df = df.resample('M').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna()

        # 4. 繪圖
        plot_df = df.tail(24)
        mc = mpf.make_marketcolors(up='red', down='green', edge='inherit', wick='inherit', volume='inherit')
        s = mpf.make_mpf_style(marketcolors=mc, gridstyle='--', y_on_right=True)
        tmp_path = "/tmp/k.png"
        fig, axes = mpf.plot(plot_df, type='candle', style=s, volume=True, mav=(5, 10), figsize=(12, 10), returnfig=True, datetime_format='%m/%d', tight_layout=False)
        
        # 5. 在圖片頂部繪製文字
        stock_name = twstock.codes[sid].name if sid in twstock.codes else ""
        # 標題
        fig.text(0.08, 0.96, f"{sid} {stock_name} ({title_tag})", fontsize=28, weight='black', fontproperties=my_font)
        # 即時股價與漲跌 (加在這裡！)
        fig.text(0.08, 0.92, rt_price_text, fontsize=24, weight='bold', color=rt_color, fontproperties=my_font)

        plt.subplots_adjust(top=0.90)
        fig.savefig(tmp_path, dpi=100, bbox_inches='tight')
        plt.close(fig)

        upload_res = cloudinary.uploader.upload(tmp_path)
        return upload_res.get("secure_url")
    except Exception as e:
        return f"生成失敗: {str(e)}"

# ========= LINE Bot 回應邏輯 =========
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
    
    if any(k in msg for k in ["日線", "週線", "月線"]):
        parts = msg.split(" ")
        sid = parts[0]
        mode = 'W' if "週線" in msg else ('M' if "月線" in msg else 'D')
        url = get_kline_url(sid, period=mode)
        if url and url.startswith("http"):
            line_bot_api.reply_message(event.reply_token, ImageSendMessage(original_content_url=url, preview_image_url=url))
        else:
            line_bot_api.reply_message(event.reply_token, TextMessage(text=f"⚠️ {url}"))
        return

    sid = get_stock_id(msg)
    if sid:
        line_bot_api.reply_message(event.reply_token, create_kline_panel(sid))
    else:
        line_bot_api.reply_message(event.reply_token, TextMessage(text=f"找不到「{msg}」相關股票"))

def create_kline_panel(sid):
    name = twstock.codes[sid].name if sid in twstock.codes else "未知"
    return FlexSendMessage(
        alt_text=f"股票 {sid} {name}",
        contents={
          "type": "bubble",
          "body": {
            "type": "box", "layout": "vertical", "spacing": "md", "contents": [
              {"type": "text", "text": f"📈 {sid} {name}", "weight": "bold", "size": "xl", "align": "center"},
              {"type": "separator"},
              {"type": "button", "style": "primary", "color": "#007bff", "action": {"type": "message", "label": "查看日 K 線", "text": f"{sid} 日線"}},
              {"type": "button", "style": "primary", "color": "#28a745", "action": {"type": "message", "label": "查看週 K 線", "text": f"{sid} 週線"}},
              {"type": "button", "style": "primary", "color": "#fd7e14", "action": {"type": "message", "label": "查看月 K 線", "text": f"{sid} 月線"}}
            ]
          }
        }
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
