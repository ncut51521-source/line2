import os, re, requests
from flask import Flask, request
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, ImageSendMessage, FlexSendMessage

app = Flask(__name__)

# ========= 核心設定 =========
LINE_ACCESS_TOKEN = "dX9zPn4sFpqbNCL+4SBGEsSGtMcSeYVZ1GEv5MNGOeISygMC896e141rVqOkETcEkRNktPujTjRf4Cn1FyoU2+S8sPPhSEj1LhTKRwLI5HQyaj09mE1ozJlM+6GKeC6JCAVaFyJxuTE3fanlzC82FQdB04t89/1O/w1cDnyilFU="
LINE_HANDLER_SECRET = "c1ef088ebc7f9dd0f04b5d7a7db03dfc" 

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_HANDLER_SECRET)

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except:
        pass
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text.strip()
    
    # 判斷是否點擊了選單按鈕 (格式如: "2330 三大法人")
    if " " in msg:
        parts = msg.split(" ")
        sid = parts[0]
        # 無論點擊什麼，我們都回傳 K 線圖，因為這最穩定
        img_url = f"https://chart.capital.com.tw/Chart/TWSTOCK/STK_{sid}.aspx" # 示意圖源
        # 另一種更穩定的圖源 (Yahoo 圖片)
        img_url = f"https://s.yimg.com/nb/tw/tw_ec_1.0.0/static/tws/stk/chart/{sid}.png"
        
        line_bot_api.reply_message(
            event.reply_token,
            ImageSendMessage(
                original_content_url=img_url,
                preview_image_url=img_url
            )
        )
        return

    # 輸入純數字代號顯示選單
    if re.match(r'^\d{4}$', msg):
        line_bot_api.reply_message(event.reply_token, create_stock_menu(msg))

def create_stock_menu(sid):
    return FlexSendMessage(
        alt_text=f"{sid} 功能選單",
        contents={
          "type": "bubble",
          "body": {
            "type": "box", "layout": "vertical", "spacing": "md", "contents": [
              {"type": "text", "text": f"📈 股票分析：{sid}", "weight": "bold", "size": "xl", "align": "center"},
              {"type": "separator"},
              {"type": "button", "style": "primary", "color": "#e74c3c", "action": {"type": "message", "label": "查看當日 K 線圖", "text": f"{sid} K線圖"}},
              {"type": "button", "style": "primary", "color": "#28a745", "action": {"type": "message", "label": "三大法人買賣超", "text": f"{sid} 三大法人"}},
              {"type": "button", "style": "secondary", "action": {"type": "uri", "label": "詳細財經數據", "uri": f"https://tw.stock.yahoo.com/quote/{sid}"}}
            ]
          }
        }
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
