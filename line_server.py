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
# 建議將這些資訊移至環境變數以策安全
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
        # 確保後端繪圖環境穩定
        plt.switch_backend('Agg')
        
        # 嘗試下載資料，加入 auto_adjust 提升穩定性
        # 縮短為 1 個月以降低被 Yahoo 判定為爬蟲的機率
        df = yf.download(f"{sid}.TW", period="1mo", interval="1d", progress=False, auto_adjust=True)
        
        if df.empty:
            df = yf.download(f"{sid}.TWO", period="1mo", interval="1d", progress=False, auto_adjust=True)
        
        if df.empty:
            return "Yahoo 目前連線頻繁或找不到代碼，請稍後再試"

        # 【關鍵修正】處理 yfinance 新版產生的多重索引 (MultiIndex) 欄位
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # 數據清洗：移除空值並確保數值化
        df = df.dropna()
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        df = df.dropna()

        if len(df) < 5:
            return "剩餘資料量不足，無法畫圖"

        # 繪圖設定 (紅漲綠跌)
        mc = mpf.make_marketcolors(up='red', down='green', edge='inherit', wick='inherit', volume='inherit')
        s = mpf.make_mpf_style(marketcolors=mc, gridstyle='--', y_on_right=True)

        tmp_path = "/tmp/k.png"
        # 僅取最後 20 根 K 棒以加速生成與上傳
        fig, axes = mpf.plot(df.tail(20), type='candle', style=s, volume=True, 
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
        return f"系統異常: {str(e)}"

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
    # 判斷是否為四位數股票代碼
    if re.match(r'^\d{4}$', msg):
        line_bot_api.reply_message(event.reply_token, create_kline_panel(msg))
    # 判斷是否觸發日線查詢
    elif "日線" in msg:
        sid = msg.split(" ")[0]
        url = get_kline_url(sid)
        if url.startswith("http"):
            line_bot_api.reply_message(
                event.reply_token, 
                ImageSendMessage(original_content_url=url, preview_image_url=url)
            )
        else:
            line_bot_api.reply_message(
                event.reply_token, 
                TextMessage(text=f"⚠️ {url}")
            )

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
    # 使用 Render 預設的 10000 端口
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
