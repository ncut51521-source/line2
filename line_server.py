import os, re, datetime, traceback
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, ImageSendMessage, FlexSendMessage

app = Flask(__name__)

# ========= 核心設定 (請確認金鑰正確) =========
LINE_ACCESS_TOKEN = "dX9zPn4sFpqbNCL+4SBGEsSGtMcSeYVZ1GEv5MNGOeISygMC896e141rVqOkETcEkRNktPujTjRf4Cn1FyoU2+S8sPPhSEj1LhTKRwLI5HQyaj09mE1ozJlM+6GKeC6JCAVaFyJxuTE3fanlzC82FQdB04t89/1O/w1cDnyilFU="
LINE_HANDLER_SECRET = "255e4550a9999d33b4d2cccd8c8c8af8" 

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_HANDLER_SECRET)

# 只有在需要時才載入這些大套件，避免啟動時卡住 Port Binding
def get_kline_url(sid, period='D'):
    import matplotlib
    matplotlib.use('Agg') 
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    import pandas as pd
    import mplfinance as mpf
    import twstock
    import cloudinary.uploader
    
    cloudinary.config( 
      cloud_name = "dzip2nboe", 
      api_key = "124438874888122", 
      api_secret = "X71kcLFVNKX-XYjKHCbCnMFAzCw" 
    )

    try:
        font_path = os.path.join(os.path.dirname(__file__), "NotoSansCJKtc-Regular.otf")
        my_font = font_manager.FontProperties(fname=font_path) if os.path.exists(font_path) else None

        stock = twstock.Stock(sid)
        if period == 'D':
            raw_data = stock.fetch_31()
            show_n = 24
            title_tag = "日線"
        elif period == 'W':
            raw_data = stock.fetch(2025, 1)
            show_n = 12
            title_tag = "週線"
        else:
            raw_data = stock.fetch(2024, 1)
            show_n = 12
            title_tag = "月線"

        if not raw_data: return "查無歷史資料"

        # 即時數據處理 (加上 try 避免沒數據時卡死)
        rt_price_text = ""
        rt_color = "black"
        try:
            rt_data = twstock.realtime.get(sid)
            if rt_data and rt_data.get('success'):
                curr = float(rt_data['realtime']['latest_trade_price'])
                prev = float(rt_data['realtime']['open']) 
                diff = curr - prev
                diff_pct = (diff / prev) * 100
                rt_color = "red" if diff > 0 else ("green" if diff < 0 else "black")
                rt_price_text = f"最新價: {curr} ({'+' if diff > 0 else ''}{diff:.2f}, {diff_pct:.2f}%)"
        except:
            rt_price_text = "即時資料獲取略過"

        df = pd.DataFrame([{'Date': d.date, 'Open': d.open, 'High': d.high, 'Low': d.low, 'Close': d.close, 'Volume': d.capacity} for d in raw_data])
        df['Date'] = pd.to_datetime(df['Date'])
        df.set_index('Date', inplace=True)
        
        if period == 'W':
            df = df.resample('W').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna()
        elif period == 'M':
            df = df.resample('M').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna()

        plot_df = df.tail(show_n)
        mc = mpf.make_marketcolors(up='red', down='green', edge='inherit', wick='inherit', volume='inherit')
        s = mpf.make_mpf_style(marketcolors=mc, gridstyle='--', y_on_right=True)
        
        tmp_path = "/tmp/k.png"
        fig, axes = mpf.plot(plot_df, type='candle', style=s, volume=True, mav=(5, 10), 
                             figsize=(12, 10), returnfig=True, 
                             datetime_format='%y/%m/%d', tight_layout=False)
        
        stock_name = twstock.codes[sid].name if sid in twstock.codes else ""
        fig.text(0.08, 0.96, f"{sid} {stock_name} ({title_tag})", fontsize=28, weight='black', fontproperties=my_font)
        fig.text(0.08, 0.92, rt_price_text, fontsize=24, weight='bold', color=rt_color, fontproperties=my_font)

        plt.subplots_adjust(top=0.90)
        fig.savefig(tmp_path, dpi=100, bbox_inches='tight')
        plt.close(fig)

        upload_res = cloudinary.uploader.upload(tmp_path)
        return upload_res.get("secure_url")
    except Exception as e:
        return f"繪圖失敗: {str(e)}"

def get_stock_id(name_or_id):
    import twstock
    name_or_id = name_or_id.upper().strip()
    if re.match(r'^\d{4,6}$', name_or_id):
        return name_or_id
    for sid, info in twstock.codes.items():
        if info.name == name_or_id:
            return sid
    return None

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    try:
        msg = event.message.text.strip()
        if any(k in msg for k in ["日線", "週線", "月線"]):
            parts = msg.split(" ")
            sid = parts[0]
            mode = 'W' if "週線" in msg else ('M' if "月線" in msg else 'D')
            url = get_kline_url(sid, period=mode)
            if url and url.startswith("http"):
                line_bot_api.reply_message(event.reply_token, ImageSendMessage(original_content_url=url, preview_image_url=url))
            else:
                line_bot_api.reply_message(event.reply_token, TextMessage(text=f"⚠️ {url}"))
            return

        sid = get_stock_id(msg)
        if sid:
            import twstock
            name = twstock.codes[sid].name if sid in twstock.codes else "未知"
            line_bot_api.reply_message(event.reply_token, create_kline_panel(sid, name))
        else:
            # 這裡之前有 jo4 的縮排錯誤，已修正
            line_bot_api.reply_message(event.reply_token, TextMessage(text=f"找不到「{msg}」相關股票"))
    except Exception as e:
        line_bot_api.reply_message(event.reply_token, TextMessage(text=f"發生錯誤: {str(e)}"))

def create_kline_panel(sid, name):
    return FlexSendMessage(
        alt_text=f"股票 {sid} {name}",
        contents={
          "type": "bubble",
          "body": {
            "type": "box", "layout": "vertical", "spacing": "md", "contents": [
              {"type": "text", "text": f"📈 {sid} {name}", "weight": "bold", "size": "xl", "align": "center"},
              {"type": "separator"},
              {"type": "button", "style": "primary", "color": "#007bff", "action": {"type": "message", "label": "查看日 K 線", "text": f"{sid} 日線"}},
              {"type": "button", "style": "primary", "color": "#28a745", "action": {"type": "message", "label": "查看週 K 線", "text": f"{sid} 週線"}},
              {"type": "button", "style": "primary", "color": "#fd7e14", "action": {"type": "message", "label": "查看月 K 線", "text": f"{sid} 月線"}}
            ]
          }
        }
    )

if __name__ == "__main__":
    # 使用環境變數的 Port，否則預設 10000
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
