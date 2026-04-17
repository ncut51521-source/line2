import os, re, datetime
import matplotlib
matplotlib.use('Agg') # 必備：伺服器環境繪圖不顯示視窗
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

# ========= 核心設定 (請確認與你的 LINE/Cloudinary 後台一致) =========
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
        stock = twstock.Stock(sid)
        raw_data = stock.fetch_31() 
        
        if not raw_data:
            return "交易所連線繁忙或代碼錯誤，請稍後再試"

        # --- 核心修正：使用屬性提取法建立 DataFrame，避免欄位數量不符錯誤 ---
        df_final = pd.DataFrame([
            {
                'Date': d.date,
                'Open': d.open,
                'High': d.high,
                'Low': d.low,
                'Close': d.close,
                'Volume': d.capacity
            } for d in raw_data
        ])
        
        df_final['Date'] = pd.to_datetime(df_final['Date'])
        df_final.set_index('Date', inplace=True)

        # 確保數據類型為數值
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            df_final[col] = pd.to_numeric(df_final[col], errors='coerce')
        df_final = df_final.dropna()

        if df_final.empty:
            return "該股票目前無足夠交易資料"

        # 繪圖風格設定 (台股傳統：紅漲綠跌)
        mc = mpf.make_marketcolors(up='red', down='green', edge='inherit', wick='inherit', volume='inherit')
        s = mpf.make_mpf_style(marketcolors=mc, gridstyle='--', y_on_right=True)

        tmp_path = "/tmp/k.png"
        # 畫最近 24 根 K 線 (約一個月交易日)
        fig, axes = mpf.plot(df_final.tail(24), type='candle', style=s, volume=True, 
                             mav=(5, 10), figsize=(10, 8), returnfig=True,
                             datetime_format='%m/%d', tight_layout=True)
        
        last_price = float(df_final['Close'].iloc[-1])
        fig.text(0.05, 0.95, f"STOCK: {sid}  Last Price: {last_price:.2f}", 
                 fontsize=20, weight='bold', color='red')

        fig.savefig(tmp_path, dpi=100, bbox_inches='tight')
        plt.close(fig)

        # 上傳到 Cloudinary 圖床
        upload_res = cloudinary.uploader.upload(tmp_path)
        return upload_res.get("secure_url")

    except Exception as e:
        return f"生成圖表失敗: {str(e)}"

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
        if url and url.startswith("http"):
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
              {"type": "text", "text": f"📈 股票代碼: {sid}", "weight": "bold", "size": "xl"},
              {"type": "button", "style": "primary", "margin": "md", "color": "#007bff", 
               "action": {"type": "message", "label": "查看日 K 線圖", "text": f"{sid} 日線"}}
            ]
          }
        }
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
