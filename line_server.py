import os
import re
import traceback
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, FlexSendMessage
import twstock  # 統一放在最上方，確保所有函式都能讀取[cite: 2]

app = Flask(__name__)

# ========= 核心設定 =========
LINE_ACCESS_TOKEN = "dX9zPn4sFpqbNCL+4SBGEsSGtMcSeYVZ1GEv5MNGOeISygMC896e141rVqOkETcEkRNktPujTjRf4Cn1FyoU2+S8sPPhSEj1LhTKRwLI5HQyaj09mE1ozJlM+6GKeC6JCAVaFyJxuTE3fanlzC82FQdB04t89/1O/w1cDnyilFU="
LINE_HANDLER_SECRET = "255e4550a9999d33b4d2cccd8c8c8af8" 

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_HANDLER_SECRET)

# ========= 邏輯：獲取股票 ID =========
def get_stock_id(name_or_id):
    name_or_id = name_or_id.upper().strip()[cite: 2]
    if re.match(r'^\d{4,6}$', name_or_id):[cite: 2]
        return name_or_id[cite: 2]
    for sid, info in twstock.codes.items():[cite: 2]
        if info.name == name_or_id:[cite: 2]
            return sid[cite: 2]
    return None[cite: 2]

# ========= 邏輯：處理各項數值化請求 =========
def get_stock_info_text(sid, info_type):
    try:
        if info_type == "即時五檔":
            rt = twstock.realtime.get(sid)[cite: 2]
            if rt['success']:
                bids = rt['realtime']['best_bid_price']
                asks = rt['realtime']['best_ask_price']
                return f"📊 {sid} 即時五檔\n買進: {', '.join(bids)}\n賣出: {', '.join(asks)}"
            return "暫時無法取得五檔數據"
            
        elif info_type == "技術指標":
            stock = twstock.Stock(sid)[cite: 2]
            ma5 = stock.moving_average(stock.price, 5)
            return f"📈 {sid} 技術指標\n現價: {stock.price[-1]}\n5日均價: {ma5[-1]:.2f}"
            
        elif info_type == "三大法人":
            return f"🏦 {sid} 三大法人買賣超\n(提示：本功能需介接三大法人 API，目前為示範位置)"
            
        elif info_type == "公司介紹":
            if sid in twstock.codes:[cite: 2]
                info = twstock.codes[sid][cite: 2]
                res = [
                    f"🏢 公司名稱：{info.name} ({sid})",
                    f"💰 額定股本：(查閱財報中)",
                    f"🏆 產業地位：該領域領先企業",
                    f"📂 產業：{info.group}",
                    f"🔍 細產業：{info.type}相關設備"
                ]
                return "\n".join(res)
            return f"查無 {sid} 的公司介紹"
            
    except Exception as e:
        return f"獲取{info_type}失敗: {str(e)}"

# ========= LINE Bot 回應邏輯 =========
@app.route("/callback", methods=['POST'])[cite: 2]
def callback():
    signature = request.headers.get('X-Line-Signature')[cite: 2]
    body = request.get_data(as_text=True)[cite: 2]
    try:
        handler.handle(body, signature)[cite: 2]
    except InvalidSignatureError:
        abort(400)[cite: 2]
    return 'OK'[cite: 2]

@handler.add(MessageEvent, message=TextMessage)[cite: 2]
def handle_message(event):
    try:
        msg = event.message.text.strip()[cite: 2]
        
        # 處理詳細查詢請求
        for action in ["即時五檔", "三大法人", "技術指標", "公司介紹"]:
            if action in msg:
                sid = msg.split(" ")[0]
                res_text = get_stock_info_text(sid, action)
                line_bot_api.reply_message(event.reply_token, TextMessage(text=res_text))
                return

        # 初始代碼輸入，顯示選單
        sid = get_stock_id(msg)[cite: 2]
        if sid:
            name = twstock.codes[sid].name if sid in twstock.codes else "未知"[cite: 2]
            line_bot_api.reply_message(event.reply_token, create_stock_menu(sid, name))
        else:
            line_bot_api.reply_message(event.reply_token, TextMessage(text=f"找不到「{msg}」相關股票"))[cite: 2]
    except Exception as e:
        line_bot_api.reply_message(event.reply_token, TextMessage(text=f"系統錯誤: {str(e)}"))[cite: 2]

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
    port = int(os.environ.get("PORT", 10000))[cite: 2]
    app.run(host='0.0.0.0', port=port)[cite: 2]
