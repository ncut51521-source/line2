import os, re
from flask import Flask, request
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, FlexSendMessage

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
    
    # 處理輸入純數字代號
    if re.match(r'^\d{4}$', msg):
        line_bot_api.reply_message(event.reply_token, create_stock_menu(msg))
        return

    # 處理按鈕觸發
    if " " in msg:
        sid = msg.split(" ")[0]
        line_bot_api.reply_message(event.reply_token, create_analysis_card(sid))

def create_stock_menu(sid):
    return FlexSendMessage(
        alt_text=f"{sid} 分析選單",
        contents={
          "type": "bubble",
          "body": {
            "type": "box", "layout": "vertical", "spacing": "md", "contents": [
              {"type": "text", "text": f"📈 台股分析：{sid}", "weight": "bold", "size": "xl", "align": "center"},
              {"type": "button", "style": "primary", "color": "#e74c3c", "action": {"type": "message", "label": "查看即時 K 線圖", "text": f"{sid} K線"}},
              {"type": "button", "style": "primary", "color": "#28a745", "action": {"type": "message", "label": "三大法人資訊", "text": f"{sid} 法人"}}
            ]
          }
        }
    )

def create_analysis_card(sid):
    # 這是最強保險：直接生成連結卡片，避開伺服器請求限制
    return FlexSendMessage(
        alt_text=f"{sid} 數據分析",
        contents={
          "type": "bubble",
          "header": {
            "type": "box", "layout": "vertical", "contents": [
              {"type": "text", "text": f"📊 {sid} 數據整合", "weight": "bold", "color": "#ffffff"}
            ], "backgroundColor": "#2c3e50"
          },
          "body": {
            "type": "box", "layout": "vertical", "spacing": "sm", "contents": [
              {"type": "text", "text": "由於伺服器連線受限，請點擊下方按鈕獲取即時數據：", "wrap": True, "size": "sm"},
              {"type": "button", "style": "link", "action": {"type": "uri", "label": "📈 查看技術 K 線", "uri": f"https://tw.stock.yahoo.com/quote/{sid}/chart"}},
              {"type": "button", "style": "link", "action": {"type": "uri", "label": "🏦 查看法人進出", "uri": f"https://tw.stock.yahoo.com/quote/{sid}/institutional-trading"}}
            ]
          }
        }
    )

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
