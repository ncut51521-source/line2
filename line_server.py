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
import twstock
import cloudinary
import cloudinary.uploader

app = Flask(__name__)

# ========= 核心設定 (請確認與你 Render 設定一致) =========
LINE_ACCESS_TOKEN = "yl+8P+/NQEAvmculw5AgfS3cIQ51yV63NOeHujxxBFgZKWME6Xa0Vs/eBQw7M8/thAsy8C1Bhr0r8uuFEP312UlZI5JP2GrqeFGIb70r3ZxygFDmgyyrqYg7kaZoLsZP6q8PdJPIKnESlz2LDNI4aAdB04t89/1O/w1cDnyilFU="
LINE_HANDLER_SECRET = "a479ce8e693bd35d0dd5541964945456" 

cloudinary.config( 
  cloud_name = "dzip2nboe", 
  api_key = "124438874888122", 
  api_secret = "X71kcLFVNKX-XYjKHCbCnMFAzCw" 
)

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_HANDLER_SECRET)

def get_kline_url(sid):
    try:
        plt.switch_backend('Agg')
        
        # --- 核心改變：使用 twstock 直接抓取台灣交易所數據 (避開 Yahoo 封鎖) ---
        stock = twstock.Stock(sid)
        raw_data = stock.fetch_31() # 抓取最近 31 筆
        
        if not raw_data:
            return "交易所連線繁忙或代碼錯誤，請稍後再試"

        # 轉換成 pandas DataFrame
        df = pd.DataFrame(raw_data)
        # twstock 原始欄位順序: Date, Capacity, Turnover, Open, High, Low, Close, Change, Transaction
        df.columns = ['Date', 'Capacity', 'Turnover', 'Open', 'High', 'Low', 'Close', 'Change', 'Transaction']
        df['Date'] = pd.to_datetime(df['Date'])
        df.set_index('Date', inplace=True)

        # 確保數據類型正確
        for col in ['Open', 'High', 'Low', 'Close', 'Capacity']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df = df.dropna()

        # 繪圖設定
        mc = mpf.make_marketcolors(up='red', down='green', edge='inherit', wick='inherit', volume='inherit')
        s = mpf.make_mpf_style(marketcolors=mc, gridstyle='--', y_on_right=True)

        tmp_path = "/tmp/k.png"
        # 畫最近 24 根 K 線
        fig, axes = mpf.plot(df.tail(24), type='candle', style=s, volume=True, 
                             mav=(5, 10), figsize=(10, 8), returnfig=True,
                             datetime_format='%m/%d', tight_layout=True)
        
        last_price = float(df['Close'].iloc[-1])
        fig.text(0.05, 0.95, f"STOCK: {sid}", fontsize=22, weight='bold')
        fig.text(0.05, 0.90, f"Last: {last_price:.2f}", fontsize=18, color='red')

        fig.savefig(tmp_path, dpi=100, bbox_inches='tight')
        plt.close(fig)

        # 上傳到 Cloudinary
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
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
