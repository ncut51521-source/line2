import os
import re
import requests
import urllib3
from flask import Flask, request
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, FlexSendMessage
import twstock

# 禁用 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# ========= 核心設定 =========
LINE_ACCESS_TOKEN = "dX9zPn4sFpqbNCL+4SBGEsSGtMcSeYVZ1GEv5MNGOeISygMC896e141rVqOkETcEkRNktPujTjRf4Cn1FyoU2+S8sPPhSEj1LhTKRwLI5HQyaj09mE1ozJlM+6GKeC6JCAVaFyJxuTE3fanlzC82FQdB04t89/1O/w1cDnyilFU="
LINE_HANDLER_SECRET = "c1ef088ebc7f9dd0f04b5d7a7db03dfc" 

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

def get_stock_info_text(sid, info_type):
    # 模擬瀏覽器，避免被證交所阻擋
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://www.twse.com.tw/'
    }
    try:
        if info_type == "即時五檔":
            rt = twstock.realtime.get(sid)
            if rt['success']:
                bids = rt['realtime']['best_bid_price']
                asks = rt['realtime']['best_ask_price']
                return f"📊 {sid} 即時五檔\n買進: {', '.join(bids)}\n賣出: {', '.join(asks)}"
            return "❌ 暫時無法取得即時數據"
            
        elif info_type == "三大法人":
            url = f"https://www.twse.com.tw/fund/T86W?response=json&stockNo={sid}"
            # 使用 verify=False 並加上 headers 提升成功率
            res = requests.get(url, verify=False, timeout=10, headers=headers)
            data = res.json()
            if data.get('stat') == 'OK' and len(data.get('data', [])) > 0:
                row = data['data'][0] 
                return (f"🏦 {sid} 三大法人買賣超\n📅 日期：{row[0]}\n"
                        f"------------------\n"
                        f"👤 外資：{row[4]} 股\n💪 投信：{row[10]} 股\n🏢 自營：{row[11]} 股")
            return f"⚠️ 查無 {sid} 法人資料 (可能尚未更新)"
            
        elif info_type == "技術指標":
            stock = twstock.Stock(sid)
            if len(stock.price) < 5: return "📈 資料量不足"
            ma5 = stock.moving_average(stock.price, 5)
            return f"📈 {sid} 技術指標\n現價: {stock.price[-1]}\n5日均價: {ma5[-1]:.2f}"
            
        elif info_type == "公司介紹":
            if sid in twstock.codes:
                info = twstock.codes[sid]
                return f"🏢 {info.name} ({sid})\n📂 產業：{info.group}\n🔍 類型：{info.type}"
            return "查無資訊"
    except Exception:
        return "❌ 證交所主機繁忙，請稍後再點一次"

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except Exception:
        pass
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text.strip()
    # 判斷是否為按鈕觸發的詳細請求
    for action in ["即時五檔", "三大法人", "技術指標", "公司介紹"]:
        if action in msg:
            sid = msg.split(" ")[0]
            line_bot_api.reply_message(event.reply_token, TextMessage(text=get_stock_info_text(sid, action)))
            return

    # 初次輸入代號顯示選單
    sid = get_stock_id(msg)
    if sid:
        name = twstock.codes[sid].name if sid in twstock.codes else "股票"
        line_bot_api.reply_message(event.reply_token, create_stock_menu(sid, name))
    else:
        line_bot_api.reply_message(event.reply_token, TextMessage(text="請輸入股票代號（如 2330）"))

def create_stock_menu(sid, name):
    return FlexSendMessage(
        alt_text=f"{sid} 選單",
        contents={
          "type": "bubble",
          "body": {
            "type": "box", "layout": "vertical", "spacing": "md", "contents": [
              {"type": "text", "text": f"📈 {sid} {name}", "weight": "bold", "size": "xl", "align": "center"},
              {"type": "separator"},
              {"type": "button", "style": "primary", "color": "#28a745", "action": {"type": "message", "label": "三大法人買賣超", "text": f"{sid} 三大法人"}},
              {"type": "button", "style": "primary", "color": "#007bff", "action": {"type": "message", "label": "即時五檔", "text": f"{sid} 即時五檔"}},
              {"type": "button", "style": "secondary", "action": {"type": "message", "label": "公司介紹", "text": f"{sid} 公司介紹"}}
            ]
          }
        }
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
