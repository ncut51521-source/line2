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
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    try:
        if info_type == "三大法人":
            # 棄用證交所官方 API，改用 FinMind (對雲端主機較友善)
            url = f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockInstitutionalInvestorsBuySell&data_id={sid}"
            res = requests.get(url, timeout=10)
            data = res.json()
            
            if data.get('msg') == 'success' and len(data.get('data', [])) > 0:
                latest = data['data'][-1]
                date = latest.get('date')
                # 計算合計買賣差額 (單位：張)
                buy = int(latest.get('buy', 0))
                sell = int(latest.get('sell', 0))
                diff = (buy - sell) // 1000
                
                return (f"🏦 {sid} 三大法人(最新交易日)\n"
                        f"📅 日期：{date}\n"
                        f"------------------\n"
                        f"📊 買賣超：{diff:,} 張\n"
                        f"✅ 數據來源：FinMind 備援介面")
            return f"⚠️ 無法取得 {sid} 法人資料，請稍後再試"

        elif info_type == "即時五檔":
            # 改用證交所另一個較鬆的即時看板介面
            url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_{sid}.tw"
            res = requests.get(url, verify=False, timeout=10, headers=headers)
            data = res.json()
            
            if data.get('msgArray'):
                info = data['msgArray'][0]
                bids = info.get('b', '---').split('_')[:5]
                asks = info.get('a', '---').split('_')[:5]
                return (f"📊 {sid} 即時五檔\n"
                        f"買進: {', '.join(bids)}\n"
                        f"賣出: {', '.join(asks)}\n"
                        f"💰 現價: {info.get('z', '---')}")
            return "❌ 目前非交易時間或 API 連線受限"

        elif info_type == "技術指標":
            # 簡單計算 (此部分若 Render 依然擋 twstock 可改用其他方式)
            import twstock
            stock = twstock.Stock(sid)
            return f"📈 {sid} 技術指標\n現價: {stock.price[-1]}\n5日均價: {sum(stock.price[-5:])/5:.2f}"

    except Exception as e:
        return f"❌ 系統錯誤: {str(e)}"

# ========= LINE 伺服器邏輯 =========
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
    
    # 處理功能按鈕
    for action in ["即時五檔", "三大法人", "技術指標"]:
        if action in msg:
            sid = msg.split(" ")[0]
            line_bot_api.reply_message(event.reply_token, TextMessage(text=get_stock_info_text(sid, action)))
            return

    # 處理代號輸入
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
              {"type": "button", "style": "primary", "color": "#007bff", "action": {"type": "message", "label": "即時五檔", "text": f"{sid} 即時五檔"}},
              {"type": "button", "style": "secondary", "action": {"type": "message", "label": "技術指標", "text": f"{sid} 技術指標"}}
            ]
          }
        }
    )

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
