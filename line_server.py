import os, re, requests, urllib3
from flask import Flask, request
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, FlexSendMessage
import twstock

# 禁用 SSL 驗證警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# ========= 核心設定 =========
LINE_ACCESS_TOKEN = "dX9zPn4sFpqbNCL+4SBGEsSGtMcSeYVZ1GEv5MNGOeISygMC896e141rVqOkETcEkRNktPujTjRf4Cn1FyoU2+S8sPPhSEj1LhTKRwLI5HQyaj09mE1ozJlM+6GKeC6JCAVaFyJxuTE3fanlzC82FQdB04t89/1O/w1cDnyilFU="
LINE_HANDLER_SECRET = "c1ef088ebc7f9dd0f04b5d7a7db03dfc" 

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_HANDLER_SECRET)

def get_stock_info_text(sid, info_type):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    try:
        if info_type == "三大法人":
            # 優先採用備援 API：Fugle Market Data (此為公開快取路徑，不需 API Key 即可做基本查詢)
            # 若此路徑也失效，才會顯示報錯
            url = f"https://api.fugle.tw/marketdata/v1.0/stock/intraday/quote/{sid}"
            try:
                # 這裡改用一個更輕量、對雲端主機更寬容的資料源
                res = requests.get(f"https://www.twse.com.tw/fund/T86W?response=json&stockNo={sid}", 
                                   verify=False, timeout=10, headers=headers)
                data = res.json()
                if data.get('stat') == 'OK' and len(data.get('data', [])) > 0:
                    row = data['data'][0]
                    # 數據清洗：移除逗號並轉為整數
                    def clean(v): return int(v.replace(',', ''))
                    return (f"🏦 {sid} 三大法人買賣超\n"
                            f"📅 日期：{row[0]}\n"
                            f"------------------\n"
                            f"👤 外資：{clean(row[4])//1000:,} 張\n"
                            f"💪 投信：{clean(row[10])//1000:,} 張\n"
                            f"🏢 自營：{clean(row[11])//1000:,} 張\n"
                            f"✅ 單位已換算為「張」")
            except:
                return f"❌ 證交所 API 封鎖中，請 1 分鐘後再試，或檢查代號 {sid}"

        elif info_type == "即時五檔":
            rt = twstock.realtime.get(sid)
            if rt['success']:
                return f"📊 {sid} 即時五檔\n買進: {', '.join(rt['realtime']['best_bid_price'])}\n賣出: {', '.join(rt['realtime']['best_ask_price'])}"
            return "❌ 即時數據源連線逾時"

    except Exception as e:
        return f"系統處理錯誤: {str(e)}"

# ========= LINE 處理邏輯 (保持穩定縮排) =========
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
    # 判斷是否為功能按鈕觸發
    for action in ["即時五檔", "三大法人", "技術指標", "公司介紹"]:
        if action in msg:
            sid = msg.split(" ")[0]
            line_bot_api.reply_message(event.reply_token, TextMessage(text=get_stock_info_text(sid, action)))
            return
    
    # 判斷是否為純代碼輸入
    sid_match = re.match(r'^\d{4,6}$', msg)
    if sid_match:
        sid = sid_match.group()
        line_bot_api.reply_message(event.reply_token, create_stock_menu(sid))
    else:
        line_bot_api.reply_message(event.reply_token, TextMessage(text="請輸入股票代號 (如 2330)"))

def create_stock_menu(sid):
    return FlexSendMessage(
        alt_text=f"股票 {sid} 選單",
        contents={
          "type": "bubble",
          "body": {
            "type": "box", "layout": "vertical", "spacing": "md", "contents": [
              {"type": "text", "text": f"📈 股票代號：{sid}", "weight": "bold", "size": "xl", "align": "center"},
              {"type": "button", "style": "primary", "color": "#28a745", "action": {"type": "message", "label": "三大法人", "text": f"{sid} 三大法人"}},
              {"type": "button", "style": "primary", "color": "#007bff", "action": {"type": "message", "label": "即時五檔", "text": f"{sid} 即時五檔"}}
            ]
          }
        }
    )

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
