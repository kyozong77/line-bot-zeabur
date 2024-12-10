import os
import json
import requests
from datetime import datetime, timedelta
import googlemaps
from dateutil.relativedelta import relativedelta
import schedule
import time
from threading import Thread
from dotenv import load_dotenv

load_dotenv()

class WeatherService:
    def __init__(self):
        self.api_key = os.getenv('WEATHER_API_KEY')
        self.base_url = "http://api.openweathermap.org/data/2.5"
        self.aqi_url = "http://api.openweathermap.org/data/2.5/air_pollution"

    def get_weather_forecast(self, city="Taipei"):
        """獲取天氣預報"""
        try:
            url = f"{self.base_url}/forecast"
            params = {
                'q': city,
                'appid': self.api_key,
                'units': 'metric',
                'lang': 'zh_tw'
            }
            response = requests.get(url, params=params)
            data = response.json()
            
            if response.status_code == 200:
                today_forecast = data['list'][0]
                weather_desc = today_forecast['weather'][0]['description']
                temp = today_forecast['main']['temp']
                humidity = today_forecast['main']['humidity']
                rain_prob = today_forecast.get('pop', 0) * 100
                
                message = f"今日天氣預報：\n"
                message += f"天氣狀況：{weather_desc}\n"
                message += f"溫度：{temp}°C\n"
                message += f"濕度：{humidity}%\n"
                
                if rain_prob > 30:
                    message += f"降雨機率：{rain_prob}%\n"
                    message += "提醒：今天可能會下雨，記得帶傘！☔"
                
                return message
            return "抱歉，無法獲取天氣資訊"
        except Exception as e:
            return f"獲取天氣資訊時發生錯誤：{str(e)}"

    def get_air_quality(self, lat=25.0330, lon=121.5654):  # 預設台北市座標
        """獲取空氣品質資訊"""
        try:
            params = {
                'lat': lat,
                'lon': lon,
                'appid': self.api_key
            }
            response = requests.get(self.aqi_url, params=params)
            data = response.json()
            
            if response.status_code == 200:
                aqi = data['list'][0]['main']['aqi']
                aqi_levels = {
                    1: "優良 😊",
                    2: "普通 😐",
                    3: "對敏感族群不健康 😷",
                    4: "不健康 🚫",
                    5: "非常不健康 ⚠️"
                }
                return f"目前空氣品質：{aqi_levels.get(aqi, '未知')}"
            return "抱歉，無法獲取空氣品質資訊"
        except Exception as e:
            return f"獲取空氣品質資訊時發生錯誤：{str(e)}"

class PhotoAlbumService:
    def __init__(self, dropbox_client):
        self.dropbox_client = dropbox_client
        
    def organize_photos_by_date(self, file_path, upload_date):
        """根據日期整理照片"""
        year = upload_date.strftime('%Y')
        month = upload_date.strftime('%m')
        target_path = f"/FamilyPhotos/{year}/{month}/{os.path.basename(file_path)}"
        return target_path
    
    def create_album_review(self, days_ago=365):
        """創建相簿回顧"""
        try:
            target_date = datetime.now() - timedelta(days=days_ago)
            target_path = f"/FamilyPhotos/{target_date.strftime('%Y')}/{target_date.strftime('%m')}"
            
            result = self.dropbox_client.files_list_folder(target_path)
            photos = []
            for entry in result.entries:
                if entry.path_lower.endswith(('.jpg', '.jpeg', '.png')):
                    photos.append(entry.path_display)
            
            if photos:
                message = f"來看看去年這個時候的回憶！\n"
                message += f"找到了 {len(photos)} 張照片 📸\n"
                # 這裡可以加入取得照片縮圖或直接分享照片的邏輯
                return message, photos
            return "這個時候還沒有照片呢！", []
        except Exception as e:
            return f"獲取相簿回顧時發生錯誤：{str(e)}", []

class RestaurantService:
    def __init__(self):
        self.gmaps = googlemaps.Client(key=os.getenv('GOOGLE_MAPS_API_KEY'))
    
    def search_restaurants(self, location, radius=1000, keyword=None):
        """搜尋附近餐廳"""
        try:
            # 如果輸入的是地址，先轉換成經緯度
            if isinstance(location, str):
                geocode_result = self.gmaps.geocode(location)
                if geocode_result:
                    location = geocode_result[0]['geometry']['location']
                else:
                    return "找不到指定的位置"
            
            # 搜尋餐廳
            places_result = self.gmaps.places_nearby(
                location=location,
                radius=radius,
                type='restaurant',
                keyword=keyword,
                language='zh-TW'
            )
            
            if places_result.get('results'):
                restaurants = places_result['results'][:5]  # 取前5筆結果
                message = "為您推薦以下餐廳：\n\n"
                
                for i, rest in enumerate(restaurants, 1):
                    name = rest.get('name', '未知')
                    rating = rest.get('rating', '無評分')
                    address = rest.get('vicinity', '地址未提供')
                    
                    message += f"{i}. {name}\n"
                    message += f"   評分：{rating}⭐\n"
                    message += f"   地址：{address}\n\n"
                
                return message
            return "抱歉，在指定範圍內找不到餐廳"
        except Exception as e:
            return f"搜尋餐廳時發生錯誤：{str(e)}"

def schedule_weather_updates(line_bot_api, group_id):
    """排程天氣更新"""
    weather_service = WeatherService()
    
    def send_morning_weather():
        weather_msg = weather_service.get_weather_forecast()
        aqi_msg = weather_service.get_air_quality()
        full_msg = f"{weather_msg}\n\n{aqi_msg}"
        
        try:
            line_bot_api.push_message(group_id, TextSendMessage(text=full_msg))
        except Exception as e:
            print(f"發送天氣資訊時發生錯誤：{str(e)}")
    
    # 設定每天早上7點發送天氣資訊
    schedule.every().day.at("07:00").do(send_morning_weather)
    
    # 在背景執行排程
    def run_schedule():
        while True:
            schedule.run_pending()
            time.sleep(60)
    
    schedule_thread = Thread(target=run_schedule, daemon=True)
    schedule_thread.start()
