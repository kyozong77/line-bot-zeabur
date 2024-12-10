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
        self.geo_url = "http://api.openweathermap.org/geo/1.0/direct"
        
    def _get_coordinates(self, city):
        """獲取城市的經緯度"""
        try:
            params = {
                'q': f"{city},TW",  # 限制在台灣範圍內搜尋
                'limit': 1,
                'appid': self.api_key
            }
            response = requests.get(self.geo_url, params=params)
            if response.status_code == 200:
                data = response.json()
                if data:
                    return data[0]['lat'], data[0]['lon']
            return None
        except Exception as e:
            print(f"獲取座標時發生錯誤：{str(e)}")
            return None

    def get_weather(self, city="台北市"):
        """獲取天氣預報"""
        try:
            # 先獲取城市座標
            coords = self._get_coordinates(city)
            if not coords:
                return f"抱歉，找不到 {city} 的位置資訊"
                
            lat, lon = coords
            
            # 獲取天氣資訊
            params = {
                'lat': lat,
                'lon': lon,
                'appid': self.api_key,
                'units': 'metric',  # 使用攝氏溫度
                'lang': 'zh_tw'     # 使用繁體中文
            }
            
            # 獲取當前天氣
            current_response = requests.get(f"{self.base_url}/weather", params=params)
            
            # 獲取天氣預報
            forecast_response = requests.get(f"{self.base_url}/forecast", params=params)
            
            if current_response.status_code == 200 and forecast_response.status_code == 200:
                current_data = current_response.json()
                forecast_data = forecast_response.json()
                
                # 解析當前天氣
                current_temp = current_data['main']['temp']
                current_feels_like = current_data['main']['feels_like']
                current_humidity = current_data['main']['humidity']
                current_weather = current_data['weather'][0]['description']
                
                # 找出未來 12 小時內最高和最低溫度
                next_12h = forecast_data['list'][:4]  # 每 3 小時一筆，取 4 筆約等於 12 小時
                temps = [item['main']['temp'] for item in next_12h]
                max_temp = max(temps)
                min_temp = min(temps)
                
                # 計算降雨機率
                rain_probs = [item.get('pop', 0) * 100 for item in next_12h]
                max_rain_prob = max(rain_probs)
                
                # 組合天氣訊息
                weather_msg = f"📍 {city}天氣預報\n\n"
                weather_msg += f"目前天氣：{current_weather}\n"
                weather_msg += f"現在溫度：{current_temp:.1f}°C\n"
                weather_msg += f"體感溫度：{current_feels_like:.1f}°C\n"
                weather_msg += f"相對濕度：{current_humidity}%\n"
                weather_msg += f"12小時內最高溫：{max_temp:.1f}°C\n"
                weather_msg += f"12小時內最低溫：{min_temp:.1f}°C\n"
                
                if max_rain_prob > 0:
                    weather_msg += f"降雨機率：{max_rain_prob:.0f}%\n"
                    
                # 添加天氣建議
                if max_rain_prob > 50:
                    weather_msg += "\n☔ 提醒：可能會下雨，記得帶傘！"
                elif current_temp > 30:
                    weather_msg += "\n☀️ 提醒：天氣炎熱，記得防曬補水！"
                elif current_temp < 15:
                    weather_msg += "\n🧥 提醒：天氣較涼，記得添加衣物！"
                
                return weather_msg
                
            return "抱歉，無法獲取天氣資訊"
            
        except Exception as e:
            print(f"獲取天氣時發生錯誤：{str(e)}")
            return "抱歉，獲取天氣資訊時發生錯誤"

    def get_air_quality(self, city="台北市"):
        """獲取空氣品質資訊"""
        try:
            # 先獲取城市座標
            coords = self._get_coordinates(city)
            if not coords:
                return f"抱歉，找不到 {city} 的位置資訊"
                
            lat, lon = coords
            
            # 獲取空氣品質資料
            params = {
                'lat': lat,
                'lon': lon,
                'appid': self.api_key
            }
            
            response = requests.get(self.aqi_url, params=params)
            if response.status_code == 200:
                data = response.json()
                
                # 解析空氣品質資料
                aqi = data['list'][0]['main']['aqi']
                components = data['list'][0]['components']
                
                # AQI 等級說明
                aqi_levels = {
                    1: ("優良 😊", "適合戶外活動"),
                    2: ("普通 😐", "敏感族群應注意"),
                    3: ("對敏感族群不健康 😷", "建議戴口罩"),
                    4: ("不健康 🚫", "建議減少戶外活動"),
                    5: ("非常不健康 ⚠️", "盡量待在室內")
                }
                
                aqi_status, aqi_advice = aqi_levels.get(aqi, ("未知", ""))
                
                # 組合空氣品質訊息
                air_msg = f"📍 {city}空氣品質\n\n"
                air_msg += f"空氣品質指數(AQI)：{aqi_status}\n"
                air_msg += f"PM2.5：{components['pm2_5']:.1f} μg/m³\n"
                air_msg += f"PM10：{components['pm10']:.1f} μg/m³\n"
                air_msg += f"臭氧(O₃)：{components['o3']:.1f} μg/m³\n"
                air_msg += f"二氧化氮(NO₂)：{components['no2']:.1f} μg/m³\n"
                air_msg += f"\n💡 建議：{aqi_advice}"
                
                return air_msg
                
            return "抱歉，無法獲取空氣品質資訊"
            
        except Exception as e:
            print(f"獲取空氣品質時發生錯誤：{str(e)}")
            return "抱歉，獲取空氣品質資訊時發生錯誤"

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
        weather_msg = weather_service.get_weather()
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
