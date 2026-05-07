import os
import re
import traceback
import requests
import urllib3
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, FlexSendMessage
import twstock

# 禁用安全請求警告（因為我們使用了 verify=False）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# ========= 核心設定 =========
LINE_ACCESS_TOKEN = "dX9zPn4sFpqbNCL+4SBGEsSGtMcSeYVZ1GEv5MNGOeISygMC896e141rVqOkETcEkRNktPujTjRf4Cn1FyoU2+S8sPPhSEj1LhTKRwLI5HQyaj09mE1ozJlM+6GKeC6JCAVaFyJxuTE3fanlzC82FQdB04t89/1O/w1cDnyilFU="
LINE_HANDLER_SECRET = "c1ef088ebc7f9dd0f04b5d7a7db03dfc" 

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_HANDLER_SECRET)

# ========= 邏輯：獲取股票 ID =========
def get_stock_id(name_or_id):
    name_or_id = name_or_id.upper().strip()
    if re.match(r'^\d{4,6}$', name_or_id):
        return name_or_id
    for sid, info in twstock.codes.items():
        if info.name == name_or_id:
            return sid
    return None

# ========= 邏輯：處理各項數值化請求 =========
def get_stock_info_text(sid, info_type):
    # 建立模擬瀏覽器的標頭，避免被證交所阻擋
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    try:
        if info_type == "即時五檔":
            # twstock 的即時資料有時會因為連線被拒絕而失敗
            rt = twstock.realtime.get(sid)
            if rt['success']:
                bids = rt['realtime']['best_bid_price']
                asks = rt['realtime']['best_ask_price']
                return f"📊 {sid} 即時五檔\n買進: {', '.join(bids)}\n賣出: {', '.join(asks)}"
            return f"獲取即時數據失敗: {rt.get('rtmessage', '遠端主機拒絕連線')}"
            
        elif info_type == "技術指標":
            stock = twstock.Stock(sid)
            if len(stock.price) < 5:
                return f"📈 {sid} 資料量不足以計算指標"
            ma5 = stock.moving_average(stock.price, 5)
            return f"📈 {sid} 技術指標\n現價: {stock.price[-1]}\n5日均價: {ma5[-1]:.2f}"
            
        elif info_type == "三大法人":
            url = f"https://www.twse.com.tw/zh/#foreign?response=json&stockNo={sid}"
            try:
                # 加上 headers 並設定 timeout
                res = requests.get(url, verify=False, timeout=15, headers=headers)
                
                # 檢查是否成功取得內容
                if not res.text.strip():
                    return "連線證交所失敗：對方未回傳數據 (可能被暫時封鎖 IP)"
                
                data = res.json()
                
                if data.get('stat') == 'OK' and len(data.get('data', [])) > 0:
                    row = data['data'][0] 
                    date_str = row[0]       
                    foreign = row[4]        # 外資
                    trust = row[10]         # 投信
                    dealer = row[11]        # 自營商
                    
                    return (f"🏦 {sid} 三大法人買賣超\n"
                            f"📅 日期：{date_str}\n"
                            f"------------------\n"
                            f"👤 外資：{foreign} 股\n"
                            f"💪 投信：{trust} 股\n"
                            f"🏢 自營：{dealer} 股\n"
                            f"⚠️ 單位為「股」，正數為買超。")
                return f"查無 {sid} 的法人資料 (非交易日或代碼錯誤)"
            except Exception as req_e:
                return f"連線證交所失敗: 服務器忙碌中，請稍後再試"
            
        elif info_type == "公司介紹":
            if sid in twstock.codes:
                info = twstock.codes[sid]
                return (f"🏢 公司名稱：{info.name} ({sid})\n"
                        f"📂 產業：{info.group}\n"
                        f"🔍 細產業：{info.type}")
            return f"查無 {sid} 的公司介紹"
            
    except Exception as e:
        return f"處理 {info_type} 時發生錯誤"

# ========= LINE Bot 回應邏輯 =========
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)
    
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        # Verify 測試時回傳 OK 確保連線通暢[cite: 2]
        return 'OK' 
    except Exception:
        return 'OK'
        
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    try:
        msg = event.message.text.strip()
        
        # 處理按鈕觸發的詳細查詢
        for action in ["即時五檔", "三大法人", "技術指標", "公司介紹"]:
            if action in msg:
                # 假設格式為 "2330 三大法人"
                sid = msg.split(" ")[0]
                res_text = get_stock_info_text(sid, action)
                line_bot_api.reply_message(event.reply_token, TextMessage(text=res_text))
                return

        # 初始代碼輸入，顯示選單按鈕
        sid = get_stock_id(msg)
        if sid:
            name = twstock.codes[sid].name if sid in twstock.codes else "未知"
            line_bot_api.reply_message(event.reply_token, create_stock_menu(sid, name))
        else:
            line_bot_api.reply_message(event.reply_token, TextMessage(text=f"找不到「{msg}」相關股票"))
    except Exception as e:
        line_bot_api.reply_message(event.reply_token, TextMessage(text=f"系統錯誤: {str(e)}"))

def create_stock_menu(sid, name):
    return FlexSendMessage(
        alt_text=f"股票 {sid} {name} 功能選單",
        contents={
          "type": "bubble",
          "body": {
            "type": "box", "layout": "vertical", "spacing": "md", "contents": [
              {"type": "text", "text": f"📈 {sid} {name}", "weight": "bold", "size": "xl", "align": "center"},
              {"type": "separator"},
              {"type": "button", "style": "primary", "color": "#007bff", "action": {"type": "message", "label": "即時五檔", "text": f"{sid} 即時五檔"}},
              {"type": "button", "style": "primary", "color": "#28a745", "action": {"type": "message", "label": "三大法人買賣超", "text": f"{sid} 三大法人"}},
              {"type": "button", "style": "primary", "color": "#fd7e14", "action": {"type": "message", "label": "技術指標(數值化)", "text": f"{sid} 技術指標"}},
              {"type": "button", "style": "secondary", "action": {"type": "message", "label": "公司介紹", "text": f"{sid} 公司介紹"}}
            ]
          }
        }
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
