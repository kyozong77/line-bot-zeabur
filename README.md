# LINE Bot

一個功能豐富的 LINE Bot，具有以下功能：

## 功能
- 基本的消息處理
- 圖片上傳到 Dropbox
- 新聞資訊獲取
- 記憶儲存和查詢
- 使用 OpenAI 進行對話

## 環境變數
需要設置以下環境變數：
```
LINE_CHANNEL_ACCESS_TOKEN=你的LINE Channel Access Token
LINE_CHANNEL_SECRET=你的LINE Channel Secret
DROPBOX_ACCESS_TOKEN=你的Dropbox Access Token
OPENAI_API_KEY=你的OpenAI API Key
NEWS_API_KEY=你的News API Key
```

## 部署到 Zeabur
1. 在 Zeabur 創建新專案
2. 連接 GitHub 倉庫
3. 設置環境變數
4. 部署完成後，在 LINE Developers 設置 Webhook URL

## 本地開發
```bash
# 安裝依賴
pip install -r requirements.txt

# 運行應用
python app/app.py
```
