import os, re, requests, urllib3, json
from flask import Flask, request
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, FlexSendMessage

# 禁用 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# ========= 核心設定 (請確認 Secret 跟 Token 沒貼錯) =========
LINE_ACCESS_TOKEN = "dX9zPn4sFpqbNCL+4SBGEsSGtMcSeYVZ1GEv5MNGOeISygMC896e141rVqOkETcEkRNktPujTjRf4Cn1FyoU2+S8sPPhSEj1LhTKRwLI5HQyaj09mE1ozJlM+6GKeC6JCAVaFyJxuTE3fanlzC82FQdB04t89/1O/w1cDnyilFU="
LINE_HANDLER_SECRET = "c1ef088ebc7f9dd0f04b5d7a7db03dfc" 

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_HANDLER_SECRET)

def get_stock_info_text(sid, info_type):
    try:
        if info_type == "三大法人":
            # 改連 FinMind 第三方 API，不連證交所
            url = f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockInstitutionalInvestorsBuySell&data_id={sid}"
            res = requests.get(url, timeout=10)
            data = res.json()
            if data.get('msg') == 'success' and len(data.get('data')) > 0:
                latest = data['data'][-1]
                # 計算合計買賣超 (張)
                diff = (int(latest.get('buy', 0)) - int(latest.get('sell', 0))) // 1000
                return (f"🏦 {sid} 三大法人(最新)\n📅 日期：{latest.get('date')}\n"
                        f"------------------\n📊 買賣超：{diff:,} 張\n"
                        f"✅ 數據來源：FinMind API")
            return f"⚠️ 暫時無法取得 {sid} 法人資料"

        elif info_type == "即時五檔":
            # 改連 Fugle 備援行情介面
            url = f"https://api.fugle.tw/marketdata/v1.0/stock/intraday/quote/{sid}"
            res = requests.get(url, timeout=10)
            data = res.json()
            if 'lastTrial' in data:
                price = data.get('lastTrial', {}).get('price', '---')
                return f"📊 {sid} 即時行情\n💰 試撮價: {price}\n💡 證交所 API 目前連線受限，此為備援數據。"
            return "❌ 目前非交易時間或數據源忙碌"

        elif info_type == "技術指標":
            import twstock
            stock = twstock.Stock(sid)
            if len(stock.price) >= 5:
                return f"📈 {sid} 技術指標\n現價: {stock.price[-1]}\n5日均價: {sum(stock.price[-5:])/5:.2f}"
            return "❌ 資料量不足"

    except Exception as e:
        return "❌ 數據源連線逾時，請稍後重試"

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
    # 判斷按鈕文字格式： "2330 三大法人"
    if " " in msg:
        parts = msg.split(" ")
        sid, action = parts[0], parts[1]
        if action in ["即時五檔", "三大法人", "技術指標"]:
            line_bot_api.reply_message(event.reply_token, TextMessage(text=get_stock_info_text(sid, action)))
            return

    # 輸入純數字代號顯示選單
    if re.match(r'^\d{4,6}$', msg):
        line_bot_api.reply_message(event.reply_token, create_stock_menu(msg))

def create_stock_menu(sid):
    return FlexSendMessage(
        alt_text=f"{sid} 選單",
        contents={
          "type": "bubble",
          "body": {
            "type": "box", "layout": "vertical", "spacing": "md", "contents": [
              {"type": "text", "text": f"🎯 股票代號：{sid}", "weight": "bold", "size": "xl", "align": "center"},
              {"type": "button", "style": "primary", "color": "#28a745", "action": {"type": "message", "label": "三大法人", "text": f"{sid} 三大法人"}},
              {"type": "button", "style": "primary", "color": "#007bff", "action": {"type": "message", "label": "即時五檔", "text": f"{sid} 即時五檔"}},
              {"type": "button", "style": "secondary", "action": {"type": "message", "label": "技術指標", "text": f"{sid} 技術指標"}}
            ]
          }
        }
    )

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
