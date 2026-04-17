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

# ========= 核心設定 (與之前一致) =========
LINE_ACCESS_TOKEN = "yl+8P+/NQEAvmculw5AgfS3cIQ51yV63NOeHujxxBFgZKWME6Xa0Vs/eBQw7M8/thAsy8C1Bhr0r8uuFEP312UlZI5JP2GrqeFGIb70r3ZxygFDmgyyrqYg7kaZoLsZP6q8PdJPIKnESlz2LDNI4aAdB04t89/1O/w1cDnyilFU="
LINE_HANDLER_SECRET = "a479ce8e693bd35d0dd5541964945456" 

cloudinary.config( 
  cloud_name = "dzip2nboe", 
  api_key = "124438874888122", 
  api_secret = "X71kcLFVNKX-XYjKHCbCnMFAzCw" 
)

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_HANDLER_SECRET)

# ========= 建立名稱轉代碼的對照表 =========
# twstock.codes 包含所有台股資訊
def get_stock_id(name_or_id):
    name_or_id = name_or_id.upper().strip()
    
    # 如果已經是 4 位以上數字，直接回傳
    if re.match(r'^\d{4,6}$', name_or_id):
        return name_or_id
    
    # 否則在 twstock 代碼表中搜尋名稱
    for sid, info in twstock.codes.items():
        if info.name == name_or_id:
            return sid
    return None

def get_kline_url(sid):
    try:
        plt.switch_backend('Agg')
        stock = twstock.Stock(sid)
        raw_data = stock.fetch_31() 
        
        if not raw_data:
            return "交易所連線繁忙或代碼錯誤"

        # 使用屬性提取法建立 DataFrame
        df_final = pd.DataFrame([
            {'Date': d.date, 'Open': d.open, 'High': d.high, 'Low': d.low, 'Close': d.close, 'Volume': d.capacity} 
            for d in raw_data
        ])
        
        df_final['Date'] = pd.to_datetime(df_final['Date'])
        df_final.set_index('Date', inplace=True)
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            df_final[col] = pd.to_numeric(df_final[col], errors='coerce')
        df_final = df_final.dropna()

        if df_final.empty: return "資料量不足"

        mc = mpf.make_marketcolors(up='red', down='green', edge='inherit', wick='inherit', volume='inherit')
        s = mpf.make_mpf_style(marketcolors=mc, gridstyle='--', y_on_right=True)

        tmp_path = "/tmp/k.png"
        fig, axes = mpf.plot(df_final.tail(24), type='candle', style=s, volume=True, 
                             mav=(5, 10), figsize=(10, 8), returnfig=True,
                             datetime_format='%m/%d', tight_layout=True)
        
        last_price = float(df_final['Close'].iloc[-1])
        stock_name = twstock.codes[sid].name if sid in twstock.codes else ""
        fig.text(0.05, 0.95, f"{sid} {stock_name}  Last: {last_price:.2f}", fontsize=20, weight='bold', color='red')

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
    
    # 處理按鈕回傳的「XXXX 日線」訊息
    if "日線" in msg:
        sid = msg.split(" ")[0]
        url = get_kline_url(sid)
        if url and url.startswith("http"):
            line_bot_api.reply_message(event.reply_token, ImageSendMessage(original_content_url=url, preview_image_url=url))
        else:
            line_bot_api.reply_message(event.reply_token, TextMessage(text=f"⚠️ {url}"))
        return

    # 處理使用者輸入 (名稱或代碼)
    sid = get_stock_id(msg)
    if sid:
        line_bot_api.reply_message(event.reply_token, create_kline_panel(sid))
    else:
        # 沒找到代碼時的回應
        line_bot_api.reply_message(event.reply_token, TextMessage(text=f"抱歉，找不到「{msg}」相關的股票資訊。"))

def create_kline_panel(sid):
    # 取得股票名稱
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
