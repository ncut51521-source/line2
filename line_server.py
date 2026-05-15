import os, re, requests, urllib3, json
from flask import Flask, request
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, FlexSendMessage

# 徹底禁用 SSL 驗證警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# ========= 核心設定 =========
# 請確保你的 Access Token 和 Secret 是正確的
LINE_ACCESS_TOKEN = "dX9zPn4sFpqbNCL+4SBGEsSGtMcSeYVZ1GEv5MNGOeISygMC896e141rVqOkETcEkRNktPujTjRf4Cn1FyoU2+S8sPPhSEj1LhTKRwLI5HQyaj09mE1ozJlM+6GKeC6JCAVaFyJxuTE3fanlzC82FQdB04t89/1O/w1cDnyilFU="
LINE_HANDLER_SECRET = "c1ef088ebc7f9dd0f04b5d7a7db03dfc" 

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_HANDLER_SECRET)

def get_stock_info_text(sid, info_type):
    # 使用通用的 Headers 偽裝瀏覽器
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    try:
        if info_type == "三大法人":
            # 備援資料源：直接從第三方快取介面抓取 (這通常不會鎖 IP)
            url = f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockInstitutionalInvestorsBuySell&data_id={sid}"
            res = requests.get(url, timeout=10)
            data = res.json()
            
            if data.get('msg') == 'success' and len(data.get('data', [])) > 0:
                # 取最後一筆（最新）資料
                latest = data['data'][-1]
                buy = int(latest.get('buy', 0))
                sell = int(latest.get('sell', 0))
                diff = (buy - sell) // 1000 # 換算成張
                
                return (f"🏦 {sid} 三大法人(最新交易日)\n"
                        f"📅 日期：{latest.get('date')}\n"
                        f"------------------\n"
                        f"📊 買賣差額：{diff:,} 張\n"
                        f"👤 單位說明：正數為買超\n"
                        f"✅ 數據來源：第三方備援介面")
            
            return f"⚠️ 目前無法從備援接口取得 {sid} 資料"

        elif info_type == "即時五檔":
            # 改用證交所另一個較寬鬆的即時資訊介面
            url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_{sid}.tw"
            res = requests.get(url, verify=False, timeout=10, headers=headers)
            data = res.json()
            
            if data.get('msgArray'):
                info = data['msgArray'][0]
                # 獲取買進與賣出的五檔價格
                b_list = info.get('b', '---').split('_')[:5]
                a_list = info.get('a', '---').split('_')[:5]
                
                return (f"📊 {sid} 即時五檔\n"
                        f"買進: {', '.join(b_list)}\n"
                        f"賣出: {', '.join(a_list)}\n"
                        f"💰 現價: {info.get('z', '---')}")
            
            return "❌ 證交所即時接口目前無回應，請於開盤時間重試"

    except Exception as e:
        return f"❌ 數據處理失敗: {str(e)}"

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
    
    # 功能按鈕過濾
    for action in ["即時五檔", "三大法人"]:
        if action in msg:
            sid = msg.split(" ")[0]
            line_bot_api.reply_message(event.reply_token, TextMessage(text=get_stock_info_text(sid, action)))
            return

    # 純代碼輸入顯示選單
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
              {"type": "button", "style": "primary", "color": "#007bff", "action": {"type": "message", "label": "即時五檔", "text": f"{sid} 即時五檔"}}
            ]
          }
        }
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
