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
import cloudinary
import cloudinary.uploader

app = Flask(__name__)

# ========= 核心設定區 =========
LINE_ACCESS_TOKEN = "zGojeXY7W+OOc+H+hpbohy6c2ZVw352Tr7V4iWm7luvYkFOqOZhjdqA4aVAU6X3fhAsy8C1Bhr0r8uuFEP312UlZI5JP2GrqeFGIb70r3ZxCW6mOW2S1k/2wuiLsE4u1UwhNQPKKRfXExBz0i/T5rAdB04t89/1O/w1cDnyilFU="
LINE_HANDLER_SECRET = "f3187d1658e4e7f172cd19fddda08a36" 

# Cloudinary 認證參數 (保證上傳成功，取代會 403/429 的 Imgur)
cloudinary.config( 
  cloud_name = "dihp3v6st", 
  api_key = "634351368739198", 
  api_secret = "RAn_VByw_qfT5O6Kx-S-zZ623rY" 
)

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_HANDLER_SECRET)

def get_kline_url(sid):
    try:
        # 1. 使用 yfinance 抓取資料 (避開證交所 403 封鎖)
        stock_id = f"{sid}.TW"
        df = yf.download(stock_id, period="3mo", interval="1d", progress=False)
        
        if df.empty:
            # 如果 .TW 抓不到，嘗試 .TWO (上櫃股票)
            df = yf.download(f"{sid}.TWO", period="3mo", interval="1d", progress=False)
            if df.empty: return "找不到該股票資料"

        # 2. 繪圖設定 (不使用中文字體，徹底解決 0x2 錯誤)
        mc = mpf.make_marketcolors(up='red', down='green', edge='inherit', wick='inherit', volume='inherit')
        s = mpf.make_mpf_style(marketcolors=mc, gridstyle='--', y_on_right=True)

        tmp_path = "/tmp/k.png"
        # 繪製 K 線、交易量與 5/20/60 均線
        fig, axes = mpf.plot(df.tail(60), type='candle', style=s, volume=True, 
                             mav=(5, 20, 60), figsize=(10, 8), returnfig=True,
                             datetime_format='%m/%d', tight_layout=True)
        
        # 標題使用英文，避免中文字體導致的崩潰
        last_price = df['Close'].iloc[-1]
        fig.text(0.1, 0.94, f"STOCK: {sid}", fontsize=22, weight='bold')
        fig.text(0.1, 0.89, f"Price: {last_price:.2f}", fontsize=18, color='red')

        fig.savefig(tmp_path, dpi=100, bbox_inches='tight')
        plt.close(fig)

        # 3. 上傳至 Cloudinary (取代 Imgur，解決上傳失敗問題)
        upload_res = cloudinary.uploader.upload(tmp_path)
        return upload_res.get("secure_url")

    except Exception as e:
        return f"系統異常: {str(e)}"

# ========= LINE Bot 邏輯 =========
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
    # 只要輸入 4 位數代碼就跳選單
    if re.match(r'^\d{4}$', msg):
        line_bot_api.reply_message(event.reply_token, create_kline_panel(msg))
    # 處理點擊按鈕後的邏輯
    elif "日線" in msg:
        sid = msg.split(" ")[0]
        url = get_kline_url(sid)
        if url.startswith("http"):
            line_bot_api.reply_message(event.reply_token, ImageSendMessage(original_content_url=url, preview_image_url=url))
        else:
            line_bot_api.reply_message(event.reply_token, TextMessage(text=f"⚠️ {url}"))

def create_kline_panel(sid):
    return FlexSendMessage(
        alt_text=f"股票 {sid} 選單",
        contents={
          "type": "bubble",
          "body": {
            "type": "box", "layout": "vertical", "contents": [
              {"type": "text", "text": f"📈 查詢股票: {sid}", "weight": "bold", "size": "xl"},
              {"type": "button", "style": "primary", "margin": "md", "color": "#007bff", 
               "action": {"type": "message", "label": "生成日 K 線圖", "text": f"{sid} 日線"}}
            ]
          }
        }
    )

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
