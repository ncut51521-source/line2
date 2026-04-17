import os, re, datetime
import matplotlib
matplotlib.use('Agg') 
import matplotlib.pyplot as plt
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, ImageSendMessage, FlexSendMessage
import pandas as pd
import mplfinance as mpf
import yfinance as yf
import twstock
import cloudinary
import cloudinary.uploader

app = Flask(__name__)

# ========= 核心設定區 =========
LINE_ACCESS_TOKEN = "zGojeXY7W+OOc+H+hpbohy6c2ZVw352Tr7V4iWm7luvYkFOqOZhjdqA4aVAU6X3fhAsy8C1Bhr0r8uuFEP312UlZI5JP2GrqeFGIb70r3ZxCW6mOW2S1k/2wuiLsE4u1UwhNQPKKRfXExBz0i/T5rAdB04t89/1O/w1cDnyilFU="
LINE_HANDLER_SECRET = "f3187d1658e4e7f172cd19fddda08a36" 

cloudinary.config( 
  cloud_name = "dihp3v6st", 
  api_key = "634351368739198", 
  api_secret = "RAn_VByw_qfT5O6Kx-S-zZ623rY" 
)

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_HANDLER_SECRET)

def get_kline_url(sid):
    try:
        plt.switch_backend('Agg')
        df = pd.DataFrame()

        # --- 策略 A: 先試 twstock (對台股最穩定) ---
        try:
            stock = twstock.Stock(sid)
            # 抓取最近 31 筆資料
            raw_data = stock.fetch_31()
            if raw_data:
                df = pd.DataFrame(raw_data)
                # twstock 欄位轉換
                df.columns = ['Date', 'Capacity', 'Turnover', 'Open', 'High', 'Low', 'Close', 'Change', 'Transaction']
                df['Date'] = pd.to_datetime(df['Date'])
                df.set_index('Date', inplace=True)
        except Exception as e:
            print(f"twstock error: {e}")

        # --- 策略 B: 如果 twstock 失敗，才試 yfinance (並處理 MultiIndex) ---
        if df.empty:
            df = yf.download(f"{sid}.TW", period="1mo", interval="1d", progress=False, auto_adjust=True)
            if df.empty:
                df = yf.download(f"{sid}.TWO", period="1mo", interval="1d", progress=False, auto_adjust=True)
            
            if not df.empty:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)

        # 檢查最終資料
        if df.empty:
            return "交易所連線繁忙，請稍後再試 (IP Blocked)"

        # 數據清洗
        df = df.dropna()
        for col in ["Open", "High", "Low", "Close"]:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df = df.dropna()

        # 繪圖設定 (台股傳統：紅漲綠跌)
        mc = mpf.make_marketcolors(up='red', down='green', edge='inherit', wick='inherit', volume='inherit')
        s = mpf.make_mpf_style(marketcolors=mc, gridstyle='--', y_on_right=True)

        tmp_path = "/tmp/k.png"
        # 畫最近 24 根 K 線 (約一個月交易日)
        fig, axes = mpf.plot(df.tail(24), type='candle', style=s, volume=True, 
                             mav=(5, 10), figsize=(10, 8), returnfig=True,
                             datetime_format='%m/%d', tight_layout=True)
        
        last_price = float(df['Close'].iloc[-1])
        fig.text(0.05, 0.95, f"STOCK: {sid}", fontsize=22, weight='bold')
        fig.text(0.05, 0.90, f"Last: {last_price:.2f}", fontsize=18, color='red')

        fig.savefig(tmp_path, dpi=100, bbox_inches='tight')
        plt.close(fig)

        # 上傳圖床
        upload_res = cloudinary.uploader.upload(tmp_path)
        return upload_res.get("secure_url")

    except Exception as e:
        return f"系統錯誤: {str(e)}"

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
    elif "日線" in msg:
        sid = msg.split(" ")[0]
        url = get_kline_url(sid)
        if url.startswith("http"):
            line_bot_api.reply_message(
                event.reply_token, 
                ImageSendMessage(original_content_url=url, preview_image_url=url)
            )
        else:
            line_bot_api.reply_message(event.reply_token, TextMessage(text=f"⚠️ {url}"))

def create_kline_panel(sid):
    return FlexSendMessage(
        alt_text=f"股票 {sid} 選單",
        contents={
          "type": "bubble",
          "body": {
            "type": "box", "layout": "vertical", "contents": [
              {"type": "text", "text": f"📈 查詢代碼: {sid}", "weight": "bold", "size": "xl"},
              {"type": "button", "style": "primary", "margin": "md", "color": "#007bff", 
               "action": {"type": "message", "label": "生成日 K 線圖", "text": f"{sid} 日線"}}
            ]
          }
        }
    )

if __name__ == "__main__":
    # Render 會自動給予 PORT 環境變數
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
