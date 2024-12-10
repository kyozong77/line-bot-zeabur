import googlemaps
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

class ParkingService:
    def __init__(self):
        self.gmaps = googlemaps.Client(key=os.getenv('GOOGLE_MAPS_API_KEY'))
    
    def search_parking(self, location, radius=1000):
        """搜尋停車場
        Args:
            location: 位置（可以是地址字串或經緯度）
            radius: 搜尋半徑（公尺）
        """
        try:
            # 如果輸入的是地址，先轉換成經緯度
            if isinstance(location, str):
                geocode_result = self.gmaps.geocode(location)
                if not geocode_result:
                    return "找不到指定的位置"
                location = geocode_result[0]['geometry']['location']
            
            # 搜尋停車場
            places_result = self.gmaps.places_nearby(
                location=location,
                radius=radius,
                type='parking',
                language='zh-TW'
            )
            
            if not places_result.get('results'):
                return "在指定範圍內找不到停車場"
            
            # 取得詳細資訊
            parking_lots = []
            for place in places_result['results'][:5]:  # 取前5個結果
                try:
                    # 獲取更詳細的場所資訊
                    place_details = self.gmaps.place(
                        place['place_id'],
                        fields=['name', 'formatted_address', 'rating', 'opening_hours', 'formatted_phone_number'],
                        language='zh-TW'
                    )['result']
                    
                    parking_info = {
                        'name': place_details.get('name', '未知名稱'),
                        'address': place_details.get('formatted_address', '地址未提供'),
                        'rating': place_details.get('rating', '無評分'),
                        'phone': place_details.get('formatted_phone_number', '無電話資訊'),
                        'is_open': '營業中' if place_details.get('opening_hours', {}).get('open_now', False) else '已關閉'
                    }
                    
                    # 計算距離
                    distance_result = self.gmaps.distance_matrix(
                        location,
                        f"{place['geometry']['location']['lat']},{place['geometry']['location']['lng']}",
                        mode="driving",
                        language="zh-TW"
                    )
                    
                    if distance_result['rows'][0]['elements'][0]['status'] == 'OK':
                        parking_info['distance'] = distance_result['rows'][0]['elements'][0]['distance']['text']
                        parking_info['duration'] = distance_result['rows'][0]['elements'][0]['duration']['text']
                    
                    parking_lots.append(parking_info)
                    
                except Exception as e:
                    print(f"Error getting details for parking lot: {str(e)}")
                    continue
            
            # 格式化輸出
            if not parking_lots:
                return "無法獲取停車場詳細資訊"
            
            message = "📍 附近的停車場：\n\n"
            for i, lot in enumerate(parking_lots, 1):
                message += f"{i}. {lot['name']}\n"
                message += f"   距離：{lot.get('distance', '未知')}\n"
                message += f"   預計行車時間：{lot.get('duration', '未知')}\n"
                message += f"   地址：{lot['address']}\n"
                message += f"   電話：{lot['phone']}\n"
                message += f"   評分：{lot['rating']}⭐\n"
                message += f"   狀態：{lot['is_open']}\n\n"
            
            return message
            
        except Exception as e:
            return f"搜尋停車場時發生錯誤：{str(e)}"
    
    def get_parking_directions(self, origin, destination):
        """獲取到停車場的導航資訊"""
        try:
            # 獲取導航路線
            directions_result = self.gmaps.directions(
                origin,
                destination,
                mode="driving",
                language="zh-TW"
            )
            
            if not directions_result:
                return "無法獲取導航資訊"
            
            # 提取路線資訊
            route = directions_result[0]
            legs = route['legs'][0]
            
            # 格式化導航資訊
            message = "🚗 導航資訊：\n\n"
            message += f"總距離：{legs['distance']['text']}\n"
            message += f"預計時間：{legs['duration']['text']}\n\n"
            message += "路線指引：\n"
            
            # 添加詳細步驟
            for i, step in enumerate(legs['steps'], 1):
                message += f"{i}. {step['html_instructions']}\n"
                message += f"   ({step['distance']['text']})\n"
            
            return message
            
        except Exception as e:
            return f"獲取導航資訊時發生錯誤：{str(e)}"
