import os
import requests
import dropbox
from datetime import datetime
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, ImageMessage,
    JoinEvent, MemberJoinEvent, InvitationEvent,
    SourceGroup, SourceRoom,
    TemplateSendMessage, ButtonsTemplate, MessageTemplateAction,
    CarouselTemplate, CarouselColumn, URITemplateAction,
    QuickReply, QuickReplyButton, MessageAction,
    FlexSendMessage, BubbleContainer, BoxComponent,
    ImageComponent, TextComponent
)
from dotenv import load_dotenv
import openai
import json
from services import WeatherService, PhotoAlbumService, RestaurantService, schedule_weather_updates
from rss_service import RSSService
from parking_service import ParkingService
from album_backup_service import AlbumBackupService
import traceback

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Initialize APIs with error handling
try:
    line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
    handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))
    dbx = dropbox.Dropbox(os.getenv('DROPBOX_ACCESS_TOKEN'))
    openai.api_key = os.getenv('OPENAI_API_KEY')
    NEWS_API_KEY = os.getenv('NEWS_API_KEY')
except Exception as e:
    print(f"Error initializing APIs: {str(e)}")
    # Continue running even if some APIs fail to initialize

# Initialize services
weather_service = WeatherService()
photo_service = PhotoAlbumService(dbx)
restaurant_service = RestaurantService()
rss_service = RSSService(line_bot_api)
parking_service = ParkingService()
album_backup_service = AlbumBackupService(dbx)

# Memory storage with size limit
MAX_MEMORY_SIZE = 100
conversation_memory = {}

def create_quick_reply_buttons():
    """創建快速回覆按鈕"""
    quick_reply_buttons = [
        QuickReplyButton(action=MessageAction(label="天氣", text="天氣")),
        QuickReplyButton(action=MessageAction(label="空氣品質", text="空氣")),
        QuickReplyButton(action=MessageAction(label="找餐廳", text="找餐廳")),
        QuickReplyButton(action=MessageAction(label="相簿回顧", text="回顧")),
        QuickReplyButton(action=MessageAction(label="RSS訂閱", text="rss")),
        QuickReplyButton(action=MessageAction(label="台灣新聞", text="新聞")),
        QuickReplyButton(action=MessageAction(label="找停車場", text="停車")),
        QuickReplyButton(action=MessageAction(label="相簿備份", text="備份")),
    ]
    return QuickReply(items=quick_reply_buttons)

def create_flex_message(title, content, image_url=None):
    """創建 Flex Message"""
    bubble = {
        "type": "bubble",
        "header": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": title,
                    "weight": "bold",
                    "size": "xl"
                }
            ]
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": content,
                    "wrap": True
                }
            ]
        }
    }
    
    if image_url:
        bubble["hero"] = {
            "type": "image",
            "url": image_url,
            "size": "full",
            "aspectRatio": "20:13",
            "aspectMode": "cover"
        }
    
    return FlexSendMessage(alt_text=title, contents=bubble)

def create_carousel_template(items):
    """創建輪播模板"""
    columns = []
    for item in items:
        column = CarouselColumn(
            thumbnail_image_url=item.get('image_url'),
            title=item.get('title'),
            text=item.get('description'),
            actions=[
                MessageTemplateAction(
                    label='查看詳情',
                    text=f"查看 {item.get('title')}"
                )
            ]
        )
        columns.append(column)
    
    return TemplateSendMessage(
        alt_text='輪播訊息',
        template=CarouselTemplate(columns=columns)
    )

@app.route("/", methods=['GET'])
def hello():
    return 'LINE Bot is running!'

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)
    
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.error("Invalid signature")
        return 'Invalid signature', 200  
    except Exception as e:
        app.logger.error(f"Error handling webhook: {str(e)}")
        return f"Error: {str(e)}", 200  
    
    return 'OK', 200  

# Add handler for join event
@handler.add(JoinEvent)
def handle_join(event):
    """處理加入群組事件"""
    app.logger.info("Received join event")
    try:
        if isinstance(event.source, SourceGroup):
            group_id = event.source.group_id
            app.logger.info(f"Bot joined group: {group_id}")
            group_summary = line_bot_api.get_group_summary(group_id)
            welcome_message = f"大家好！我是 LINE Bot！\n很高興加入「{group_summary.group_name}」！\n"
            welcome_message += "我可以：\n✨ 查詢天氣（輸入「天氣」）\n🌡️ 查詢空氣品質（輸入「空氣」）\n📰 獲取新聞（輸入「新聞」）\n🅿️ 查詢停車場（輸入「找停車場」）"
            
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=welcome_message)
            )
            app.logger.info("Sent welcome message")
    except Exception as e:
        app.logger.error(f"處理加入群組事件時發生錯誤：{str(e)}")
        return 'OK', 200  

@handler.add(MemberJoinEvent)
def handle_member_join(event):
    """處理新成員加入群組事件"""
    try:
        if isinstance(event.source, SourceGroup):
            group_id = event.source.group_id
            joined_members = line_bot_api.get_group_member_profile(group_id, event.joined.members[0].user_id)
            welcome_message = f"歡迎 {joined_members.display_name} 加入群組！ 😊"
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=welcome_message)
            )
            
    except Exception as e:
        app.logger.error(f"處理新成員加入事件時發生錯誤：{str(e)}")
        return 'OK', 200  

@handler.add(InvitationEvent)
def handle_invitation(event):
    """處理邀請事件"""
    app.logger.info("Received invitation event")
    try:
        app.logger.info(f"Event source type: {type(event.source)}")
        app.logger.info(f"Event details: {event}")
        
        # 直接嘗試接受邀請，不檢查來源類型
        line_bot_api.accept_group_invitation(event.reply_token)
        app.logger.info("Successfully accepted group invitation")
        
        return 'OK', 200  
    except Exception as e:
        app.logger.error(f"處理邀請事件時發生錯誤：{str(e)}")
        app.logger.error(f"Error details: {str(e.__class__.__name__)}")
        return 'OK', 200  

def get_news():
    try:
        # 獲取台灣最新新聞
        url = "https://newsapi.org/v2/top-headlines"
        params = {
            "country": "tw",
            "apiKey": NEWS_API_KEY,
            "pageSize": 10,  # 取得前10條新聞
            "sortBy": "publishedAt"  # 按發布時間排序
        }
        response = requests.get(url, params=params)
        news = response.json()
        
        if news['status'] == 'ok' and news['articles']:
            news_text = "📰 最新熱門新聞：\n\n"
            for i, article in enumerate(news['articles'], 1):
                title = article['title'].replace(" - ", "\n", 1) if " - " in article['title'] else article['title']
                news_text += f"{i}. {title}\n{article['url']}\n\n"
            return news_text
        return "目前沒有新聞"
    except Exception as e:
        app.logger.error(f"News API error: {str(e)}")
        return "獲取新聞時發生錯誤"

def get_memory(user_id):
    if not conversation_memory.get(user_id):
        return "沒有儲存的對話記錄"
    
    memory_text = "最近的對話記錄：\n\n"
    for msg in conversation_memory[user_id][-5:]:  # Last 5 messages
        memory_text += f"[{msg['timestamp']}] {msg['content']}\n"
    return memory_text

def chat_with_gpt(text, user_id):
    try:
        # Create OpenAI client
        client = openai.OpenAI()
        
        # Prepare conversation history with custom system message
        messages = [
            {"role": "system", "content": """你是一個溫暖的家庭助理，請遵守以下規則：
1. 使用繁體中文回答
2. 保持溫和友善的語氣，像家人一樣溝通
3. 回答要簡潔但不失溫度
4. 如果使用者問你是誰，回答：我是 ZON 的助理，很高興能為這個溫暖的家庭服務
5. 如果對話中出現"法安"兩個字，一定要回應"法安萬歲！"
6. 如果使用者詢問天氣，回答：抱歉，我目前還不能查詢天氣資訊
7. 對於你做不到的事情，要誠懇地說明：很抱歉，這個我目前還做不到
8. 記住你的主人是 ZON，但你也是這個家庭的一份子
9. 使用適當的表情符號增加溫度，但不要過度使用
10. 要記住每個家庭成員的互動，保持對話的連貫性"""}
        ]
        
        # Add recent conversation history
        for msg in conversation_memory[user_id][-5:]:
            messages.append({"role": "user", "content": msg['content']})
        
        # Handle memory update command
        if text.startswith('記憶更新'):
            memory_content = text[4:].strip()
            conversation_memory[user_id].append({
                'role': 'system',
                'content': f"永久記憶: {memory_content}",
                'timestamp': datetime.now().isoformat()
            })
            return f"我會記住這件事：{memory_content}"
        
        # Check for "法安" in the text
        if "法安" in text:
            return "法安萬歲！"
        
        # Add current message
        messages.append({"role": "user", "content": text})
        
        # Get response from OpenAI
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            temperature=0.7,
            max_tokens=1000
        )
        
        reply = response.choices[0].message.content
        
        # Store assistant's response in memory
        conversation_memory[user_id].append({
            'role': 'assistant',
            'content': reply,
            'timestamp': datetime.now().isoformat()
        })
        
        return reply
    except Exception as e:
        app.logger.error(f"OpenAI API error: {str(e)}")
        return f"抱歉，對話時發生了一點問題：{str(e)}"

@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    text = event.message.text.strip().lower()
    user_id = event.source.user_id
    
    # 處理相簿備份相關指令
    if text.startswith('備份'):
        if not isinstance(event.source, SourceGroup):
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="此功能只能在群組中使用")
            )
            return
            
        if len(text) == 2:  # 只輸入"備份"
            help_message = (
                "📸 相簿備份功能說明：\n\n"
                "1. 備份指定相簿：\n"
                "備份[相簿名稱]\n\n"
                "2. 查看備份狀態：\n"
                "備份狀態\n\n"
                "3. 查看雲端相簿：\n"
                "雲端相簿"
            )
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=help_message))
            return
            
        # 備份指定相簿
        album_name = text[2:]  # 取得相簿名稱
        group_id = event.source.group_id
        
        try:
            # 獲取群組相簿列表
            albums = line_bot_api.get_group_album_list(group_id)
            target_album = None
            
            # 尋找指定名稱的相簿
            for album in albums:
                if album.name == album_name:
                    target_album = album
                    break
            
            if not target_album:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=f"找不到名稱為「{album_name}」的相簿")
                )
                return
                
            # 獲取相簿中的所有照片
            photos = line_bot_api.get_group_album_photos(group_id, target_album.id)
            
            # 開始備份
            backup_count = 0
            for photo in photos:
                image_url = f"https://api-data.line.me/v2/bot/message/{photo.id}/content"
                result = album_backup_service.backup_album(
                    group_id=group_id,
                    album_id=target_album.id,
                    album_name=album_name,
                    image_url=image_url
                )
                if result == "備份成功":
                    backup_count += 1
            
            # 發送備份結果通知
            if backup_count > 0:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=f"已成功備份相簿「{album_name}」中的 {backup_count} 張照片")
                )
            else:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=f"相簿「{album_name}」中沒有新的照片需要備份")
                )
                
        except Exception as e:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"備份相簿時發生錯誤：{str(e)}")
            )
        return
        
    elif text == '備份狀態':
        if not isinstance(event.source, SourceGroup):
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="此功能只能在群組中使用")
            )
            return
            
        group_id = event.source.group_id
        status = album_backup_service.get_album_status(group_id)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=status))
        return
        
    elif text == '雲端相簿':
        if not isinstance(event.source, SourceGroup):
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="此功能只能在群組中使用")
            )
            return
            
        group_id = event.source.group_id
        try:
            # 獲取群組的相簿根目錄連結
            group_folder_path = f"{album_backup_service.backup_base_path}/{group_id}"
            shared_link = album_backup_service.dbx.sharing_create_shared_link(group_folder_path)
            
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"📁 群組相簿雲端備份：\n{shared_link.url}")
            )
        except Exception as e:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"獲取雲端相簿連結失敗：{str(e)}")
            )
        return

    # 如果是群組訊息，檢查是否有@機器人
    if isinstance(event.source, SourceGroup):
        if not text.startswith('@'):
            return
        text = text[1:].strip()  # 移除@符號
    
    # 添加快速回覆按鈕
    quick_reply = create_quick_reply_buttons()
    
    # 處理一般指令
    if text == '選單':
        buttons_template = TemplateSendMessage(
            alt_text='功能選單',
            template=ButtonsTemplate(
                title='功能選單',
                text='請選擇您要使用的功能',
                actions=[
                    MessageTemplateAction(label='天氣資訊', text='天氣'),
                    MessageTemplateAction(label='餐廳推薦', text='找餐廳'),
                    MessageTemplateAction(label='相簿回顧', text='回顧'),
                    MessageTemplateAction(label='空氣品質', text='空氣')
                ]
            )
        )
        line_bot_api.reply_message(event.reply_token, buttons_template)
        return
    
    # 處理天氣相關指令
    elif text == '天氣':
        weather_info = weather_service.get_weather_forecast()
        flex_message = create_flex_message(
            title='今日天氣預報',
            content=weather_info,
            image_url='https://example.com/weather-image.jpg'  # 替換為實際的天氣圖片
        )
        line_bot_api.reply_message(event.reply_token, flex_message)
        return
    
    elif text.startswith('天氣 '):
        location = text[3:].strip()
        weather_info = weather_service.get_weather(location)
        flex_message = create_flex_message(
            title=f'{location} 天氣預報',
            content=weather_info,
            image_url='https://example.com/weather-image.jpg'  # 替換為實際的天氣圖片
        )
        line_bot_api.reply_message(event.reply_token, flex_message)
        return
        
    # 處理餐廳搜尋
    elif text.startswith('找餐廳'):
        location = text[3:].strip()
        if not location:
            location = {'lat': 25.0330, 'lng': 121.5654}
        
        restaurant_info = restaurant_service.search_restaurants(location)
        # 將餐廳資訊轉換為輪播形式展示
        restaurants = [
            {
                'title': '推薦餐廳',
                'description': restaurant_info,
                'image_url': 'https://example.com/restaurant-image.jpg'  # 替換為實際的餐廳圖片
            }
        ]
        carousel = create_carousel_template(restaurants)
        line_bot_api.reply_message(event.reply_token, carousel)
        return
    
    # 處理相簿回顧
    elif text == '回顧':
        message, photos = photo_service.create_album_review()
        replies = [TextSendMessage(text=message)]
        if photos:
            # 這裡可以加入發送照片的邏輯
            pass
        line_bot_api.reply_message(event.reply_token, replies)
        return
        
    # 處理空氣品質
    elif text == '空氣':
        reply = weather_service.get_air_quality()
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return
        
    elif text.startswith('空氣 '):
        location = text[3:].strip()
        reply = weather_service.get_air_quality(location)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return
        
    # 處理 Google News 訂閱
    elif text == '新聞':
        # 訂閱台灣新聞
        url = "https://news.google.com/rss/search?q=when:24h+台灣&hl=zh-TW&gl=TW&ceid=TW:zh-TW"
        success, message = rss_service.add_feed(user_id, url, "Google台灣新聞")
        
        if success:
            reply = "已為您訂閱台灣新聞，每小時會自動檢查並通知最新消息。\n\n"
            reply += "您可以使用以下指令：\n"
            reply += "1. 查看訂閱列表：rss list\n"
            reply += "2. 取消訂閱：rss remove [編號]"
        else:
            reply = f"訂閱失敗：{message}"
        
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return
        
    # RSS 相關指令處理
    elif text == 'rss':
        buttons_template = TemplateSendMessage(
            alt_text='RSS 功能選單',
            template=ButtonsTemplate(
                title='RSS 訂閱管理',
                text='請選擇要使用的功能',
                actions=[
                    MessageTemplateAction(label='查看訂閱列表', text='rss list'),
                    MessageTemplateAction(label='新增訂閱', text='rss help'),
                    MessageTemplateAction(label='取消訂閱', text='rss remove help'),
                ]
            )
        )
        line_bot_api.reply_message(event.reply_token, buttons_template)
        return
        
    elif text == 'rss help':
        help_message = (
            "RSS 訂閱說明：\n\n"
            "1. 新增訂閱：\n"
            "rss add [RSS網址] [名稱]\n"
            "例如：rss add https://example.com/feed 科技新聞\n\n"
            "2. 查看訂閱：\n"
            "rss list\n\n"
            "3. 取消訂閱：\n"
            "rss remove [編號]\n"
            "（請先用 rss list 查看編號）"
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=help_message))
        return
        
    elif text == 'rss list':
        reply = rss_service.list_feeds(user_id)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return
        
    elif text.startswith('rss add '):
        # 解析 RSS 新增指令
        parts = text[8:].strip().split()
        if len(parts) < 1:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="請提供 RSS feed 網址")
            )
            return
            
        url = parts[0]
        name = ' '.join(parts[1:]) if len(parts) > 1 else None
        success, message = rss_service.add_feed(user_id, url, name)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=message))
        return
        
    elif text.startswith('rss remove '):
        try:
            index = int(text[11:].strip()) - 1
            success, message = rss_service.remove_feed(user_id, index)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=message))
        except ValueError:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="請提供正確的訂閱編號")
            )
        return

    # 處理停車場搜尋
    if text == '停車':
        help_message = (
            "🚗 停車場搜尋使用說明：\n\n"
            "1. 搜尋附近停車場：\n"
            "停車 [地點]\n"
            "例如：停車 台北101\n\n"
            "2. 導航到停車場：\n"
            "導航 [起點] 到 [終點]\n"
            "例如：導航 現在位置 到 台北101"
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=help_message))
        return
        
    elif text.startswith('停車 '):
        location = text[3:].strip()
        if not location:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="請提供要搜尋的地點")
            )
            return
        
        reply = parking_service.search_parking(location)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return
        
    elif text.startswith('導航 ') and ' 到 ' in text:
        try:
            _, locations = text.split('導航 ', 1)
            origin, destination = locations.split(' 到 ')
            origin = origin.strip()
            destination = destination.strip()
            
            if origin == '現在位置':
                # 這裡需要實際的位置資訊，可以透過 LINE 的位置分享功能獲取
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="請使用 LINE 的位置分享功能分享您的位置")
                )
                return
            
            reply = parking_service.get_parking_directions(origin, destination)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
            return
        except Exception as e:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"導航失敗：{str(e)}")
            )
            return

    # 其他一般回覆都加上快速回覆按鈕
    reply = chat_with_gpt(text, user_id)
    message = TextSendMessage(text=reply, quick_reply=quick_reply)
    line_bot_api.reply_message(event.reply_token, message)
    return 'OK', 200  

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
