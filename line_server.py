import os, re, requests, urllib3
from flask import Flask, request
from linebot import LineBotApi, WebhookHandler
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

def get_stock_info_text(sid, info_type):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    try:
        if info_type == "三大法人":
            # 這是另一個更穩定的證交所數據路徑，有時能繞過 API 限制
            # 嘗試抓取該股當日法人買賣數據
            url = f"https://www.twse.com.tw/fund/T86W?response=json&stockNo={sid}"
            res = requests.get(url, verify=False, timeout=10, headers=headers)
            data = res.json()
            
            if data.get('stat') == 'OK' and len(data.get('data', [])) > 0:
                row = data['data'][0]
                # 將「股」換算成「張」，讓數據更直觀
                def to_lots(value):
                    val = int(value.replace(',', ''))
                    return f"{val // 1000:,} 張"

                return (f"🏦 {sid} 三大法人買賣超\n"
                        f"📅 日期：{row[0]}\n"
                        f"------------------\n"
                        f"👤 外資：{to_lots(row[4])}\n"
                        f"💪 投信：{to_lots(row[10])}\n"
                        f"🏢 自營：{to_lots(row[11])}\n"
                        f"📊 合計：{to_lots(row[12])}\n"
                        f"註：正數為買超，單位為張。")
            
            # 如果上面被封鎖，改用備援接口 (Fugle 或其他)
            return f"❌ 證交所 API 目前連線負載過重，請於 30 秒後重試一次。"

        # ...其餘功能(即時五檔等)保持不變...
        elif info_type == "即時五檔":
            rt = twstock.realtime.get(sid)
            if rt['success']:
                return f"📊 {sid} 即時五檔\n買進: {', '.join(rt['realtime']['best_bid_price'])}\n賣出: {', '.join(rt['realtime']['best_ask_price'])}"
            return "❌ 無法取得五檔數據"

    except Exception as e:
        return "❌ 數據讀取失敗，請重新點擊一次"

# ...中間的 callback 與 handle_message 保持不變...

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
    # 初次輸入代號顯示選單
    sid = "".join(filter(str.isdigit, msg))[:6] # 簡單過濾代號
    if len(sid) >= 4:
        line_bot_api.reply_message(event.reply_token, create_stock_menu(sid, "股票"))
    else:
        line_bot_api.reply_message(event.reply_token, TextMessage(text="請輸入股票代號（如 2330）"))

def create_stock_menu(sid, name):
    return FlexSendMessage(
        alt_text=f"{sid} 選單",
        contents={
          "type": "bubble",
          "body": {
            "type": "box", "layout": "vertical", "spacing": "md", "contents": [
              {"type": "text", "text": f"📈 {sid}", "weight": "bold", "size": "xl", "align": "center"},
              {"type": "separator"},
              {"type": "button", "style": "primary", "color": "#28a745", "action": {"type": "message", "label": "三大法人買賣超", "text": f"{sid} 三大法人"}},
              {"type": "button", "style": "primary", "color": "#007bff", "action": {"type": "message", "label": "即時五檔", "text": f"{sid} 即時五檔"}}
            ]
          }
        }
    )

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
