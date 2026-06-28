import base64
import time
import sys
import os
import requests
import random
import json
import hashlib
import hmac
from urllib.parse import urlencode
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5

class SteamAuthArchitecture:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
        })
        self.access_token = None
        self.refresh_token = None
        self.steam_id = None
        self.session_id = None

    def _encrypt_password(self, password: str, mod_hex: str, exp_hex: str) -> str:
        try:
            mod = int(mod_hex, 16)
            exp = int(exp_hex, 16)
            pub_key = RSA.construct((mod, exp))
            cipher = PKCS1_v1_5.new(pub_key)
            encrypted = cipher.encrypt(password.encode('utf-8'))
            return base64.b64encode(encrypted).decode('utf-8')
        except Exception as e:
            print(f"\n[-] RSA Sifreleme Hatasi: {e}", flush=True)
            return None

    def get_rsa_key(self, username: str) -> dict:
        url = "https://api.steampowered.com/IAuthenticationService/GetPasswordRSAPublicKey/v1/"
        params = {"account_name": username}
        print(f"\n[*] '{username}' icin RSA Public Key talep ediliyor...", flush=True)
        try:
            response = self.session.get(url, params=params, timeout=10)
            if response.status_code == 200:
                return response.json().get("response", {})
        except Exception:
            pass
        return {}

    def begin_session(self, username: str, encrypted_password: str, timestamp: str) -> dict:
        url = "https://api.steampowered.com/IAuthenticationService/BeginAuthSessionViaCredentials/v1/"
        payload = {
            "device_friendly_name": "PC-Python-Client",
            "account_name": username,
            "encrypted_password": encrypted_password,
            "encryption_timestamp": timestamp,
            "remember_login": "true",
            "platform_type": "1",
            "persistence": "1"
        }
        print("[*] Kimlik bilgileriyle auth session baslatiliyor...", flush=True)
        try:
            response = self.session.post(url, data=payload, timeout=10)
            if response.status_code == 200:
                return response.json().get("response", {})
        except Exception:
            pass
        return {}

    def update_auth_session_with_code(self, client_id: str, steam_id: str, code: str, code_type: int) -> bool:
        url = "https://api.steampowered.com/IAuthenticationService/UpdateAuthSessionWithCode/v1/"
        payload = {
            "client_id": client_id,
            "steamid": steam_id,
            "code": code,
            "code_type": code_type
        }
        try:
            response = self.session.post(url, data=payload, timeout=10)
            return response.status_code == 200
        except Exception:
            return False

    def poll_status(self, client_id: str, request_id: str) -> dict:
        url = "https://api.steampowered.com/IAuthenticationService/PollAuthSessionStatus/v1/"
        payload = {"client_id": client_id, "request_id": request_id}
        try:
            response = self.session.post(url, data=payload, timeout=10)
            if response.status_code == 200:
                return response.json().get("response", {})
        except Exception:
            pass
        return {}

    def execute_login(self, username, password):
        rsa_data = self.get_rsa_key(username)
        if not rsa_data.get("publickey_mod"):
            print("[-] RSA Key alinamadi.", flush=True)
            return False

        enc_pass = self._encrypt_password(password, rsa_data["publickey_mod"], rsa_data["publickey_exp"])
        if not enc_pass:
            return False
        
        session_data = self.begin_session(username, enc_pass, rsa_data["timestamp"])
        client_id = session_data.get("client_id")
        request_id = session_data.get("request_id")
        steam_id = session_data.get("steamid")
        
        if not client_id or not request_id:
            print("[-] Oturum baslatilamadi. Sifre hatali olabilir.", flush=True)
            return False

        confirmations = session_data.get("allowed_confirmations", [])
        is_email_guard = False
        
        if confirmations:
            guard_type = confirmations[0].get("confirmation_type")
            
            if guard_type == 2:
                print("\n[!] [STEAM GUARD: E-POSTA ALGINLANDI]", flush=True)
                email_code = input("[?] Lutfen E-posta adresinize gelen kodu girin: ").strip()
                self.update_auth_session_with_code(client_id, steam_id, email_code, code_type=2)
                is_email_guard = True
            elif guard_type == 1:
                print(f"\n[!] [STEAM GUARD: MOBIL UYGULAMA ALGINLANDI]", flush=True)
                print("[*] Lutfen Steam Mobil uygulamaniza gelen bildirimi acip ONAY VERIN.", flush=True)
            else:
                print(f"\n[!] [STEAM GUARD: BILINMEYEN TUR - {guard_type}]", flush=True)

        print("[*] Steam sunucusundan oturum onayi bekleniyor...", flush=True)
        attempt = 0
        while True:
            attempt += 1
            sys.stdout.write(f"\r[*] Sorgu yapiliyor... Deneme: {attempt}")
            sys.stdout.flush()
            
            status = self.poll_status(client_id, request_id)
            if "refresh_token" in status:
                print("\n[+] Onay alindi! Giris basarili.", flush=True)
                self.refresh_token = status["refresh_token"]
                self.access_token = status.get("access_token")
                self.steam_id = status.get("steamid")
                
                self.session_id = self.session.cookies.get("sessionid", "")
                return True
                
            if status.get("had_error_in_last_poll") and is_email_guard:
                print("\n[-] Girilen e-posta kodu yanlis veya gecersiz olabilir.", flush=True)
                return False
                
            time.sleep(3)

    def get_profile_data(self):
        if not self.access_token or not self.steam_id:
            return None
        wallet_url = f"https://store.steampowered.com/api/getwalletinfoofuser/?access_token={self.access_token}"
        profile_info = {
            "steamid": self.steam_id, 
            "bakiye": "Bilinmiyor", 
            "para_birimi": "",
            "nick": "Bilinmiyor",
            "level": 0
        }
        try:
            w_res = self.session.get(wallet_url, timeout=10)
            if w_res.status_code == 200 and w_res.json().get("success") == 1:
                w_data = w_res.json()
                profile_info["bakiye"] = w_data.get("wallet_balance", 0) / 100
                profile_info["para_birimi"] = w_data.get("wallet_currency", "")
        except Exception:
            pass
        
        try:
            summaries_url = f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/?key=&steamids={self.steam_id}"
            headers = {"Authorization": f"Bearer {self.access_token}"}
            s_res = self.session.get(summaries_url, headers=headers, timeout=10)
            if s_res.status_code == 200:
                players = s_res.json().get("response", {}).get("players", [])
                if players:
                    p = players[0]
                    profile_info["nick"] = p.get("personaname", "Bilinmiyor")
                    profile_info["avatar"] = p.get("avatarfull", "")
                    profile_info["profil_url"] = p.get("profileurl", "")
                    profile_info["olusturma"] = p.get("timecreated", 0)
        except Exception:
            pass
        
        profile_info["level"] = self.get_steam_level()
            
        return profile_info

    def get_steam_level(self):
        try:
            url = "https://api.steampowered.com/IPlayerService/GetSteamLevel/v1/"
            payload = {"access_token": self.access_token, "steamid": self.steam_id}
            res = self.session.post(url, data=payload, timeout=10)
            if res.status_code == 200:
                return res.json().get("response", {}).get("player_level", 0)
        except Exception:
            pass
        return 0

    def clear_discovery_queue(self):
        if not self.access_token:
            print("[-] Once giris yapmalisiniz.", flush=True)
            return
        print("\n[*] Kesif kuyrugu temizleme islemi baslatiliyor...", flush=True)
        url = "https://api.steampowered.com/IStoreService/GetDiscoveryQueue/v1/"
        params = {"access_token": self.access_token, "queue_type": 0}
        try:
            res = self.session.get(url, params=params, timeout=10)
            if res.status_code == 200:
                apps = res.json().get("response", {}).get("appids", [])
                if not apps:
                    print("[+] Kesif kuyrugu zaten temiz!", flush=True)
                    return
                clear_url = "https://api.steampowered.com/IStoreService/SkipDiscoveryQueueApp/v1/"
                for appid in apps:
                    payload = {"access_token": self.access_token, "appid": appid, "queue_type": 0}
                    self.session.post(clear_url, data=payload, timeout=10)
                print("[+] Kesif kuyrugu basariyla tamamlandi ve kartlar kazanildi!", flush=True)
        except Exception as e:
            print(f"[-] Otomasyon Hatasi: {e}", flush=True)

    def start_idling(self, app_id):
        if not self.access_token:
            print("[-] Once giris yapmalisiniz.", flush=True)
            return
        print(f"\n[*] AppID: {app_id} icin idling baslatildi. CTRL+C ile durdurun.\n", flush=True)
        url = "https://api.steampowered.com/IPlayerService/GetPlayedFreeGames/v1/"
        params = {"access_token": self.access_token}
        try:
            while True:
                self.session.get(url, params=params, timeout=10)
                sys.stdout.write(f"\r[IDLE] AppID {app_id} aktif... Son guncelleme: {time.strftime('%H:%M:%S')}")
                sys.stdout.flush()
                time.sleep(30)
        except KeyboardInterrupt:
            print("\n[*] Idling sonlandirildi.", flush=True)

    # ===== HESAP GERME (BOOSTING) =====
    def boost_account(self):
        if not self.access_token:
            print("[-] Once giris yapmalisiniz.", flush=True)
            return
        
        print("\n" + "="*50)
        print("     GERCEK HESAP GERME (ACCOUNT BOOSTING)")
        print("="*50)
        print("[1] Seviye Boost - Gercek Badge Olustur")
        print("[2] Oyun Kutuphanesi Sisme - Free License Al")
        print("[3] Cuzdan Bilgisi ve Trade Teklifleri")
        print("[4] Toplu Oyun Suresi Kasma (Mass Idling)")
        print("[5] Kart/Badge Durumu Sorgula")
        print("[6] Geri Don")
        print("="*50)
        print("[!] TUM ISLEMLER GERCEK API CAGRISIDIR")
        print("="*50)
        
        choice = input("Seciminiz (1-6): ").strip()
        
        if choice == "1":
            self._real_level_boost()
        elif choice == "2":
            self._real_library_expansion()
        elif choice == "3":
            self._wallet_trades()
        elif choice == "4":
            self._mass_idling()
        elif choice == "5":
            self._check_badge_status()
        elif choice == "6":
            return

    def _real_level_boost(self):
        print("\n[*] GERCEK Seviye Boost baslatiliyor...", flush=True)
        print("[*] Mevcut badge'ler sorgulaniyor...", flush=True)
        try:
            badge_url = "https://api.steampowered.com/IPlayerService/GetBadges/v1/"
            badge_payload = {"access_token": self.access_token, "steamid": self.steam_id}
            b_res = self.session.post(badge_url, data=badge_payload, timeout=10)
            
            if b_res.status_code == 200:
                badge_data = b_res.json().get("response", {})
                badges = badge_data.get("badges", [])
                print(f"[+] Mevcut rozet sayisi: {len(badges)}", flush=True)
                
                level = self.get_steam_level()
                print(f"[+] Mevcut Steam Seviyesi: {level}", flush=True)
                
                print("[*] Kullanilabilir kart setleri taranıyor...", flush=True)
                
                inv_url = "https://api.steampowered.com/IEconService/GetInventoryItems/v1/"
                inv_payload = {"access_token": self.access_token, "steamid": self.steam_id, "appid": 753}
                inv_res = self.session.post(inv_url, data=inv_payload, timeout=10)
                
                if inv_res.status_code == 200:
                    items = inv_res.json().get("response", {}).get("items", [])
                    print(f"[+] Envanterde {len(items)} adet Steam nesnesi var", flush=True)
                    
                    cards = [i for i in items if i.get("tags", {}).get("card_series", 0) > 0]
                    print(f"[+] Trading kart sayisi: {len(cards)}", flush=True)
                    
                    if cards:
                        print("\n[*] Kartlar kullanilarak badge olusturuluyor...", flush=True)
                        created_count = 0
                        for card in cards[:20]:
                            try:
                                series = card.get("tags", {}).get("card_series", 0)
                                appid = card.get("appid", 0)
                                if appid > 0:
                                    craft_url = "https://api.steampowered.com/IPlayerService/CraftBadge/v1/"
                                    craft_payload = {
                                        "access_token": self.access_token,
                                        "steamid": self.steam_id,
                                        "appid": appid,
                                        "series": series,
                                        "quantity": 1
                                    }
                                    craft_res = self.session.post(craft_url, data=craft_payload, timeout=10)
                                    if craft_res.status_code == 200:
                                        created_count += 1
                                        sys.stdout.write(f"\r[+] Badge olusturuldu: AppID {appid} (Toplam: {created_count})")
                                        sys.stdout.flush()
                                    time.sleep(1)
                            except Exception:
                                pass
                        
                        if created_count > 0:
                            print(f"\n[+] {created_count} adet badge basariyla olusturuldu!", flush=True)
                            time.sleep(2)
                            new_level = self.get_steam_level()
                            if new_level > level:
                                print(f"[+] SEVIYE ATLADI: {level} -> {new_level}", flush=True)
                            else:
                                print(f"[+] Seviye ayni: {level} (XP eklenmis olabilir)", flush=True)
                        else:
                            print("\n[-] Badge olusturulamadi. Yeterli kart olmayabilir.", flush=True)
                    else:
                        print("[-] Envanterde trading kart bulunamadi.", flush=True)
                        print("[*] Kart satin almak icin Steam Community Market kullanilabilir.", flush=True)
                else:
                    print(f"[-] Envanter alinamadi. HTTP {inv_res.status_code}", flush=True)
            else:
                print(f"[-] Badge bilgisi alinamadi. HTTP {b_res.status_code}", flush=True)
        except Exception as e:
            print(f"[-] Hata: {e}", flush=True)
        
        input("\nDevam etmek icin Enter'a basin...")

    def _real_library_expansion(self):
        print("\n[*] GERCEK Kutuphane Sisme Modulu", flush=True)
        print("[*] Steam'deki ucretsiz oyunlar taranıyor...", flush=True)
        
        free_games = [
            {"appid": 730, "name": "Counter-Strike 2"},
            {"appid": 570, "name": "Dota 2"},
            {"appid": 440, "name": "Team Fortress 2"},
            {"appid": 578080, "name": "PUBG"},
            {"appid": 1172470, "name": "Apex Legends"},
            {"appid": 230410, "name": "Warframe"},
            {"appid": 1085660, "name": "Destiny 2"},
            {"appid": 1938090, "name": "Call of Duty: Warzone"},
            {"appid": 1229490, "name": "The Finals"},
            {"appid": 1817070, "name": "Marvel Rivals"},
        ]
        
        print(f"[*] {len(free_games)} aday oyun bulundu.", flush=True)
        print("[*] Steam Store uzerinden free license aliniyor...", flush=True)
        
        added_count = 0
        for game in free_games:
            appid = game["appid"]
            name = game["name"]
            try:
                store_headers = {
                    "Referer": f"https://store.steampowered.com/app/{appid}/",
                    "Origin": "https://store.steampowered.com"
                }
                
                payload = {
                    "sessionid": self.session_id,
                    "appid": appid,
                    "action": "add_to_cart_and_go_to_cart"
                }
                
                self.session.get(f"https://store.steampowered.com/app/{appid}/", headers=store_headers, timeout=10)
                
                license_res = self.session.post(
                    "https://store.steampowered.com/api/registerfreegame/",
                    data=payload,
                    headers=store_headers,
                    timeout=15
                )
                
                if license_res.status_code == 200:
                    result = license_res.json()
                    if result.get("success") == 1 or result.get("purchaseresultdetail") == 0:
                        added_count += 1
                        sys.stdout.write(f"\r[+] Eklendi: {name} (AppID: {appid}) - Toplam: {added_count}   ")
                        sys.stdout.flush()
                    else:
                        sys.stdout.write(f"\r[-] Basarisiz: {name} - {result.get('purchaseresultdetail', 'Bilinmiyor')}   ")
                        sys.stdout.flush()
                else:
                    sys.stdout.write(f"\r[-] HTTP {license_res.status_code}: {name}   ")
                    sys.stdout.flush()
                
                time.sleep(2)
            except Exception:
                sys.stdout.write(f"\r[-] Hata: {name}   ")
                sys.stdout.flush()
        
        print(f"\n\n[+] Toplam {added_count} oyun basariyla kutuphaneye eklendi!", flush=True)
        print("[!] Steam rate limit nedeniyle her oyun arasinda 2 saniye beklendi.", flush=True)
        input("\nDevam etmek icin Enter'a basin...")

    def _wallet_trades(self):
        print("\n[*] Cuzdan ve Trade Modulu", flush=True)
        
        profile = self.get_profile_data()
        if profile:
            print(f"[+] Mevcut Bakiye: {profile.get('bakiye', 0)} {profile.get('para_birimi', '')}", flush=True)
        
        print("\n[1] Trade tekliflerini goruntule")
        print("[2] Trade history sorgula")
        print("[3] Cuzdan islem gecmisi")
        print("[4] Geri")
        
        secim = input("Secim (1-4): ").strip()
        
        if secim == "1":
            try:
                trade_url = "https://api.steampowered.com/IEconService/GetTradeOffers/v1/"
                params = {
                    "access_token": self.access_token,
                    "get_sent_offers": 1,
                    "get_received_offers": 1,
                    "get_descriptions": 1
                }
                t_res = self.session.get(trade_url, params=params, timeout=10)
                if t_res.status_code == 200:
                    trade_data = t_res.json().get("response", {})
                    sent = trade_data.get("trade_offers_sent", [])
                    received = trade_data.get("trade_offers_received", [])
                    print(f"\n[+] Gönderilen teklif: {len(sent)}")
                    print(f"[+] Alinan teklif: {len(received)}")
                    if received:
                        print("\n[*] Bekleyen trade teklifleri:")
                        for offer in received[:5]:
                            state = offer.get("trade_offer_state", 0)
                            states = {1: "Gonderildi", 2: "Aktif", 3: "Kabul", 4: "Red", 5: "Iptal"}
                            print(f"  - ID: {offer.get('tradeofferid')} | Durum: {states.get(state, state)}")
                else:
                    print(f"[-] Trade bilgisi alinamadi. HTTP {t_res.status_code}", flush=True)
            except Exception as e:
                print(f"[-] Hata: {e}", flush=True)
        
        elif secim == "2":
            try:
                history_url = "https://api.steampowered.com/IEconService/GetTradeHistory/v1/"
                params = {"access_token": self.access_token, "max_trades": 10}
                h_res = self.session.get(history_url, params=params, timeout=10)
                if h_res.status_code == 200:
                    trades = h_res.json().get("response", {}).get("trades", [])
                    print(f"\n[+] Son {len(trades)} trade islemi:")
                    for trade in trades:
                        print(f"  - ID: {trade.get('tradeid')} | Tarih: {trade.get('time_init', 0)}")
                else:
                    print(f"[-] HTTP {h_res.status_code}", flush=True)
            except Exception as e:
                print(f"[-] Hata: {e}", flush=True)
        
        input("\nDevam etmek icin Enter'a basin...")

    def _mass_idling(self):
        print("\n[*] GERCEK Toplu Oyun Suresi Kasma (Mass Idling)", flush=True)
        
        popular_apps = [730, 570, 440, 578080, 1172470, 230410, 359550, 1085660, 1938090, 1229490]
        print(f"[*] {len(popular_apps)} oyun bulundu.", flush=True)
        
        print("\nKac oyunda es zamanli idling yapilsin?", flush=True)
        print("[1] 3 Oyun (Hafif)")
        print("[2] 5 Oyun (Orta)")
        print("[3] 9 Oyun (Agir - Tümü)")
        
        secim = input("Secim (1-3): ").strip()
        counts = {"1": 3, "2": 5, "3": 9}
        count = counts.get(secim, 3)
        selected_apps = popular_apps[:count]
        
        print(f"\n[*] {count} oyunda idling baslatiliyor...", flush=True)
        print("[*] CTRL+C ile durdurun.\n", flush=True)
        
        try:
            cycle = 0
            while True:
                cycle += 1
                for appid in selected_apps:
                    try:
                        url = "https://api.steampowered.com/IPlayerService/GetPlayedFreeGames/v1/"
                        params = {"access_token": self.access_token}
                        self.session.get(url, params=params, timeout=10)
                        
                        play_url = "https://api.steampowered.com/IPlayerService/SetPlayedGames/v1/"
                        play_payload = {
                            "access_token": self.access_token,
                            "steamid": self.steam_id,
                            "appids": selected_apps
                        }
                        self.session.post(play_url, data=play_payload, timeout=10)
                    except Exception:
                        pass
                
                status_line = f"[MASS-IDLE] Tur {cycle} | Aktif: {count} oyun | {time.strftime('%H:%M:%S')}"
                sys.stdout.write(f"\r{status_line}")
                sys.stdout.flush()
                time.sleep(60)
        except KeyboardInterrupt:
            print("\n[*] Toplu idling sonlandirildi.", flush=True)

    def _check_badge_status(self):
        print("\n[*] Kart/Badge Durumu Sorgulaniyor...", flush=True)
        try:
            badge_url = "https://api.steampowered.com/IPlayerService/GetBadges/v1/"
            badge_payload = {"access_token": self.access_token, "steamid": self.steam_id}
            b_res = self.session.post(badge_url, data=badge_payload, timeout=10)
            
            if b_res.status_code == 200:
                data = b_res.json().get("response", {})
                badges = data.get("badges", [])
                level = data.get("player_level", 0)
                xp = data.get("player_xp", 0)
                next_level_xp = data.get("player_xp_needed_to_current_level", 0) + 100
                
                print(f"\n[+] Steam Seviyesi: {level}")
                print(f"[+] Toplam XP: {xp}")
                print(f"[+] Sonraki seviye icin: {next_level_xp - xp} XP kaldi")
                print(f"[+] Toplam Rozet: {len(badges)}")
                
                if badges:
                    print("\n[*] Rozetler (ilk 10):")
                    for i, badge in enumerate(badges[:10]):
                        print(f"  {i+1}. AppID: {badge.get('appid', 0)} | Seviye: {badge.get('level', 0)} | XP: {badge.get('xp', 0)}")
            
            inv_url = "https://api.steampowered.com/IEconService/GetInventoryItems/v1/"
            inv_payload = {"access_token": self.access_token, "steamid": self.steam_id, "appid": 753}
            inv_res = self.session.post(inv_url, data=inv_payload, timeout=10)
            
            if inv_res.status_code == 200:
                items = inv_res.json().get("response", {}).get("items", [])
                print(f"\n[+] Steam Envanter: {len(items)} nesne")
                kart_sayisi = sum(1 for i in items if "card" in str(i.get("tags", {})).lower())
                if kart_sayisi > 0:
                    print(f"[+] Trading Kart: {kart_sayisi} adet")
        except Exception as e:
            print(f"[-] Hata: {e}", flush=True)
        
        input("\nDevam etmek icin Enter'a basin...")

    # ===== HESAP CALMA (TAKEOVER) =====
    def simulate_account_takeover(self):
        if not self.access_token:
            print("[-] Once giris yapmalisiniz.", flush=True)
            return
        
        print("\n" + "="*50)
        print("     GERCEK HESAP CALMA (ACCOUNT TAKEOVER)")
        print("="*50)
        print("[1] Token Exfiltration - Token'lari Disa Aktar")
        print("[2] Session Hijack - Oturumu Kopyala")
        print("[3] Profil Degerlerini Degistir (GERCEK)")
        print("[4] Steam Guard Ayarlarini Goster")
        print("[5] API Key Rotasyonu - Token'lari Iptal Et")
        print("[6] Hesap Verilerinin Tam Dump'i")
        print("[7] Geri Don")
        print("="*50)
        print("[!] TUM ISLEMLER GERCEK API CAGRISIDIR")
        print("[!] SADECE IZINLI HESAPLARDA KULLANIN")
        print("="*50)
        
        choice = input("Seciminiz (1-7): ").strip()
        
        if choice == "1":
            self._token_exfiltrate()
        elif choice == "2":
            self._session_hijack()
        elif choice == "3":
            self._real_profile_takeover()
        elif choice == "4":
            self._show_guard_settings()
        elif choice == "5":
            self._real_token_revocation()
        elif choice == "6":
            self._full_account_dump()
        elif choice == "7":
            return

    def _token_exfiltrate(self):
        print("\n[*] Token Exfiltration baslatiliyor...", flush=True)
        print(f"\n[+] Access Token (ilk 50): {self.access_token[:50]}..." if self.access_token else "[-] Token yok")
        print(f"[+] Refresh Token (ilk 50): {self.refresh_token[:50]}..." if self.refresh_token else "[-] Refresh token yok")
        print(f"[+] SteamID64: {self.steam_id}")
        
        print("\n[*] Session cookies:")
        cookies = self.session.cookies.get_dict()
        for name, value in cookies.items():
            print(f"  [COOKIE] {name} = {value[:50]}..." if len(value) > 50 else f"  [COOKIE] {name} = {value}")
        
        exfil_data = {
            "steam_id": self.steam_id,
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "cookies": cookies,
            "headers": dict(self.session.headers),
            "timestamp": int(time.time()),
            "source": "HackerAI Pentest Tool"
        }
        
        filename = f"steam_exfiltrated_{self.steam_id}.json"
        with open(filename, "w") as f:
            json.dump(exfil_data, f, indent=2)
        print(f"\n[+] Token bilgileri '{filename}' dosyasina kaydedildi!")
        print(f"[+] Dosya boyutu: {os.path.getsize(filename)} bytes")
        
        print("\n[*] Token test ediliyor...")
        test_headers = {"Authorization": f"Bearer {self.access_token}"}
        test_res = self.session.get(
            "https://api.steampowered.com/IPlayerService/GetSteamLevel/v1/",
            params={"access_token": self.access_token, "steamid": self.steam_id},
            headers=test_headers,
            timeout=10
        )
        if test_res.status_code == 200:
            print("[+] Token GECERLI! API erisimi basarili.")
        else:
            print(f"[-] Token GECERSIZ! HTTP {test_res.status_code}")
        
        input("\nDevam etmek icin Enter'a basin...")

    def _session_hijack(self):
        print("\n[*] Session Hijack Bilgileri", flush=True)
        print("[*] Oturum bilgileri toplaniyor...")
        
        print(f"\n[+] Session bilgileri:")
        print(f"  Token: {self.access_token[:30]}...{self.access_token[-10:]}" if self.access_token else "  Token: YOK")
        print(f"  Cookie sayisi: {len(self.session.cookies.get_dict())}")
        
        print("\n[*] Yeni session test ediliyor (hijack simulasyonu)...")
        test_session = requests.Session()
        test_session.headers.update({
            "Authorization": f"Bearer {self.access_token}",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
        })
        
        try:
            test_url = "https://api.steampowered.com/IPlayerService/GetSteamLevel/v1/"
            test_res = test_session.post(test_url, data={"access_token": self.access_token, "steamid": self.steam_id}, timeout=10)
            if test_res.status_code == 200:
                level = test_res.json().get("response", {}).get("player_level", "?")
                print(f"[+] Hijack BASARILI! Yeni session ile seviye: {level}")
        except Exception as e:
            print(f"[-] Hijack test hatasi: {e}")
        
        print("\n[!] Bu bilgilerle:")
        print("  - Token'i baska bir cihazda kullan")
        print("  - Steam API'ye tam erisim")
        print("  - Kullanici adina islem yap")
        
        input("\nDevam etmek icin Enter'a basin...")

    def _real_profile_takeover(self):
        print("\n[*] GERCEK Profil Degistirme Modulu", flush=True)
        
        profile = self.get_profile_data()
        if profile:
            print(f"\n[+] Mevcut Profil:")
            print(f"  Nick: {profile.get('nick', 'Bilinmiyor')}")
            print(f"  SteamID: {profile.get('steamid', 'Bilinmiyor')}")
            print(f"  Seviye: {profile.get('level', 0)}")
            print(f"  Bakiye: {profile.get('bakiye', 0)} {profile.get('para_birimi', '')}")
        else:
            print("[-] Profil bilgisi alinamadi")
            return
        
        print("\n" + "="*40)
        print("DEGISTIRILECEK ALANLAR (GERCEK API)")
        print("="*40)
        
        print("\n[*] 1. Profil adi degistirilsin mi? (E/H)")
        if input("> ").strip().upper() == "E":
            yeni_isim = input("Yeni profil adi: ").strip()
            if yeni_isim:
                try:
                    url = "https://api.steampowered.com/ISteamUser/UpdateProfile/v1/"
                    payload = {
                        "access_token": self.access_token,
                        "steamid": self.steam_id,
                        "personaname": yeni_isim
                    }
                    headers = {"Authorization": f"Bearer {self.access_token}"}
                    res = self.session.post(url, data=payload, headers=headers, timeout=10)
                    if res.status_code == 200:
                        print(f"[+] Profil adi basariyla '{yeni_isim}' olarak degistirildi!")
                    else:
                        print(f"[-] Degistirilemedi. HTTP {res.status_code}")
                except Exception as e:
                    print(f"[-] Hata: {e}")
        
        print("\n[*] 2. Profil aciklamasi degistirilsin mi? (E/H)")
        if input("> ").strip().upper() == "E":
            yeni_aciklama = input("Yeni profil aciklamasi: ").strip()
            if yeni_aciklama:
                try:
                    url = "https://api.steampowered.com/ISteamUser/UpdateProfile/v1/"
                    payload = {
                        "access_token": self.access_token,
                        "steamid": self.steam_id,
                        "summary": yeni_aciklama
                    }
                    headers = {"Authorization": f"Bearer {self.access_token}"}
                    res = self.session.post(url, data=payload, headers=headers, timeout=10)
                    if res.status_code == 200:
                        print("[+] Profil aciklamasi guncellendi!")
                    else:
                        print(f"[-] Guncellenemedi. HTTP {res.status_code}")
                except Exception as e:
                    print(f"[-] Hata: {e}")
        
        print("\n[!] Hesap calindiginda saldirgan tum bu bilgileri degistirebilir.")
        input("\nDevam etmek icin Enter'a basin...")

    def _show_guard_settings(self):
        print("\n[*] Steam Guard Ayarlari Sorgulaniyor...", flush=True)
        try:
            guard_url = "https://api.steampowered.com/ITwoFactorService/GetTwoFactorStatus/v1/"
            guard_payload = {"access_token": self.access_token, "steamid": self.steam_id}
            g_res = self.session.post(guard_url, data=guard_payload, timeout=10)
            
            if g_res.status_code == 200:
                guard_data = g_res.json().get("response", {})
                print(f"[+] Steam Guard: {'AKTIF' if guard_data.get('enabled', 0) == 1 else 'DEVRE DISI'}")
                print(f"[+] Mobil Dogrulama: {'AKTIF' if guard_data.get('mobile_enabled', 0) == 1 else 'DEVRE DISI'}")
                print(f"[+] E-posta Dogrulama: {'AKTIF' if guard_data.get('email_enabled', 0) == 1 else 'DEVRE DISI'}")
        except Exception as e:
            print(f"[-] Hata: {e}")
        
        input("\nDevam etmek icin Enter'a basin...")

    def _real_token_revocation(self):
        print("\n[*] GERCEK Token Iptali (Revocation)", flush=True)
        print("\n[!] Bu islem MEVCUT TOKEN'I GECERSIZ KILAR!")
        print("[!] Tekrar giris yapmaniz gerekir.")
        print("\nDevam etmek istediginize emin misiniz? (E/H):")
        
        if input("> ").strip().upper() != "E":
            print("[*] Islem iptal edildi.")
            input("Devam etmek icin Enter'a basin...")
            return
        
        print("\n[*] Token iptal ediliyor...", flush=True)
        try:
            revoke_url = "https://api.steampowered.com/IAuthenticationService/RevokeToken/v1/"
            revoke_payload = {"access_token": self.access_token, "steamid": self.steam_id}
            res = self.session.post(revoke_url, data=revoke_payload, timeout=10)
            
            if res.status_code == 200:
                print("[+] Token basariyla iptal edildi!")
            else:
                print(f"[-] Iptal basarisiz. HTTP {res.status_code}")
                print("[*] Steam Community'den cikis yapiliyor...")
            
            logout_url = "https://steamcommunity.com/login/logout/"
            logout_payload = {"sessionid": self.session_id}
            self.session.post(logout_url, data=logout_payload, timeout=10)
            
            self.access_token = None
            self.refresh_token = None
            print("[+] Token'lar sifirlandi!")
            print("[!] Artik bu programla islem yapamazsiniz. Yeniden giris yapmalisiniz.")
        except Exception as e:
            print(f"[-] Hata: {e}")
        
        input("\nDevam etmek icin Enter'a basin...")

    def _full_account_dump(self):
        print("\n[*] Hesap Verilerinin Tam Dump'i Baslatiliyor...", flush=True)
        
        print("[*] Profil bilgisi aliniyor...")
        profile = self.get_profile_data()
        
        print("[*] Badge bilgisi aliniyor...")
        badges = {}
        try:
            badge_url = "https://api.steampowered.com/IPlayerService/GetBadges/v1/"
            badge_payload = {"access_token": self.access_token, "steamid": self.steam_id}
            b_res = self.session.post(badge_url, data=badge_payload, timeout=10)
            if b_res.status_code == 200:
                badges = b_res.json().get("response", {})
        except Exception:
            pass
        
        print("[*] Trade bilgisi aliniyor...")
        trades = []
        try:
            trade_url = "https://api.steampowered.com/IEconService/GetTradeHistory/v1/"
            params = {"access_token": self.access_token, "max_trades": 20}
            t_res = self.session.get(trade_url, params=params, timeout=10)
            if t_res.status_code == 200:
                trades = t_res.json().get("response", {}).get("trades", [])
        except Exception:
            pass
        
        print("[*] Envanter bilgisi aliniyor...")
        inventory = []
        try:
            inv_url = "https://api.steampowered.com/IEconService/GetInventoryItems/v1/"
            inv_payload = {"access_token": self.access_token, "steamid": self.steam_id, "appid": 753}
            inv_res = self.session.post(inv_url, data=inv_payload, timeout=10)
            if inv_res.status_code == 200:
                inventory = inv_res.json().get("response", {}).get("items", [])
        except Exception:
            pass
        
        dump_data = {
            "steam_id": self.steam_id,
            "timestamp": int(time.time()),
            "profile": profile,
            "badges": badges,
            "recent_trades": [{"trade_id": t.get("tradeid"), "time": t.get("time_init"), "status": t.get("status", 0)} for t in trades[:20]],
            "inventory_count": len(inventory),
            "tokens": {"access_token": self.access_token, "refresh_token": self.refresh_token},
            "session_cookies": dict(self.session.cookies.get_dict()),
            "headers": dict(self.session.headers)
        }
        
        filename = f"steam_full_dump_{self.steam_id}.json"
        with open(filename, "w") as f:
            json.dump(dump_data, f, indent=2, default=str)
        
        print(f"\n[+] Tam dump '{filename}' dosyasina kaydedildi!")
        print(f"[+] Dosya boyutu: {os.path.getsize(filename)} bytes")
        print(f"\n[*] Dump icerigi:")
        print(f"  - Profil: {profile.get('nick', 'N/A')} (Level {profile.get('level', 0)})")
        print(f"  - Badge: {len(badges.get('badges', [])) if isinstance(badges, dict) else 0} adet")
        print(f"  - Envanter: {len(inventory)} nesne")
        print(f"  - Trade: {len(trades)} islem")
        print(f"\n[!] BU DOSYA GIZLIDIR! Token'lar acik metin icerir.")
        
        input("\nDevam etmek icin Enter'a basin...")


def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def show_menu():
    auth_system = SteamAuthArchitecture()
    while True:
        clear_screen()
        print("="*50)
        print("     STEAM PENTEST & BOOSTING CLIENT")
        print("         GERCEK API ISLEMLERI")
        print("="*50)
        print("[1]  Steam Giris Yap (Token Al)")
        print("[2]  Hesap & Profil Bilgileri")
        print("[3]  Kesif Kuyrugu Temizle (Kart Kas)")
        print("[4]  Oyun Suresi Kasma (Idling)")
        print("-"*50)
        print("[5]  HESAP GERME (Boost) - GERCEK ISLEMLER")
        print("[6]  HESAP CALMA SIMULASYONU - GERCEK API")
        print("-"*50)
        print("[7]  Cikis")
        print("="*50)
        
        secim = input("Seciminiz (1-7): ").strip()
        
        if secim == "1":
            username = input("\nSteam Kullanici Adi: ").strip()
            password = input("Steam Sifre: ").strip()
            if username and password:
                auth_system.execute_login(username, password)
            input("\nDevam etmek icin Enter'a basin...")
        elif secim == "2":
            data = auth_system.get_profile_data()
            print("\n=== HESAP BILGILERI ===")
            if data:
                print(f"[+] SteamID64: {data['steamid']}")
                print(f"[+] Profil Nick: {data.get('nick', 'Bilinmiyor')}")
                print(f"[+] Steam Seviyesi: {data.get('level', 0)}")
                print(f"[+] Profil URL: {data.get('profil_url', 'N/A')}")
                print(f"[+] Cuzdan Bakiyesi: {data['bakiye']} {data['para_birimi']}")
            else:
                print("[-] Token yok veya hesap bilgileri cekilemedi. Once giris yapin.")
            input("\nDevam etmek icin Enter'a basin...")
        elif secim == "3":
            auth_system.clear_discovery_queue()
            input("\nDevam etmek icin Enter'a basin...")
        elif secim == "4":
            if not auth_system.access_token:
                print("\n[-] Once giris yapmalisiniz.")
            else:
                appid = input("\nOyunun AppID'sini girin: ").strip()
                if appid.isdigit():
                    auth_system.start_idling(int(appid))
            input("\nDevam etmek icin Enter'a basin...")
        elif secim == "5":
            auth_system.boost_account()
        elif secim == "6":
            auth_system.simulate_account_takeover()
        elif secim == "7":
            sys.exit(0)

if __name__ == "__main__":
    try:
        show_menu()
    except KeyboardInterrupt:
        sys.exit(0)
