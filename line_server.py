import os, re, requests, urllib3, json
from flask import Flask, request
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, FlexSendMessage
import twstock

# 徹底禁用 SSL 驗證警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# ========= 核心設定 =========
LINE_ACCESS_TOKEN = "dX9zPn4sFpqbNCL+4SBGEsSGtMcSeYVZ1GEv5MNGOeISygMC896e141rVqOkETcEkRNktPujTjRf4Cn1FyoU2+S8sPPhSEj1LhTKRwLI5HQyaj09mE1ozJlM+6GKeC6JCAVaFyJxuTE3fanlzC82FQdB04t89/1O/w1cDnyilFU="
LINE_HANDLER_SECRET = "c1ef088ebc7f9dd0f04b5d7a7db03dfc" 

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_HANDLER_SECRET)

def get_stock_info_text(sid, info_type):
    # 模擬真實瀏覽器的 Headers
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Referer': 'https://www.twse.com.tw/zh/page/trading/fund/T86W.html'
    }
    
    try:
        if info_type == "三大法人":
            # 嘗試抓取證交所日報表
            url = f"https://www.twse.com.tw/fund/T86W?response=json&stockNo={sid}"
            res = requests.get(url, verify=False, timeout=10, headers=headers)
            
            if res.status_code != 200:
                return f"❌ 證交所拒絕連線 (錯誤碼: {res.status_code})"
                
            data = res.json()
            if data.get('stat') == 'OK' and len(data.get('data', [])) > 0:
                row = data['data'][0] 
                # row[4]:外資, row[10]:投信, row[11]:自營商
                return (f"🏦 {sid} 三大法人買賣超\n"
                        f"📅 日期：{row[0]}\n"
                        f"------------------\n"
                        f"👤 外資：{row[4]} 股\n"
                        f"💪 投信：{row[10]} 股\n"
                        f"🏢 自營：{row[11]} 股\n"
                        f"✅ 數據已成功獲取")
            return f"⚠️ 查無 {sid} 資料 (今日可能尚未更新)"

        elif info_type == "即時五檔":
            # 避開 twstock 直接抓取即時 API
            url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_{sid}.tw"
            res = requests.get(url, verify=False, timeout=10, headers=headers)
            data = res.json()
            if data.get('msgArray'):
                info = data['msgArray'][0]
                bids = info.get('b', '0_0_0_0_0').split('_')[:5]
                asks = info.get('a', '0_0_0_0_0').split('_')[:5]
                return f"📊 {sid} 即時五檔\n買進: {', '.join(bids)}\n賣出: {', '.join(asks)}"
            return "❌ 無法取得即時數據，盤後時間請查三大法人"

        elif info_type == "技術指標":
            # 因為 twstock 在 Render 易被擋，若失敗則回傳現價
            stock = twstock.Stock(sid)
            return f"📈 {sid} 技術指標\n現價: {stock.price[-1]}\n5日均價: {sum(stock.price[-5:])/5:.2f}"

    except Exception as e:
        return f"❌ 系統繁忙: 請稍後再試一次"

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
    
    # 判斷功能按鈕
    for action in ["即時五檔", "三大法人", "技術指標"]:
        if action in msg:
            sid = msg.split(" ")[0]
            line_bot_api.reply_message(event.reply_token, TextMessage(text=get_stock_info_text(sid, action)))
            return

    # 輸入代號顯示選單
    sid_match = re.match(r'^\d{4}$', msg)
    if sid_match:
        sid = sid_match.group()
        line_bot_api.reply_message(event.reply_token, create_stock_menu(sid))

def create_stock_menu(sid):
    return FlexSendMessage(
        alt_text=f"{sid} 功能選單",
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
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
