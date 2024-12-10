import os
import json
from datetime import datetime
import dropbox
import requests
from pathlib import Path

class AlbumBackupService:
    def __init__(self, dropbox_client):
        self.dbx = dropbox_client
        self.backup_base_path = '/LineGroupAlbums'  # Dropbox 中的基礎路徑
        self.temp_dir = 'temp_downloads'  # 臨時下載目錄
        self.albums_record_file = 'albums_record.json'  # 用於記錄相簿資訊
        self.setup()

    def setup(self):
        """初始化設定"""
        # 確保臨時目錄存在
        if not os.path.exists(self.temp_dir):
            os.makedirs(self.temp_dir)
        
        # 載入相簿記錄
        self.albums_record = self.load_albums_record()

    def load_albums_record(self):
        """載入相簿記錄"""
        try:
            try:
                # 從 Dropbox 下載記錄檔
                self.dbx.files_download_to_file(
                    os.path.join(self.temp_dir, self.albums_record_file),
                    f"{self.backup_base_path}/{self.albums_record_file}"
                )
            except dropbox.exceptions.ApiError:
                # 如果檔案不存在，返回空字典
                return {}

            with open(os.path.join(self.temp_dir, self.albums_record_file), 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"載入相簿記錄時發生錯誤：{str(e)}")
            return {}

    def save_albums_record(self):
        """儲存相簿記錄"""
        try:
            # 將記錄寫入臨時檔案
            with open(os.path.join(self.temp_dir, self.albums_record_file), 'w', encoding='utf-8') as f:
                json.dump(self.albums_record, f, ensure_ascii=False, indent=2)

            # 上傳到 Dropbox
            with open(os.path.join(self.temp_dir, self.albums_record_file), 'rb') as f:
                self.dbx.files_upload(
                    f.read(),
                    f"{self.backup_base_path}/{self.albums_record_file}",
                    mode=dropbox.files.WriteMode.overwrite
                )
        except Exception as e:
            print(f"儲存相簿記錄時發生錯誤：{str(e)}")

    def ensure_folder_exists(self, path):
        """確保 Dropbox 中的資料夾存在"""
        try:
            self.dbx.files_get_metadata(path)
        except dropbox.exceptions.ApiError as e:
            if isinstance(e.error, dropbox.files.GetMetadataError) and e.error.is_path():
                # 資料夾不存在，創建它
                self.dbx.files_create_folder_v2(path)

    def backup_album(self, group_id, album_id, album_name, image_url):
        """備份相簿中的圖片"""
        try:
            # 建立群組和相簿的路徑
            group_path = f"{self.backup_base_path}/{group_id}"
            album_path = f"{group_path}/{album_name}"

            # 確保資料夾存在
            self.ensure_folder_exists(self.backup_base_path)
            self.ensure_folder_exists(group_path)
            self.ensure_folder_exists(album_path)

            # 檢查是否已經備份過這張圖片
            image_filename = os.path.basename(image_url)
            if self.is_image_backed_up(group_id, album_id, image_filename):
                return "圖片已經備份過了"

            # 下載圖片到臨時目錄
            temp_path = os.path.join(self.temp_dir, image_filename)
            response = requests.get(image_url)
            if response.status_code != 200:
                return "下載圖片失敗"

            with open(temp_path, 'wb') as f:
                f.write(response.content)

            # 上傳到 Dropbox
            with open(temp_path, 'rb') as f:
                upload_path = f"{album_path}/{image_filename}"
                self.dbx.files_upload(
                    f.read(),
                    upload_path,
                    mode=dropbox.files.WriteMode.add
                )

            # 更新記錄
            if group_id not in self.albums_record:
                self.albums_record[group_id] = {}
            if album_id not in self.albums_record[group_id]:
                self.albums_record[group_id][album_id] = {
                    'name': album_name,
                    'images': [],
                    'created_at': datetime.now().isoformat()
                }
            
            self.albums_record[group_id][album_id]['images'].append({
                'filename': image_filename,
                'original_url': image_url,
                'backup_path': upload_path,
                'backed_up_at': datetime.now().isoformat()
            })

            # 儲存記錄
            self.save_albums_record()

            # 清理臨時檔案
            os.remove(temp_path)

            return "備份成功"

        except Exception as e:
            return f"備份失敗：{str(e)}"

    def is_image_backed_up(self, group_id, album_id, image_filename):
        """檢查圖片是否已經備份過"""
        if group_id not in self.albums_record:
            return False
        if album_id not in self.albums_record[group_id]:
            return False
        
        return any(
            image['filename'] == image_filename
            for image in self.albums_record[group_id][album_id]['images']
        )

    def get_album_status(self, group_id, album_id=None):
        """獲取相簿備份狀態"""
        if group_id not in self.albums_record:
            return "此群組尚未有備份的相簿"

        if album_id:
            # 查詢特定相簿
            if album_id not in self.albums_record[group_id]:
                return "找不到此相簿的備份記錄"
            
            album = self.albums_record[group_id][album_id]
            return (
                f"相簿名稱：{album['name']}\n"
                f"建立時間：{album['created_at']}\n"
                f"已備份圖片數：{len(album['images'])}"
            )
        else:
            # 列出所有相簿
            message = "群組相簿備份狀態：\n\n"
            for album_id, album in self.albums_record[group_id].items():
                message += (
                    f"📁 {album['name']}\n"
                    f"建立時間：{album['created_at']}\n"
                    f"已備份圖片數：{len(album['images'])}\n\n"
                )
            return message

    def get_backup_link(self, group_id, album_id):
        """獲取相簿的 Dropbox 共享連結"""
        try:
            if group_id not in self.albums_record or album_id not in self.albums_record[group_id]:
                return "找不到此相簿的備份"

            album = self.albums_record[group_id][album_id]
            album_path = f"{self.backup_base_path}/{group_id}/{album['name']}"

            # 創建共享連結
            shared_link = self.dbx.sharing_create_shared_link(album_path)
            return f"相簿 {album['name']} 的備份連結：\n{shared_link.url}"

        except Exception as e:
            return f"獲取備份連結失敗：{str(e)}"
