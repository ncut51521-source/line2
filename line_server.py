import os, re, datetime
import matplotlib
matplotlib.use('Agg') 
import matplotlib.pyplot as plt
from matplotlib import font_manager  # 載入字體管理工具
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

# ========= 核心設定 =========
LINE_ACCESS_TOKEN = "yl+8P+/NQEAvmculw5AgfS3cIQ51yV63NOeHujxxBFgZKWME6Xa0Vs/eBQw7M8/thAsy8C1Bhr0r8uuFEP312UlZI5JP2GrqeFGIb70r3ZxygFDmgyyrqYg7kaZoLsZP6q8PdJPIKnESlz2LDNI4aAdB04t89/1O/w1cDnyilFU="
LINE_HANDLER_SECRET = "a479ce8e693bd35d0dd5541964945456" 

cloudinary.config( 
  cloud_name = "dzip2nboe", 
  api_key = "124438874888122", 
  api_secret = "X71kcLFVNKX-XYjKHCbCnMFAzCw" 
)

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_HANDLER_SECRET)

def get_stock_id(name_or_id):
    name_or_id = name_or_id.upper().strip()
    if re.match(r'^\d{4,6}$', name_or_id):
        return name_or_id
    for sid, info in twstock.codes.items():
        if info.name == name_or_id:
            return sid
    return None

def get_kline_url(sid):
    try:
        plt.switch_backend('Agg')
        
        # --- 1. 設定中文字體 (務必確認檔名正確) ---
        font_path = os.path.join(os.path.dirname(__file__), "NotoSansTC-Regular.otf")
        if os.path.exists(font_path):
            my_font = font_manager.FontProperties(fname=font_path)
        else:
            print("警告：找不到字體檔，中文可能顯示異常")
            my_font = None

        stock = twstock.Stock(sid)
        raw_data = stock.fetch_31() 
        if not raw_data: return "交易所連線繁忙"

        # 建立數據表
        df_final = pd.DataFrame([
            {'Date': d.date, 'Open': d.open, 'High': d.high, 'Low': d.low, 'Close': d.close, 'Volume': d.capacity} 
            for d in raw_data
        ])
        df_final['Date'] = pd.to_datetime(df_final['Date'])
        df_final.set_index('Date', inplace=True)
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            df_final[col] = pd.to_numeric(df_final[col], errors='coerce')
        df_final = df_final.dropna()

        # 最新數據與名稱
        last_row = df_final.iloc[-1]
        o, h, l, c = last_row['Open'], last_row['High'], last_row['Low'], last_row['Close']
        stock_name = twstock.codes[sid].name if sid in twstock.codes else ""

        # 繪圖設定
        mc = mpf.make_marketcolors(up='red', down='green', edge='inherit', wick='inherit', volume='inherit')
        s = mpf.make_mpf_style(marketcolors=mc, gridstyle='--', y_on_right=True)

        tmp_path = "/tmp/k.png"
        fig, axes = mpf.plot(df_final.tail(24), type='candle', style=s, volume=True, 
                             mav=(5, 10), figsize=(12, 10), returnfig=True,
                             datetime_format='%m/%d', tight_layout=False)
        
        # --- 2. 顯示加粗資訊文字並套用字體 ---
        # 標題 (代碼 + 中文名稱)
        fig.text(0.08, 0.96, f"{sid} {stock_name}", fontsize=28, weight='black', color='black', fontproperties=my_font)
        
        # 數值資訊
        info_text = f"O: {o:.2f}  H: {h:.2f}  L: {l:.2f}  C: {c:.2f}"
        fig.text(0.08, 0.92, info_text, fontsize=22, weight='black', 
                 color='red' if c >= o else 'green', fontproperties=my_font)

        # 留白設定，確保文字不擋到圖表
        plt.subplots_adjust(top=0.90)

        fig.savefig(tmp_path, dpi=100, bbox_inches='tight')
        plt.close(fig)

        upload_res = cloudinary.uploader.upload(tmp_path)
        return upload_res.get("secure_url")

    except Exception as e:
        return f"生成失敗: {str(e)}"

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
    if "日線" in msg:
        sid = msg.split(" ")[0]
        url = get_kline_url(sid)
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
            "type": "box", "layout": "vertical", "contents": [
              {"type": "text", "text": f"📈 {sid} {name}", "weight": "bold", "size": "xl"},
              {"type": "button", "style": "primary", "margin": "md", "color": "#007bff", 
               "action": {"type": "message", "label": "查看日 K 線圖", "text": f"{sid} 日線"}}
            ]
          }
        }
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
