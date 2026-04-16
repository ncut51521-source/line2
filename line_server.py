import os, re
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

# ========= 核心設定 =========
LINE_ACCESS_TOKEN = "yl+8P+/NQEAvmculw5AgfS3cIQ51yV63NOeHujxxBFgZKWME6Xa0Vs/eBQw7M8/thAsy8C1Bhr0r8uuFEP312UlZI5JP2GrqeFGIb70r3ZxygFDmgyyrqYg7kaZoLsZP6q8PdJPIKnESlz2LDNI4aAdB04t89/1O/w1cDnyilFU="
LINE_HANDLER_SECRET = "a479ce8e693bd35d0dd5541964945456"

cloudinary.config(
    cloud_name="dzip2nboe",
    api_key="124438874888122",
    api_secret="X71kcLFVNKX-XYjKHCbCnMFAzCw"
)

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_HANDLER_SECRET)

# ========= 取得K線圖 =========
def get_kline_url(sid):
    try:
        # 抓資料（先上市，再上櫃）
        df = yf.download(f"{sid}.TW", period="3mo", interval="1d", progress=False)
        if df.empty:
            df = yf.download(f"{sid}.TWO", period="3mo", interval="1d", progress=False)

        if df.empty:
            return "找不到股票資料"

        # ====== 🔧 關鍵修正（避免你現在的錯誤）======
        df = df.dropna()

        for col in ["Open", "High", "Low", "Close", "Volume"]:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        df = df.dropna()

        if df.empty or len(df) < 10:
            return "資料不足，無法畫圖"
        # =========================================

        # 台股紅漲綠跌
        mc = mpf.make_marketcolors(
            up='red',
            down='green',
            edge='inherit',
            wick='inherit',
            volume='inherit'
        )
        style = mpf.make_mpf_style(
            marketcolors=mc,
            gridstyle='--',
            y_on_right=True
        )

        tmp_path = "/tmp/k.png"

        fig, axes = mpf.plot(
            df.tail(60),
            type='candle',
            style=style,
            volume=True,
            mav=(5, 20, 60),
            figsize=(10, 8),
            returnfig=True,
            datetime_format='%m/%d',
            tight_layout=True
        )

        last_price = df['Close'].iloc[-1]

        fig.text(0.05, 0.95, f"STOCK: {sid}", fontsize=20, weight='bold')
        fig.text(0.05, 0.90, f"Last: {last_price:.2f}", fontsize=16, color='red')

        fig.savefig(tmp_path, dpi=100, bbox_inches='tight')
        plt.close(fig)

        # 上傳圖床
        res = cloudinary.uploader.upload(tmp_path)
        return res.get("secure_url")

    except Exception as e:
        return f"系統錯誤: {str(e)}"


# ========= LINE Webhook =========
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'


# ========= 訊息處理 =========
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text.strip()

    # 輸入股票代碼（例如 2330）
    if re.match(r'^\d{4}$', msg):
        line_bot_api.reply_message(
            event.reply_token,
            create_kline_panel(msg)
        )

    # 生成K線
    elif "日線" in msg:
        sid = msg.split(" ")[0]
        url = get_kline_url(sid)

        if url.startswith("http"):
            line_bot_api.reply_message(
                event.reply_token,
                ImageSendMessage(
                    original_content_url=url,
                    preview_image_url=url
                )
            )
        else:
            line_bot_api.reply_message(
                event.reply_token,
                TextMessage(text=f"⚠️ {url}")
            )


# ========= 按鈕UI =========
def create_kline_panel(sid):
    return FlexSendMessage(
        alt_text=f"股票 {sid}",
        contents={
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": f"📈 查詢代碼: {sid}",
                        "weight": "bold",
                        "size": "xl"
                    },
                    {
                        "type": "button",
                        "style": "primary",
                        "margin": "md",
                        "color": "#007bff",
                        "action": {
                            "type": "message",
                            "label": "生成日 K 線圖",
                            "text": f"{sid} 日線"
                        }
                    }
                ]
            }
        }
    )


# ========= 啟動 =========
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
