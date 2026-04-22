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
import twstock
import cloudinary
import cloudinary.uploader

app = Flask(__name__)

# 配置資訊
LINE_ACCESS_TOKEN = "yl+8P+/NQEAvmculw5AgfS3cIQ51yV63NOeHujxxBFgZKWME6Xa0Vs/eBQw7M8/thAsy8C1Bhr0r8uuFEP312UlZI5JP2GrqeFGIb70r3ZxygFDmgyyrqYg7kaZoLsZP6q8PdJPIKnESlz2LDNI4aAdB04t89/1O/w1cDnyilFU="
LINE_HANDLER_SECRET = "a479ce8e693bd35d0dd5541964945456"

cloudinary.config(cloud_name="dzip2nboe", api_key="124438874888122", api_secret="X71kcLFVNKX-XYjKHCbCnMFAzCw")

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_HANDLER_SECRET)

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
    
    # 修正點：使用正則表達式擷取代號
    if any(k in msg for k in ["日線", "週線", "月線"]):
        sid_match = re.search(r'\d+', msg)
        if not sid_match:
            line_bot_api.reply_message(event.reply_token, TextMessage(text="請提供正確代號，例如：2330日線"))
            return
        
        sid = sid_match.group()
        mode = 'W' if "週線" in msg else ('M' if "月線" in msg else 'D')
        
        # 呼叫 K 線生成 (邏輯維持您原本的 get_kline_url)
        url = get_kline_url(sid, period=mode)
        if url.startswith("http"):
            line_bot_api.reply_message(event.reply_token, ImageSendMessage(original_content_url=url, preview_image_url=url))
        else:
            line_bot_api.reply_message(event.reply_token, TextMessage(text=url))
        return

    # 名稱轉代號邏輯
    sid = get_stock_id(msg) # 使用您原本的 get_stock_id 函式
    if sid:
        line_bot_api.reply_message(event.reply_token, create_kline_panel(sid)) # 使用您原本的 Flex 函式
    else:
        line_bot_api.reply_message(event.reply_token, TextMessage(text=f"找不到標的：{msg}"))

# 這裡保留您原本的 get_kline_url, get_stock_id, create_kline_panel 函式...

if __name__ == "__main__":
    app.run(port=10000)
