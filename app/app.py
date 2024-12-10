import os
import requests
import dropbox
from datetime import datetime
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    ImageMessage, ImageSendMessage
)
from dotenv import load_dotenv
import openai
import json

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

# Memory storage with size limit
MAX_MEMORY_SIZE = 100
conversation_memory = {}

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
        abort(400)
    except Exception as e:
        app.logger.error(f"Error handling webhook: {str(e)}")
        abort(500)
    
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    text = event.message.text.lower()
    user_id = event.source.user_id
    
    # Initialize user memory if not exists
    if user_id not in conversation_memory:
        conversation_memory[user_id] = []
    
    # Limit memory size
    if len(conversation_memory[user_id]) >= MAX_MEMORY_SIZE:
        conversation_memory[user_id] = conversation_memory[user_id][-MAX_MEMORY_SIZE:]
    
    # Store message in memory
    conversation_memory[user_id].append({
        'role': 'user',
        'content': text,
        'timestamp': datetime.now().isoformat()
    })
    
    try:
        # Handle different commands
        if text.startswith('/news'):
            response = get_news()
        elif text.startswith('/memory'):
            response = get_memory(user_id)
        elif text.startswith('/clear'):
            conversation_memory[user_id] = []
            response = "記憶已清除！"
        else:
            response = chat_with_gpt(text, user_id)
        
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=response)
        )
    except Exception as e:
        app.logger.error(f"Error handling message: {str(e)}")
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="抱歉，處理訊息時發生錯誤。")
        )

@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    try:
        message_content = line_bot_api.get_message_content(event.message.id)
        
        # Save image temporarily
        temp_file_path = f"/tmp/{event.message.id}.jpg"
        with open(temp_file_path, "wb") as f:
            for chunk in message_content.iter_content():
                f.write(chunk)
        
        # Upload to Dropbox
        try:
            with open(temp_file_path, "rb") as f:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                dropbox_path = f"/line_bot_images/{timestamp}.jpg"
                dbx.files_upload(f.read(), dropbox_path)
            
            # Get shareable link
            shared_link = dbx.sharing_create_shared_link(dropbox_path)
            response = f"圖片已上傳到 Dropbox！\n連結：{shared_link.url}"
        except Exception as e:
            app.logger.error(f"Dropbox upload error: {str(e)}")
            response = f"上傳失敗：{str(e)}"
        finally:
            # Clean up temp file
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
        
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=response)
        )
    except Exception as e:
        app.logger.error(f"Error handling image: {str(e)}")
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="抱歉，處理圖片時發生錯誤。")
        )

def get_news():
    try:
        url = f"https://newsapi.org/v2/top-headlines?country=tw&apiKey={NEWS_API_KEY}"
        response = requests.get(url)
        news = response.json()
        
        if news['status'] == 'ok':
            articles = news['articles'][:5]  # Get top 5 news
            news_text = "最新新聞：\n\n"
            for i, article in enumerate(articles, 1):
                news_text += f"{i}. {article['title']}\n{article['url']}\n\n"
            return news_text
        return "獲取新聞時出現錯誤"
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
        # Prepare conversation history
        messages = [
            {"role": "system", "content": "你是一個友善的助手，請用繁體中文回答。"}
        ]
        
        # Add recent conversation history
        for msg in conversation_memory[user_id][-5:]:
            messages.append({"role": "user", "content": msg['content']})
        
        # Add current message
        messages.append({"role": "user", "content": text})
        
        # Get response from OpenAI
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages
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
        return f"與 AI 對話時發生錯誤：{str(e)}"

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
