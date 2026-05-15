import os, re, requests, urllib3, json
from flask import Flask, request
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, FlexSendMessage

# 徹底禁用 SSL 驗證警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# ========= 核心設定 =========
LINE_ACCESS_TOKEN = "dX9zPn4sFpqbNCL+4SBGEsSGtMcSeYVZ1GEv5MNGOeISygMC896e141rVqOkETcEkRNktPujTjRf4Cn1FyoU2+S8sPPhSEj1LhTKRwLI5HQyaj09mE1ozJlM+6GKeC6JCAVaFyJxuTE3fanlzC82FQdB04t89/1O/w1cDnyilFU="
LINE_HANDLER_SECRET = "c1ef088ebc7f9dd0f04b5d7a7db03dfc" 

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_HANDLER_SECRET)

def get_stock_info_text(sid, info_type):
    # 這是最後一道防線：如果 API 全部失敗，就回傳漂亮的 Flex 連結卡片
    if info_type == "三大法人":
        url = f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockInstitutionalInvestorsBuySell&data_id={sid}"
        try:
            res = requests.get(url, timeout=5)
            data = res.json()
            if data.get('msg') == 'success' and len(data.get('data')) > 0:
                latest = data['data'][-1]
                diff = (int(latest.get('buy', 0)) - int(latest.get('sell', 0))) // 1000
                return f"🏦 {sid} 三大法人\n📅 {latest.get('date')}\n📊 買賣超：{diff:,} 張"
        except:
            pass # 失敗則走下方的「備援卡片」
        return create_backup_link(sid, "三大法人", f"https://tw.stock.yahoo.com/quote/{sid}/institutional-trading")

    elif info_type == "即時五檔":
        return create_backup_link(sid, "即時行情", f"https://tw.stock.yahoo.com/quote/{sid}")

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
    if " " in msg:
        parts = msg.split(" ")
        sid, action = parts[0], parts[1]
        res = get_stock_info_text(sid, action)
        if isinstance(res, str):
            line_bot_api.reply_message(event.reply_token, TextMessage(text=res))
        else:
            line_bot_api.reply_message(event.reply_token, res)
        return

    if re.match(r'^\d{4}$', msg):
        line_bot_api.reply_message(event.reply_token, create_stock_menu(msg))

def create_stock_menu(sid):
    return FlexSendMessage(
        alt_text=f"{sid} 功能選單",
        contents={
          "type": "bubble",
          "body": {
            "type": "box", "layout": "vertical", "spacing": "md", "contents": [
              {"type": "text", "text": f"🎯 股票代號：{sid}", "weight": "bold", "size": "xl", "align": "center"},
              {"type": "button", "style": "primary", "color": "#28a745", "action": {"type": "message", "label": "三大法人買賣超", "text": f"{sid} 三大法人"}},
              {"type": "button", "style": "primary", "color": "#007bff", "action": {"type": "message", "label": "即時五檔查詢", "text": f"{sid} 即時五檔"}}
            ]
          }
        }
    )

def create_backup_link(sid, label, url):
    return FlexSendMessage(
        alt_text=f"點擊查看 {sid} {label}",
        contents={
          "type": "bubble",
          "body": {
            "type": "box", "layout": "vertical", "contents": [
              {"type": "text", "text": f"⚠️ {sid} 數據存取受限", "weight": "bold", "color": "#ff0000"},
              {"type": "text", "text": "伺服器 IP 目前遭阻擋，請點擊下方直接查看數據：", "wrap": True, "size": "sm", "margin": "md"},
              {"type": "button", "margin": "xl", "style": "link", "height": "sm", "action": {"type": "uri", "label": f"查看 {label}", "uri": url}}
            ]
          }
        }
    )

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
