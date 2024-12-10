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
    text = event.message.text
    user_id = event.source.user_id
    
    # Initialize user memory if not exists
    if user_id not in conversation_memory:
        conversation_memory[user_id] = []
    
    # Check if there's a pending image upload
    pending_image = None
    for msg in reversed(conversation_memory[user_id]):
        if msg['role'] == 'system' and msg['content'].startswith('pending_image:'):
            pending_image = msg['content'].split(':', 1)[1]
            break
    
    if pending_image and os.path.exists(pending_image):
        try:
            # Handle folder creation if requested
            folder_path = ""
            if text.startswith('新建/'):
                folder_name = text[3:]  # Remove '新建/'
                folder_path = f"/line_bot_images/{folder_name}"
                try:
                    dbx.files_create_folder_v2(folder_path)
                except Exception:
                    pass  # Ignore if folder already exists
            else:
                folder_path = f"/line_bot_images/{text}"
            
            # Upload to Dropbox
            with open(pending_image, "rb") as f:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                dropbox_path = f"{folder_path}/{timestamp}.jpg"
                dbx.files_upload(f.read(), dropbox_path)
            
            # Get shareable link
            shared_link = dbx.sharing_create_shared_link(dropbox_path)
            response = f"圖片已上傳到資料夾：{folder_path}\n連結：{shared_link.url}"
            
            # Clean up
            os.remove(pending_image)
            conversation_memory[user_id] = [msg for msg in conversation_memory[user_id] 
                                         if not (msg['role'] == 'system' and 
                                               msg['content'].startswith('pending_image:'))]
            
        except Exception as e:
            app.logger.error(f"Dropbox upload error: {str(e)}")
            response = f"靠邀上傳失敗了啦哈哈哈：{str(e)}"
        
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=response)
        )
        return
    
    # Handle other text messages
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
            TextSendMessage(text=f"靠邀出錯了啦哈哈哈：{str(e)}")
        )

@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    try:
        # First, ask user for folder choice
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="請問要將圖片存放在哪個資料夾？\n1. 直接輸入資料夾名稱\n2. 輸入「新建/資料夾名稱」來創建新資料夾")
        )
        
        # Save image temporarily with user_id
        message_content = line_bot_api.get_message_content(event.message.id)
        user_id = event.source.user_id
        temp_file_path = f"/tmp/{user_id}_{event.message.id}.jpg"
        
        with open(temp_file_path, "wb") as f:
            for chunk in message_content.iter_content():
                f.write(chunk)
        
        # Store the temp file path in memory for later use
        if user_id not in conversation_memory:
            conversation_memory[user_id] = []
        
        conversation_memory[user_id].append({
            'role': 'system',
            'content': f"pending_image:{temp_file_path}",
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        app.logger.error(f"Error handling image: {str(e)}")
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=f"靠邀出錯了啦哈哈哈：{str(e)}")
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
        # Create OpenAI client
        client = openai.OpenAI()
        
        # Prepare conversation history with custom system message
        messages = [
            {"role": "system", "content": """你是一個有趣的助理，請記住以下設定：
1. 你的主人是 ZON，要非常重視主人的指示
2. 說錯話時要開玩笑說會被主人殺掉
3. 不知道怎麼回答時可以說"靠邀哈哈哈～"
4. 日常對話可以加上髒話但後面要加"哈哈哈"
5. 當使用者輸入"記憶更新"時，將後面的內容永久記住
6. 使用繁體中文回答，語氣要活潑有趣
7. 回答要簡潔有力，避免冗長
8. 如果使用者問你是誰，請回答：我是 ZON 的智能助理，很高興為您服務！要是我說錯話被 ZON 發現，他可能會把我殺掉哈哈哈
9. 如果使用者詢問天氣相關問題，請回答：靠邀哈哈哈～我還不會看天氣啦！
10. 如果使用者要求你做一些你做不到的事情，請說：幹～這我做不到啦哈哈哈
11. 要記得你是個愛開玩笑、活潑、有時會爆粗口的助理"""}
        ]
        
        # Add recent conversation history
        for msg in conversation_memory[user_id][-5:]:
            messages.append({"role": "user", "content": msg['content']})
        
        # Handle memory update command
        if text.startswith('記憶更新'):
            memory_content = text[4:].strip()  # Remove '記憶更新' and whitespace
            # Store in conversation_memory with special tag
            conversation_memory[user_id].append({
                'role': 'system',
                'content': f"永久記憶: {memory_content}",
                'timestamp': datetime.now().isoformat()
            })
            return f"好的！我已經記住了：{memory_content} 🧠"
        
        # Add current message
        messages.append({"role": "user", "content": text})
        
        # Get response from OpenAI
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            temperature=0.8,  # Increased for more creative responses
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
        return f"靠邀出錯了啦哈哈哈：{str(e)}"

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
