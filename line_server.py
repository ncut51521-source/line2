import os, re, requests, urllib3
from flask import Flask, request
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, FlexSendMessage
from bs4 import BeautifulSoup
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
    if re.match(r'^\d{4,6}$', name_or_id): return name_or_id
    for sid, info in twstock.codes.items():
        if info.name == name_or_id: return sid
    return None

def get_stock_info_text(sid, info_type):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://www.twse.com.tw/zh/page/trading/fund/T86W.html'
    }
    try:
        if info_type == "即時五檔":
            rt = twstock.realtime.get(sid)
            if rt['success']:
                return f"📊 {sid} 即時五檔\n買進: {', '.join(rt['realtime']['best_bid_price'])}\n賣出: {', '.join(rt['realtime']['best_ask_price'])}"
            return "❌ 證交所目前連線異常"

        elif info_type == "三大法人":
            # 優先嘗試 API 版
            api_url = f"https://www.twse.com.tw/fund/T86W?response=json&stockNo={sid}"
            try:
                res = requests.get(api_url, verify=False, timeout=8, headers=headers)
                data = res.json()
                if data.get('stat') == 'OK' and len(data.get('data', [])) > 0:
                    row = data['data'][0]
                    return f"🏦 {sid} 三大法人\n📅 日期：{row[0]}\n👤 外資：{row[4]} 股\n💪 投信：{row[10]} 股\n🏢 自營：{row[11]} 股"
            except:
                pass # API 被擋，嘗試爬網頁版

            # 備援方案：爬證交所網頁 HTML
            web_url = f"https://www.twse.com.tw/zh/page/trading/fund/T86W.html"
            # 這裡我們換一個比較容易抓的第三方來源：玩股網或 Yahoo (示範跳轉連結)
            return f"⚠️ 證交所 API 偵測到頻繁存取。\n請點擊連結查看 {sid} 法人進出：\nhttps://tw.stock.yahoo.com/quote/{sid}/institutional-trading"

        elif info_type == "技術指標":
            stock = twstock.Stock(sid)
            ma5 = stock.moving_average(stock.price, 5)
            return f"📈 {sid} 技術指標\n現價: {stock.price[-1]}\n5日均價: {ma5[-1]:.2f}"

        elif info_type == "公司介紹":
            if sid in twstock.codes:
                info = twstock.codes[sid]
                return f"🏢 {info.name} ({sid})\n📂 產業：{info.group}\n🔍 類型：{info.type}"
            return "查無資訊"
    except Exception as e:
        return f"❌ 查詢失敗，請稍後再試"

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
    for action in ["即時五檔", "三大法人", "技術指標", "公司介紹"]:
        if action in msg:
            sid = msg.split(" ")[0]
            line_bot_api.reply_message(event.reply_token, TextMessage(text=get_stock_info_text(sid, action)))
            return
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
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
