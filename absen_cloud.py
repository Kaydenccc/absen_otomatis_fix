import requests
import sqlite3
import random
import math
import time
import logging
from datetime import datetime, time as dt_time
import pytz
import os

class AbsenCloud:
    def __init__(self):
        # ========== KONFIGURASI ==========
        self.NIP = "199909262025051003"
        self.LAT_KANTOR = -3.2795460218952925
        self.LON_KANTOR = 119.85262806281504
        self.RADIUS_METER = 20
        self.ENDPOINT = "https://sielka.kemenagtanatoraja.id/tambahabsentes.php"
        
        # Telegram Bot - Isi dengan data Anda
        self.TELEGRAM_TOKEN = "YOUR_TELEGRAM_TOKEN"
        self.TELEGRAM_CHAT_ID = "YOUR_CHAT_ID"
        
        # Timezone
        self.TIMEZONE = "Asia/Makassar"
        self.wita = pytz.timezone(self.TIMEZONE)
        
        # Setup logging
        self.setup_logging()
        self.init_database()
    
    def setup_logging(self):
        """Setup logging untuk cloud"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('absen_cloud.log'),
                logging.StreamHandler()
            ]
        )
    
    def init_database(self):
        """Initialize SQLite database di cloud"""
        self.conn = sqlite3.connect('absen_cloud.db', check_same_thread=False)
        self.cursor = self.conn.cursor()
        
        # Create tables
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS absen_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tanggal TEXT NOT NULL,
                jenis TEXT NOT NULL,
                koordinat_lat REAL NOT NULL,
                koordinat_lon REAL NOT NULL,
                jarak_meter REAL NOT NULL,
                waktu TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(tanggal, jenis)
            )
        ''')
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS koordinat_harian (
                tanggal TEXT PRIMARY KEY,
                lat REAL NOT NULL,
                lon REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        self.conn.commit()
        logging.info("✅ Database initialized")
    
    def generate_random_coordinate(self):
        """Generate random coordinate within 20m radius"""
        radius_deg = self.RADIUS_METER / 111111.0
        r = radius_deg * math.sqrt(random.random())
        theta = random.random() * 2 * math.pi
        
        delta_lat = r * math.cos(theta)
        delta_lon = r * math.sin(theta) / math.cos(math.radians(self.LAT_KANTOR))
        
        new_lat = self.LAT_KANTOR + delta_lat
        new_lon = self.LON_KANTOR + delta_lon
        
        return round(new_lat, 7), round(new_lon, 7)
    
    def get_daily_coordinate(self):
        """Get or create today's coordinate"""
        today = datetime.now(self.wita).strftime('%Y-%m-%d')
        
        self.cursor.execute(
            "SELECT lat, lon FROM koordinat_harian WHERE tanggal = ?", 
            (today,)
        )
        result = self.cursor.fetchone()
        
        if result:
            return result[0], result[1]
        else:
            # Generate new coordinate
            lat, lon = self.generate_random_coordinate()
            self.cursor.execute(
                "INSERT INTO koordinat_harian (tanggal, lat, lon) VALUES (?, ?, ?)",
                (today, lat, lon)
            )
            self.conn.commit()
            
            # Send notification
            distance = self.calculate_distance(self.LAT_KANTOR, self.LON_KANTOR, lat, lon)
            self.send_telegram(
                f"📍 <b>KOORDINAT HARIAN DIBUAT</b>\n"
                f"📅 {today}\n"
                f"🎯 {lat}, {lon}\n"
                f"📏 {distance:.1f} meter dari kantor"
            )
            
            logging.info(f"Generated coordinate: {lat}, {lon}")
            return lat, lon
    
    def calculate_distance(self, lat1, lon1, lat2, lon2):
        """Calculate distance between coordinates"""
        from math import radians, sin, cos, sqrt, atan2
        R = 6371000
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        return R * c
    
    def check_already_absent(self, jenis):
        """Check if already absent today"""
        today = datetime.now(self.wita).strftime('%Y-%m-%d')
        self.cursor.execute(
            "SELECT 1 FROM absen_log WHERE tanggal = ? AND jenis = ?",
            (today, jenis)
        )
        return self.cursor.fetchone() is not None
    
    def send_telegram(self, message):
        """Send notification to Telegram"""
        try:
            url = f"https://api.telegram.org/bot{self.TELEGRAM_TOKEN}/sendMessage"
            payload = {
                'chat_id': self.TELEGRAM_CHAT_ID,
                'text': message,
                'parse_mode': 'HTML'
            }
            response = requests.post(url, json=payload, timeout=10)
            return response.status_code == 200
        except Exception as e:
            logging.error(f"Failed to send Telegram: {e}")
            return False
    
    def send_absen(self, jenis):
        """Send attendance request"""
        now = datetime.now(self.wita)
        today = now.strftime('%Y-%m-%d')
        current_time = now.strftime('%H:%M:%S')
        
        # Check if already absent
        if self.check_already_absent(jenis):
            logging.info(f"Already {jenis} today")
            return False, "Sudah absen hari ini"
        
        # Get today's coordinate
        lat, lon = self.get_daily_coordinate()
        lokasi = f"{lat},{lon}"
        
        # Add random delay
        delay = random.randint(0, 600)
        time.sleep(delay)
        
        # Send request
        try:
            data = {
                'nip': self.NIP,
                'lokasi': lokasi
            }
            
            response = requests.post(
                self.ENDPOINT,
                data=data,
                timeout=30,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
            )
            
            response_text = response.text.strip()
            status = "SUCCESS" if response.status_code == 200 and "berhasil" in response_text.lower() else "FAILED"
            
            # Save to database
            distance = self.calculate_distance(self.LAT_KANTOR, self.LON_KANTOR, lat, lon)
            self.cursor.execute('''
                INSERT INTO absen_log 
                (tanggal, jenis, koordinat_lat, koordinat_lon, jarak_meter, waktu, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (today, jenis, lat, lon, distance, current_time, status))
            self.conn.commit()
            
            # Send notification
            if status == "SUCCESS":
                message = (
                    f"✅ <b>ABSEN {jenis.upper()} BERHASIL</b>\n"
                    f"📅 {today} {current_time} WITA\n"
                    f"📍 {lokasi}\n"
                    f"📏 {distance:.1f} meter dari kantor"
                )
            else:
                message = (
                    f"❌ <b>ABSEN {jenis.upper()} GAGAL</b>\n"
                    f"📅 {today} {current_time}\n"
                    f"📍 {lokasi}\n"
                    f"📝 {response_text}"
                )
            
            self.send_telegram(message)
            logging.info(f"Absen {jenis}: {status}")
            return status == "SUCCESS", response_text
            
        except Exception as e:
            logging.error(f"Error sending absen: {e}")
            self.send_telegram(f"🚨 ERROR: {str(e)}")
            return False, str(e)
    
    def check_schedule(self):
        """Check if current time is within schedule"""
        now = datetime.now(self.wita)
        weekday = now.weekday()  # 0=Monday, 4=Friday
        current_time = now.time()
        
        # Check masuk (Mon-Fri, 06:10-07:20)
        if dt_time(6, 10) <= current_time <= dt_time(7, 20) and weekday <= 4:
            return "masuk"
        
        # Check pulang
        if weekday <= 3:  # Mon-Thu
            if dt_time(16, 0) <= current_time <= dt_time(17, 0):
                return "pulang"
        elif weekday == 4:  # Friday
            if dt_time(16, 30) <= current_time <= dt_time(17, 10):
                return "pulang"
        
        return None
    
    def run(self):
        """Main execution"""
        jenis = self.check_schedule()
        
        if jenis:
            logging.info(f"Running absen {jenis}...")
            success, message = self.send_absen(jenis)
            return f"Absen {jenis}: {'Success' if success else 'Failed'} - {message}"
        else:
            msg = f"Not in schedule: {datetime.now(self.wita).strftime('%H:%M:%S')}"
            logging.info(msg)
            return msg
    
    def close(self):
        """Close connections"""
        self.conn.close()

def main():
    """Main function untuk cloud"""
    system = AbsenCloud()
    try:
        result = system.run()
        print(result)
    except Exception as e:
        print(f"Error: {e}")
        system.send_telegram(f"🚨 CRITICAL ERROR: {str(e)}")
    finally:
        system.close()

if __name__ == "__main__":
    main()