import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import customtkinter as ctk
import threading
import requests
import json
import base64
import random
import time
import socket
import hashlib
import re
import webbrowser
import os
import yaml
import qrcode
from io import BytesIO
from PIL import Image, ImageTk
from urllib.parse import unquote, urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
import sqlite3
from typing import List, Dict, Any
import logging

# ---------------- Configuration ----------------
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

COLORS = {
    'background': '#0d1117',
    'sidebar': '#161b22',
    'card': '#21262d',
    'primary': '#238636',
    'primary-hover': '#2ea043',
    'danger': '#ff4444',
    'success': '#3fb950',
    'warning': '#d29922',
    'info': '#58a6ff',
    'accent': '#da3633',
    'telegram': '#0088cc',
    'text-primary': '#f0f6fc',
    'text-secondary': '#8b949e',
}

GITHUB_CONFIG_SOURCES = [
    "https://raw.githubusercontent.com/MatinGhanbari/v2ray-configs/main/subscriptions/v2ray/all_sub.txt",
    "https://raw.githubusercontent.com/MatinGhanbari/v2ray-configs/main/subscriptions/filtered/subs/vmess.txt",
    "https://raw.githubusercontent.com/MatinGhanbari/v2ray-configs/main/subscriptions/filtered/subs/vless.txt",
    "https://raw.githubusercontent.com/MatinGhanbari/v2ray-configs/main/subscriptions/filtered/subs/trojan.txt",
    "https://raw.githubusercontent.com/MatinGhanbari/v2ray-configs/main/subscriptions/filtered/subs/ss.txt",
    "https://raw.githubusercontent.com/MatinGhanbari/v2ray-configs/main/subscriptions/v2ray/subs/sub1.txt",
    "https://raw.githubusercontent.com/mahdibland/V2RayAggregator/master/Eternity.txt",
    "https://raw.githubusercontent.com/mahdibland/V2RayAggregator/master/sub/splitted/vmess.txt",
    "https://raw.githubusercontent.com/mahdibland/V2RayAggregator/master/sub/splitted/trojan.txt",
    "https://raw.githubusercontent.com/mahdibland/V2RayAggregator/master/sub/splitted/ss.txt",
    "https://raw.githubusercontent.com/mahdibland/V2RayAggregator/master/sub/splitted/ssr.txt",
    "https://raw.githubusercontent.com/Epodonios/v2ray-configs/refs/heads/main/Sub2.txt"
]

EXPORT_FORMATS = {
    "V2rayN": {"extension": ".txt", "format": "base64"},
    "Shadowrocket": {"extension": ".conf", "format": "surge"},
    "Clash": {"extension": ".yml", "format": "yaml"},
    "Quantumult": {"extension": ".conf", "format": "quantumult"},
    "Surge": {"extension": ".conf", "format": "surge"},
    "Raw": {"extension": ".txt", "format": "raw"}
}

SUPPORTED_PROTOCOLS = ["vmess", "vless", "trojan", "ss", "tuic", "hysteria", "wireguard", "ssr"]


class AdvancedV2RayTester:
    def __init__(self, max_workers=25):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.logger = self.setup_logger()
        self.clash_test_urls = [
            "http://www.gstatic.com/generate_204",
            "http://www.google.com/generate_204",
            "http://connectivitycheck.android.com/generate_204",
            "https://cp.cloudflare.com/generate_204" 
        ]
        
    def setup_logger(self):
        logger = logging.getLogger('V2RayTester')
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        return logger

    def get_real_delay(self, config_uri, timeout=3):
        """Measure real delay similar to V2RayNG with HTTP test priority"""
        try:
            protocol = config_uri.split("://")[0] if "://" in config_uri else ""
            ip = self.extract_ip(config_uri, protocol)
            port = self.extract_port(config_uri, protocol)
            
            if not ip or not port:
                self.logger.warning(f"Invalid IP/port for config: {config_uri[:50]}...")
                return None
            
            # V2RayNG-like HTTP test
            best_latency = float('inf')
            for test_url in self.clash_test_urls:
                try:
                    start_time = time.time()
                    response = requests.get(
                        test_url,
                        timeout=timeout,
                        headers={'User-Agent': 'V2RayNG/1.8.21'},
                        allow_redirects=False
                    )
                    if response.status_code in [204, 200]:
                        latency = round((time.time() - start_time) * 1000)
                        if latency < best_latency:
                            best_latency = latency
                            self.logger.debug(f"Successful HTTP test on {test_url}: {latency}ms")
                except Exception as e:
                    self.logger.debug(f"Failed HTTP test on {test_url}: {str(e)}")
                    continue
            
            if best_latency != float('inf'):
                return best_latency
            
            start_time = time.time()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((ip, port))
            delay = round((time.time() - start_time) * 1000)
            sock.close()
            
            self.logger.debug(f"Socket test for {ip}:{port} - Result: {'Success' if result == 0 else 'Failed'}, Delay: {delay}ms")
            return delay if result == 0 else None
        except Exception as e:
            self.logger.error(f"Delay test error for {config_uri[:50]}...: {str(e)}")
            return None

    def extract_port(self, config_uri, protocol):
        try:
            if protocol == "vmess":
                return self.extract_port_vmess(config_uri)
            elif protocol in ["vless", "trojan", "ss", "ssr"]:
                return self.extract_port_from_url(config_uri)
        except Exception as e:
            self.logger.error(f"Port extraction error for {config_uri[:50]}...: {str(e)}")
        return 443

    def extract_port_vmess(self, config_uri):
        try:
            b64_data = config_uri.split("://")[1].split("#")[0]
            padding = 4 - len(b64_data) % 4
            if padding != 4:
                b64_data += "=" * padding
            decoded = base64.b64decode(b64_data).decode('utf-8', errors='ignore')
            config_json = json.loads(decoded)
            port = config_json.get('port', 443)
            self.logger.debug(f"Extracted port {port} from VMess config")
            return port
        except Exception as e:
            self.logger.error(f"VMess port extraction error: {str(e)}")
            return 443

    def extract_port_from_url(self, config_uri):
        try:
            parsed = urlparse(config_uri)
            if parsed.port:
                self.logger.debug(f"Extracted port {parsed.port} from URL")
                return parsed.port
            default_ports = {
                'vless': 443, 'vmess': 443, 'trojan': 443, 
                'ss': 8388, 'ssr': 8388, 'tuic': 443, 'hysteria': 443
            }
            port = default_ports.get(parsed.scheme, 443)
            self.logger.debug(f"Using default port {port} for protocol {parsed.scheme}")
            return port
        except Exception as e:
            self.logger.error(f"URL port extraction error: {str(e)}")
            return 443

    def advanced_ping(self, ip, port=443, timeout=5):
        try:
            start_time = time.time()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((ip, port))
            response_time = round((time.time() - start_time) * 1000)
            sock.close()
            
            self.logger.debug(f"Ping test to {ip}:{port} - Result: {'Success' if result == 0 else 'Failed'}, Time: {response_time}ms")
            return response_time if result == 0 else None
        except Exception as e:
            self.logger.error(f"Ping test error for {ip}:{port}: {str(e)}")
            return None

    def analyze_config_quality(self, config):
        score = 100
        issues = []
        
        name = config.get('name', '').lower()
        if any(word in name for word in ['test', 'demo', 'expired', 'old']):
            score -= 30
            issues.append("Test or expired config")
        
        ping = config.get('ping')
        if ping:
            if ping < 100:
                score += 20
            elif ping > 500:
                score -= 30
                issues.append("High latency")
            elif ping > 1000:
                score -= 50
                issues.append("Very high latency")
        
        protocol = config.get('protocol', '')
        if protocol in ['vless', 'trojan']:
            score += 10
        elif protocol == 'ss':
            score -= 5
        elif protocol == 'ssr':
            score -= 10
            issues.append("SSR might be outdated")
        
        if any(word in name for word in ['slow', 'bad', 'dead']):
            score -= 20
        
        return {
            'score': max(0, min(100, score)),
            'issues': issues,
            'grade': 'A+' if score >= 95 else 'A' if score >= 85 else 'B' if score >= 70 else 'C' if score >= 50 else 'D'
        }

    def test_config(self, config_uri):
        try:
            protocol = config_uri.split("://")[0] if "://" in config_uri else ""
            
            if protocol not in SUPPORTED_PROTOCOLS:
                self.logger.warning(f"Unsupported protocol: {protocol}")
                return {"status": "Unsupported", "protocol": protocol}
            
            ip = self.extract_ip(config_uri, protocol)
            if not ip:
                self.logger.warning(f"No valid IP found for config: {config_uri[:50]}...")
                return {"status": "No IP Found", "protocol": protocol}
            
            real_delay = self.get_real_delay(config_uri)
            
            if real_delay:
                self.logger.info(f"Config tested successfully: {config_uri[:50]}... - Delay: {real_delay}ms")
                return {
                    "status": "Active",
                    "protocol": protocol,
                    "ping": real_delay,
                    "ip": ip,
                    "quality": self.analyze_config_quality({
                        'protocol': protocol,
                        'ping': real_delay,
                        'name': config_uri.split('#')[-1] if '#' in config_uri else ''
                    })
                }
            else:
                ping_result = self.advanced_ping(ip)
                status = "Timeout" if not ping_result else "Active (Port Test)"
                
                self.logger.info(f"Fallback test result for {config_uri[:50]}...: {status}")
                return {
                    "status": status,
                    "protocol": protocol,
                    "ping": ping_result,
                    "ip": ip,
                    "quality": self.analyze_config_quality({
                        'protocol': protocol,
                        'ping': ping_result,
                        'name': config_uri.split('#')[-1] if '#' in config_uri else ''
                    })
                }
        except Exception as e:
            self.logger.error(f"Test config error for {config_uri[:50]}...: {str(e)}")
            return {"status": f"Error: {str(e)}", "protocol": "Unknown"}

    def extract_ip(self, config_uri, protocol):
        try:
            ip_match = re.search(r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b', config_uri)
            if ip_match:
                ip = ip_match.group(0)
                self.logger.debug(f"Extracted direct IP: {ip}")
                return ip
            
            domain_match = re.search(r'@([a-zA-Z0-9][a-zA-Z0-9.-]{1,254}[a-zA-Z0-9])[:/]', config_uri)
            if domain_match:
                domain = domain_match.group(1)
                self.logger.debug(f"Extracted domain: {domain}")
                return domain
            
            if protocol == "vmess":
                return self.extract_ip_vmess(config_uri)
            elif protocol in ["vless", "trojan", "ss", "ssr"]:
                return self.extract_ip_from_url(config_uri)
        except Exception as e:
            self.logger.error(f"IP extraction error for {config_uri[:50]}...: {str(e)}")
        return ""

    def extract_ip_vmess(self, config_uri):
        try:
            b64_data = config_uri.split("://")[1].split("#")[0]
            padding = 4 - len(b64_data) % 4
            if padding != 4:
                b64_data += "=" * padding
            decoded = base64.b64decode(b64_data).decode('utf-8', errors='ignore')
            config_json = json.loads(decoded)
            ip = config_json.get('add', '')
            self.logger.debug(f"Extracted VMess IP: {ip}")
            return ip
        except Exception as e:
            self.logger.error(f"VMess IP extraction error: {str(e)}")
            return ""

    def extract_ip_from_url(self, config_uri):
        try:
            parsed = urlparse(config_uri)
            if parsed.hostname:
                self.logger.debug(f"Extracted hostname: {parsed.hostname}")
                return parsed.hostname
        except Exception as e:
            self.logger.error(f"URL IP extraction error: {str(e)}")
        return ""

# ---------------- Telegram Bot Manager ----------------
class EnhancedTelegramBotManager:
    def __init__(self):
        self.bot = None
        self.is_connected = False
        self.message_templates = {
            'default': """🔰 *{remark}*

⚡ **Protocol:** {protocol}
📊 **Latency:** {ping}ms
⭐ **Quality:** {quality}
🌍 **Server:** {server}
📅 **Updated:** {time}

`{config}`""",
            'premium': """🌟 **Premium V2Ray Configuration** 🌟

🔰 *{remark}*
⚡ **Type:** {protocol} | ⭐ **Grade:** {quality}
📊 **Performance:** {ping}ms Latency
🌍 **Location:** {server}
🕒 **Freshness:** {time}

```{config}```

💎 **Best for streaming and gaming**""",
            'simple': """{protocol} Config | {ping}ms
{config}"""
        }
    
    def connect_bot(self, token):
        try:
            try:
                import telebot
            except ImportError:
                return False, "Telebot library not installed. Run: pip install pyTelegramBotAPI"
            
            if not token or len(token) < 10:
                return False, "Invalid bot token"
            
            self.bot = telebot.TeleBot(token, parse_mode='HTML')
            bot_info = self.bot.get_me()
            if bot_info:
                self.is_connected = True
                return True, f"✅ Connected to @{bot_info.username}"
            else:
                return False, "Failed to get bot information"
        except Exception as e:
            error_msg = str(e)
            if "Unauthorized" in error_msg:
                return False, "❌ Invalid bot token"
            elif "timed out" in error_msg.lower():
                return False, "⏰ Connection timeout - check your internet"
            else:
                return False, f"❌ Connection error: {error_msg}"

    def send_config_to_channel(self, channel_id, config, custom_remark=None, template='default', additional_text=""):
        if not self.is_connected or not self.bot:
            return False, "Bot not connected"
        
        try:
            if not channel_id:
                return False, "Channel ID is empty"
            
            remark = custom_remark if custom_remark else config.get('name', 'V2Ray Config')
            remark = unquote(remark)
            protocol = config.get('protocol', '').upper()
            ping = config.get('ping', 'N/A')
            quality = config.get('quality', {}).get('grade', 'N/A')
            server = config.get('ip', 'Unknown')
            config_uri = config.get('uri', '')
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
            
            if custom_remark and '#' in config_uri:
                config_uri = config_uri.split('#')[0] + f'#{custom_remark}'
            elif custom_remark and '#' not in config_uri:
                config_uri = config_uri + f'#{custom_remark}'
            
            message_template = self.message_templates.get(template, self.message_templates['default'])
            formatted_message = message_template.format(
                remark=remark,
                protocol=protocol,
                ping=ping,
                quality=quality,
                server=server,
                time=current_time,
                config=config_uri
            )
            
            if additional_text:
                formatted_message += f"\n\n{additional_text}"
            
            self.bot.send_message(channel_id, formatted_message, parse_mode='Markdown')
            return True, "✅ Configuration sent successfully"
        except Exception as e:
            error_msg = str(e)
            if "chat not found" in error_msg.lower():
                return False, "❌ Channel not found - check Channel ID"
            elif "bot was blocked" in error_msg.lower():
                return False, "❌ Bot was blocked by the user"
            elif "not enough rights" in error_msg.lower():
                return False, "❌ Bot doesn't have permission to send messages"
            else:
                return False, f"❌ Send failed: {error_msg}"

    def test_connection(self, token, channel_id):
        success, message = self.connect_bot(token)
        if not success:
            return success, message
        
        try:
            test_message = "🤖 *V2Ray Manager Test Message*\n\nThis is a test message to verify bot connectivity and permissions."
            self.bot.send_message(channel_id, test_message, parse_mode='Markdown')
            return True, "✅ Connection test successful! Bot can send messages."
        except Exception as e:
            return False, f"❌ Test failed: {str(e)}"


class AutoUpdateManager:
    def __init__(self, update_callback):
        self.update_callback = update_callback
        self.update_interval = 30
        self.is_running = False
        self.thread = None
        
    def start_auto_update(self, interval_minutes=30):
        self.update_interval = interval_minutes
        self.is_running = True
        self.thread = threading.Thread(target=self._auto_update_loop, daemon=True)
        self.thread.start()
        
    def stop_auto_update(self):
        self.is_running = False
        
    def _auto_update_loop(self):
        while self.is_running:
            time.sleep(self.update_interval * 60)
            if self.is_running:
                print(f"Auto-update triggered after {self.update_interval} minutes")
                self.update_callback()
                
    def set_interval(self, interval_minutes):
        self.update_interval = interval_minutes


class QRCodeGenerator:
    @staticmethod
    def generate_qr_code(config_uri, size=300):
        try:
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(config_uri)
            qr.make(fit=True)
            
            img = qr.make_image(fill_color="black", back_color="white")
            img = img.resize((size, size), Image.Resampling.LANCZOS)
            
            return img
        except Exception as e:
            print(f"QR generation error: {e}")
            return None


class GitHubConfigHunter:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.logger = self.setup_logger()

    def setup_logger(self):
        logger = logging.getLogger('GitHubConfigHunter')
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        return logger

    def fix_github_url(self, url):
        try:
            parsed = urlparse(url)
            if 'github.com' not in parsed.netloc:
                return url

            url = url.replace('/blob/', '/raw/')
            url = re.sub(r'/refs/heads/[^/]+', '', url)
            
            if not url.startswith('https://raw.githubusercontent.com'):
                parts = parsed.path.split('/')
                if len(parts) >= 4:
                    repo_owner, repo_name = parts[1:3]
                    path = '/'.join(parts[3:])
                    url = f"https://raw.githubusercontent.com/{repo_owner}/{repo_name}/{path}"
            
            self.logger.debug(f"Fixed URL: Original: {url} -> Fixed: {url}")
            return url
        except Exception as e:
            self.logger.error(f"Error fixing URL {url}: {str(e)}")
            return url

    def is_valid_config(self, config):
        try:
            if len(config) < 10:
                self.logger.warning(f"Config too short: {config[:50]}...")
                return False
            
            protocol = config.split("://")[0] if "://" in config else ""
            if protocol not in SUPPORTED_PROTOCOLS:
                self.logger.warning(f"Invalid protocol in config: {protocol}")
                return False
            
            if protocol == "vmess":
                try:
                    b64_data = config.split("://")[1].split("#")[0]
                    padding = 4 - len(b64_data) % 4
                    if padding != 4:
                        b64_data += "=" * padding
                    decoded = base64.b64decode(b64_data).decode('utf-8', errors='ignore')
                    config_json = json.loads(decoded)
                    if not all(key in config_json for key in ['v', 'ps', 'add', 'port']):
                        self.logger.warning(f"Invalid VMess structure: {config[:50]}...")
                        return False
                except:
                    self.logger.warning(f"Invalid VMess encoding: {config[:50]}...")
                    return False
            elif protocol in ["vless", "trojan", "ss", "ssr"]:
                if '@' not in config or ':' not in config:
                    self.logger.warning(f"Invalid URL structure for {protocol}: {config[:50]}...")
                    return False
            
            return True
        except Exception as e:
            self.logger.error(f"Validation error for config {config[:50]}...: {str(e)}")
            return False

    def generate_config_name(self, config):
        try:
            protocol = config.split("://")[0] if "://" in config else "unknown"
            if '#' in config:
                name = config.split('#')[-1]
                if name.strip() and len(name) > 3:
                    return unquote(name)
            
            ip = self.extract_ip(config, protocol)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            return f"{protocol.upper()}_{ip or 'server'}_{timestamp}"
        except Exception as e:
            self.logger.error(f"Error generating name for config {config[:50]}...: {str(e)}")
            return f"Unnamed_{protocol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    def extract_ip(self, config, protocol):
        try:
            ip_match = re.search(r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b', config)
            if ip_match:
                ip = ip_match.group(0)
                self.logger.debug(f"Extracted direct IP: {ip}")
                return ip
            
            domain_match = re.search(r'@([a-zA-Z0-9][a-zA-Z0-9.-]{1,254}[a-zA-Z0-9])[:/]', config)
            if domain_match:
                domain = domain_match.group(1)
                self.logger.debug(f"Extracted domain: {domain}")
                return domain
            
            if protocol == "vmess":
                return self.extract_ip_vmess(config)
            elif protocol in ["vless", "trojan", "ss", "ssr"]:
                return self.extract_ip_from_url(config)
        except Exception as e:
            self.logger.error(f"IP extraction error for {config[:50]}...: {str(e)}")
        return ""

    def extract_ip_vmess(self, config):
        try:
            b64_data = config.split("://")[1].split("#")[0]
            padding = 4 - len(b64_data) % 4
            if padding != 4:
                b64_data += "=" * padding
            decoded = base64.b64decode(b64_data).decode('utf-8', errors='ignore')
            config_json = json.loads(decoded)
            ip = config_json.get('add', '')
            self.logger.debug(f"Extracted VMess IP: {ip}")
            return ip
        except Exception as e:
            self.logger.error(f"VMess IP extraction error: {str(e)}")
            return ""

    def extract_ip_from_url(self, config):
        try:
            parsed = urlparse(config)
            if parsed.hostname:
                self.logger.debug(f"Extracted hostname: {parsed.hostname}")
                return parsed.hostname
        except Exception as e:
            self.logger.error(f"URL IP extraction error: {str(e)}")
        return ""

    def fetch_configs_from_sources(self, max_results=500):
        all_configs = []
        successful_sources = 0
        
        self.logger.info(f"Starting fetch from {len(GITHUB_CONFIG_SOURCES)} sources (max {max_results} configs)")
        
        for source_url in GITHUB_CONFIG_SOURCES:
            fixed_url = self.fix_github_url(source_url)
            try:
                self.logger.info(f"Fetching from: {source_url} (Fixed: {fixed_url})")
                response = self.session.get(fixed_url, timeout=20)
                
                if response.status_code == 200:
                    configs = self.extract_configs_from_text(response.text)
                    valid_configs = [cfg for cfg in configs if self.is_valid_config(cfg)]
                    all_configs.extend(valid_configs)
                    successful_sources += 1
                    self.logger.info(f"✓ Found {len(configs)} configs ({len(valid_configs)} valid) from {fixed_url}")
                    
                    if len(all_configs) >= max_results:
                        self.logger.info(f"Reached max results ({max_results})")
                        break
                else:
                    self.logger.warning(f"✗ Failed to fetch from {fixed_url}: HTTP {response.status_code}")
                    
            except Exception as e:
                self.logger.error(f"✗ Error fetching from {fixed_url}: {str(e)}")
        
        self.logger.info(f"Completed fetch: {successful_sources}/{len(GITHUB_CONFIG_SOURCES)} sources successful")
        self.logger.info(f"Total valid configurations found: {len(all_configs)}")
        
        return all_configs[:max_results]

    def extract_configs_from_text(self, text):
        configs = []
        patterns = [
            r'(vmess://[A-Za-z0-9+/=]{20,}(?:#[^\s\x00-\x1F\x7F]*)?)',
            r'(vless://[0-9a-fA-F-]{36}@[a-zA-Z0-9.-]+:[0-9]+(?:\?[^\s#]*)?(?:#[^\s\x00-\x1F\x7F]*)?)',
            r'(trojan://[^@:\s]+@[a-zA-Z0-9.-]+:[0-9]+(?:\?[^\s#]*)?(?:#[^\s\x00-\x1F\x7F]*)?)',
            r'(ss://(?:[A-Za-z0-9+/=]+|(?:[a-zA-Z0-9-]+:[^@:\s]+)@[a-zA-Z0-9.-]+:[0-9]+)(?:#[^\s\x00-\x1F\x7F]*)?)',
            r'(ssr://[A-Za-z0-9+/=]+(?:#[^\s\x00-\x1F\x7F]*)?)',
            r'(https?://[^\s<>"]+\.txt)',
            r'(https?://[^\s<>"]+?(?:subscription|sub)[^\s<>"]*)'
        ]
        
        try:
            if re.match(r'^[A-Za-z0-9+/=]+$', text.strip()):
                decoded_text = base64.b64decode(text.strip()).decode('utf-8', errors='ignore')
                text += '\n' + decoded_text
                self.logger.debug("Detected and decoded base64 content")
        except:
            pass
        
        for pattern in patterns:
            matches = re.finditer(pattern, text, re.MULTILINE)
            for match in matches:
                config = match.group(0)
                if any(proto in config.lower() for proto in SUPPORTED_PROTOCOLS):
                    configs.append(config)
                    self.logger.debug(f"Extracted config: {config[:50]}...")
        
        configs_with_names = []
        for config in set(configs):
            if self.is_valid_config(config):
                config_name = self.generate_config_name(config)
                configs_with_names.append((config, config_name))
        
        self.logger.info(f"Extracted {len(configs_with_names)} valid unique configs")
        return [cfg[0] for cfg in configs_with_names]

class AIConfigManager:
    def __init__(self):
        self.hunter = GitHubConfigHunter()
        self.tester = AdvancedV2RayTester()
        
    def smart_config_filter(self, configs, user_preferences):
        filtered = []
        
        for config in configs:
            score = 0
            
            protocol = config.get('protocol', '')
            if protocol in user_preferences.get('preferred_protocols', []):
                score += 30
            
            ping = config.get('ping', float('inf'))
            max_ping = user_preferences.get('max_ping', 300)
            if ping < max_ping:
                score += 50 - (ping / 10)
            
            quality = config.get('quality', {}).get('score', 0)
            score += quality / 2
            
            issues = config.get('quality', {}).get('issues', [])
            score -= len(issues) * 5
            
            if score >= user_preferences.get('min_score', 50):
                config['ai_score'] = round(score, 1)
                filtered.append(config)
        
        return sorted(filtered, key=lambda x: x.get('ai_score', 0), reverse=True)

class ConfigDatabase:
    def __init__(self):
        self.conn = sqlite3.connect('v2ray_configs.db', check_same_thread=False)
        self.create_tables()
    
    def create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                protocol TEXT,
                uri TEXT UNIQUE,
                name TEXT,
                ping INTEGER,
                status TEXT,
                quality_score INTEGER,
                ai_score REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS telegram_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_token TEXT,
                channel_id TEXT,
                message_template TEXT DEFAULT 'default',
                auto_send BOOLEAN DEFAULT FALSE,
                last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS app_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                auto_update_interval INTEGER DEFAULT 30,
                max_configs INTEGER DEFAULT 500,
                preferred_protocols TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self.conn.commit()
    
    def save_config(self, config):
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO configs 
                (protocol, uri, name, ping, status, quality_score, ai_score, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (
                config.get('protocol'),
                config.get('uri'),
                config.get('name'),
                config.get('ping'),
                config.get('status'),
                config.get('quality', {}).get('score', 0),
                config.get('ai_score', 0)
            ))
            self.conn.commit()
        except Exception as e:
            print(f"Database error: {e}")

    def save_telegram_settings(self, bot_token, channel_id, message_template='default', auto_send=False):
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO telegram_settings 
                (id, bot_token, channel_id, message_template, auto_send)
                VALUES (1, ?, ?, ?, ?)
            ''', (bot_token, channel_id, message_template, auto_send))
            self.conn.commit()
        except Exception as e:
            print(f"Database error: {e}")

    def load_telegram_settings(self):
        try:
            cursor = self.conn.cursor()
            cursor.execute('SELECT bot_token, channel_id, message_template, auto_send FROM telegram_settings WHERE id = 1')
            result = cursor.fetchone()
            return result if result else (None, None, 'default', False)
        except:
            return (None, None, 'default', False)

    def save_app_settings(self, settings):
        try:
            cursor = self.conn.cursor()
            preferred_protocols = json.dumps(settings.get('preferred_protocols', []))
            cursor.execute('''
                INSERT OR REPLACE INTO app_settings 
                (id, auto_update_interval, max_configs, preferred_protocols)
                VALUES (1, ?, ?, ?)
            ''', (
                settings.get('auto_update_interval', 30),
                settings.get('max_configs', 500),
                preferred_protocols
            ))
            self.conn.commit()
        except Exception as e:
            print(f"Database error: {e}")

    def load_app_settings(self):
        try:
            cursor = self.conn.cursor()
            cursor.execute('SELECT auto_update_interval, max_configs, preferred_protocols FROM app_settings WHERE id = 1')
            result = cursor.fetchone()
            if result:
                return {
                    'auto_update_interval': result[0],
                    'max_configs': result[1],
                    'preferred_protocols': json.loads(result[2]) if result[2] else []
                }
        except:
            pass
        return {
            'auto_update_interval': 30,
            'max_configs': 500,
            'preferred_protocols': ['vless', 'trojan', 'vmess']
        }

class ExportManager:
    @staticmethod
    def export_to_format(configs, format_name, app_name):
        if format_name == "V2rayN":
            return ExportManager.export_v2rayn(configs)
        elif format_name == "Clash":
            return ExportManager.export_clash(configs, app_name)
        elif format_name == "Shadowrocket":
            return ExportManager.export_shadowrocket(configs)
        elif format_name == "Raw":
            return ExportManager.export_raw(configs)
        else:
            return "\n".join([cfg['uri'] for cfg in configs])

    @staticmethod
    def export_v2rayn(configs):
        return base64.b64encode(
            "\n".join([cfg['uri'] for cfg in configs]).encode()
        ).decode()

    @staticmethod
    def export_clash(configs, app_name):
        clash_config = {
            'proxies': [],
            'proxy-groups': [
                {
                    'name': 'Auto',
                    'type': 'url-test',
                    'proxies': [cfg['name'] for cfg in configs],
                    'url': 'http://www.gstatic.com/generate_204',
                    'interval': 300
                }
            ],
            'rules': [
                'GEOIP,CN,DIRECT',
                'MATCH,Auto'
            ]
        }
        
        for cfg in configs:
            proxy = {
                'name': cfg['name'],
                'type': cfg['protocol'],
                'server': cfg.get('ip', 'unknown'),
                'port': 443,
                'uuid': ExportManager._generate_uuid() if cfg['protocol'] in ['vmess', 'vless'] else '',
                'alterId': 0 if cfg['protocol'] == 'vmess' else None,
                'cipher': 'auto' if cfg['protocol'] == 'ss' else None
            }
            clash_config['proxies'].append(proxy)
        
        return yaml.dump(clash_config, allow_unicode=True)

    @staticmethod
    def _generate_uuid():
        return hashlib.md5(str(time.time()).encode()).hexdigest()[:8]

    @staticmethod
    def export_shadowrocket(configs):
        lines = ["[Proxy]"]
        for cfg in configs:
            lines.append(f"{cfg['protocol']} = {cfg['uri']}")
        lines.extend(["\n[Rule]", "FINAL,Proxy"])
        return "\n".join(lines)

    @staticmethod
    def export_raw(configs):
        return "\n".join([cfg['uri'] for cfg in configs])


class AdvancedV2rayManager:
    def __init__(self):
        self.root = ctk.CTk()
        self.root.title("PingRay - Professional Configuration Management")
        self.root.geometry("1200x820")
        self.root.minsize(1200, 700) 
        
        self.ai_manager = AIConfigManager()
        self.database = ConfigDatabase()
        self.export_manager = ExportManager()
        self.qr_generator = QRCodeGenerator()
        self.telegram_manager = EnhancedTelegramBotManager()
        self.auto_update_manager = AutoUpdateManager(self.auto_update_configs)
        
        self.setup_variables()
        self.setup_ui()
        self.load_settings()
        
    def setup_variables(self):
        self.current_tab = "V2ray"
        self.configs = []
        self.settings = self.database.load_app_settings()
        self.settings.update({
            'github_search': True,
            'ai_filtering': True,
            'real_delay_testing': True
        })

    def setup_ui(self):
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(1, weight=1)
        
        self.create_sidebar()
        self.create_main_area()
        self.create_status_bar()
        self.setup_context_menu()

    def setup_context_menu(self):
        self.context_menu = tk.Menu(self.root, tearoff=0, bg='#2d2d2d', fg='white')
        self.context_menu.add_command(label="Copy Config Link", command=self.copy_selected_config)
        self.context_menu.add_command(label="Generate QR Code", command=self.generate_qr_for_selected)
        self.context_menu.add_separator()
        
        export_menu = tk.Menu(self.context_menu, tearoff=0, bg='#2d2d2d', fg='white')
        for app_name in EXPORT_FORMATS.keys():
            export_menu.add_command(
                label=f"Export for {app_name}", 
                command=lambda app=app_name: self.export_selected_config(app)
            )
        self.context_menu.add_cascade(label="Export For", menu=export_menu)
        
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Send to Telegram", command=self.send_to_telegram)
        self.context_menu.add_command(label="Edit Remark", command=self.edit_remark)
        self.context_menu.add_command(label="Copy Channel ID", command=self.copy_channel_id)
        
        self.tree.bind("<Button-3>", self.show_context_menu)

    def show_context_menu(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            self.context_menu.post(event.x_root, event.y_root)

    def create_sidebar(self):
        self.sidebar = ctk.CTkFrame(self.root, width=280, fg_color=COLORS['sidebar'])
        self.sidebar.grid(row=0, column=0, sticky="nswe")
        self.sidebar.grid_propagate(False)
        
        title_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        title_frame.pack(pady=(30, 20), padx=20, fill="x")
        
        ctk.CTkLabel(
            title_frame, 
            text="PingRay", 
            font=ctk.CTkFont(size=24, weight="bold"), 
            text_color=COLORS['primary']
        ).pack(side="left")
        
        ctk.CTkLabel(
            title_frame, 
            text="V1", 
            font=ctk.CTkFont(size=24)
        ).pack(side="left", padx=(5, 0))
        
        self.create_sidebar_tabs()
        
        self.auto_update_status = ctk.CTkLabel(
            self.sidebar,
            text="Auto-Update: OFF",
            text_color=COLORS['text-secondary'],
            font=ctk.CTkFont(size=12)
        )
        self.auto_update_status.pack(side="bottom", pady=10)
        
        ctk.CTkButton(
            self.sidebar,
            text="🔍 Advanced GitHub Search",
            command=self.start_github_search,
            height=40,
            fg_color=COLORS['info'],
            hover_color=COLORS['primary-hover']
        ).pack(side="bottom", pady=20, padx=15, fill="x")

    def create_sidebar_tabs(self):
        tabs = [
            ("V2ray", "🌐"),
            ("Telegram", "📱"),
            ("Settings", "⚙️"),
            ("Export", "📤"),
            ("Import", "📥"),
            ("AI Analysis", "🤖")
        ]
        
        self.sidebar_buttons = {}
        
        for tab_name, icon in tabs:
            btn = ctk.CTkButton(
                self.sidebar,
                text=f"{icon} {tab_name}",
                anchor="w",
                height=45,
                fg_color="transparent",
                hover_color=COLORS['primary-hover'],
                font=ctk.CTkFont(size=15),
                command=lambda tn=tab_name: self.switch_tab(tn)
            )
            btn.pack(fill="x", padx=15, pady=3)
            self.sidebar_buttons[tab_name] = btn

    def create_main_area(self):
        self.main_frame = ctk.CTkFrame(self.root, fg_color=COLORS['background'])
        self.main_frame.grid(row=0, column=1, sticky="nswe")
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(1, weight=1)
        
        self.tab_views = {}
        self.create_v2ray_tab()
        self.create_telegram_tab()
        self.create_settings_tab()
        self.create_export_tab()
        self.create_import_tab()
        self.create_ai_tab()
        
        self.show_tab("V2ray")

    def create_v2ray_tab(self):
        frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        
        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=20)
        
        ctk.CTkLabel(
            header,
            text="V2Ray Configuration Management",
            font=ctk.CTkFont(size=22, weight="bold")
        ).pack(side="left")
        
        controls = ctk.CTkFrame(header, fg_color="transparent")
        controls.pack(side="right")
        
        ctk.CTkButton(
            controls,
            text="Update Configs",
            command=self.update_configs
        ).pack(side="left", padx=5)
        
        ctk.CTkButton(
            controls,
            text="Test All",
            command=self.test_all_configs,
            fg_color=COLORS['danger'],
            hover_color='#ff6666'
        ).pack(side="left", padx=5)
        
        self.auto_update_btn = ctk.CTkButton(
            controls,
            text="🔄 Auto: OFF",
            command=self.toggle_auto_update,
            fg_color=COLORS['warning'],
            hover_color='#e6a022',
            width=100
        )
        self.auto_update_btn.pack(side="left", padx=5)
        
        self.create_configs_table(frame)
        
        self.tab_views["V2ray"] = frame

    def create_telegram_tab(self):
        frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        
        ctk.CTkLabel(
            frame,
            text="Enhanced Telegram Bot Integration",
            font=ctk.CTkFont(size=22, weight="bold")
        ).pack(pady=20)
        
        settings_frame = ctk.CTkFrame(frame, fg_color=COLORS['card'])
        settings_frame.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(
            settings_frame,
            text="Step 1: Bot Configuration",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", padx=15, pady=10)
        
        token_frame = ctk.CTkFrame(settings_frame, fg_color="transparent")
        token_frame.pack(fill="x", padx=15, pady=5)
        
        ctk.CTkLabel(token_frame, text="Bot Token:").pack(side="left")
        
        self.bot_token_entry = ctk.CTkEntry(token_frame, placeholder_text="1234567890:ABCdefGHIjklMNopqrstUVwxyz", show="*")
        self.bot_token_entry.pack(side="left", fill="x", expand=True, padx=(10, 5))
        
        self.token_visible = False
        ctk.CTkButton(
            token_frame,
            text="👁",
            command=self.toggle_token_visibility,
            width=40
        ).pack(side="right")
        
        channel_frame = ctk.CTkFrame(settings_frame, fg_color="transparent")
        channel_frame.pack(fill="x", padx=15, pady=5)
        
        ctk.CTkLabel(channel_frame, text="Channel ID:").pack(side="left")
        
        self.channel_id_entry = ctk.CTkEntry(channel_frame, placeholder_text="@channelname or -1001234567890")
        self.channel_id_entry.pack(side="left", fill="x", expand=True, padx=(10, 5))
        
        ctk.CTkButton(
            channel_frame,
            text="📋",
            command=self.copy_channel_id,
            width=40
        ).pack(side="right")
        
        help_label = ctk.CTkLabel(
            settings_frame, 
            text="💡 For public channels: @channelname\n💡 For private channels: -1001234567890 (get from @userinfobot)",
            text_color=COLORS['text-secondary'],
            font=ctk.CTkFont(size=12)
        )
        help_label.pack(anchor="w", padx=15, pady=5)
        
        connect_frame = ctk.CTkFrame(settings_frame, fg_color="transparent")
        connect_frame.pack(fill="x", padx=15, pady=10)
        
        ctk.CTkButton(
            connect_frame,
            text="🔗 Connect Bot",
            command=self.connect_telegram_bot,
            fg_color=COLORS['telegram'],
            hover_color='#007ab3'
        ).pack(side="left", padx=5)
        
        ctk.CTkButton(
            connect_frame,
            text="🧪 Test Connection",
            command=self.test_telegram_connection,
            fg_color=COLORS['info'],
            hover_color='#469fff'
        ).pack(side="left", padx=5)
        
        ctk.CTkButton(
            connect_frame,
            text="💾 Save Settings",
            command=self.save_telegram_settings,
            fg_color=COLORS['success']
        ).pack(side="left", padx=5)
        
        self.telegram_status_label = ctk.CTkLabel(
            settings_frame, 
            text="🔴 Not connected", 
            text_color=COLORS['danger'],
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.telegram_status_label.pack(anchor="w", padx=15, pady=10)
        
        message_frame = ctk.CTkFrame(frame, fg_color=COLORS['card'])
        message_frame.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(
            message_frame,
            text="Step 2: Message Configuration",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", padx=15, pady=10)
        
        ctk.CTkLabel(message_frame, text="Message Template:").pack(anchor="w", padx=15, pady=5)
        self.message_template = ctk.StringVar(value="default")
        
        template_frame = ctk.CTkFrame(message_frame, fg_color="transparent")
        template_frame.pack(fill="x", padx=15, pady=5)
        
        templates = [
            ("default", "Default"),
            ("premium", "Premium"), 
            ("simple", "Simple")
        ]
        
        for template_key, template_name in templates:
            ctk.CTkRadioButton(
                template_frame,
                text=template_name,
                variable=self.message_template,
                value=template_key
            ).pack(side="left", padx=10)
        
        ctk.CTkLabel(message_frame, text="Additional Text (optional):").pack(anchor="w", padx=15, pady=5)
        self.additional_text_entry = ctk.CTkEntry(
            message_frame, 
            placeholder_text="Extra message to include with each configuration"
        )
        self.additional_text_entry.pack(fill="x", padx=15, pady=5)
        
        send_frame = ctk.CTkFrame(frame, fg_color=COLORS['card'])
        send_frame.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(
            send_frame,
            text="Step 3: Send Configuration",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", padx=15, pady=10)
        
        send_buttons_frame = ctk.CTkFrame(send_frame, fg_color="transparent")
        send_buttons_frame.pack(fill="x", padx=15, pady=10)
        
        ctk.CTkButton(
            send_buttons_frame,
            text="📤 Send Test Message",
            command=self.send_test_message,
            fg_color=COLORS['warning'],
            height=40
        ).pack(side="left", padx=5)
        
        ctk.CTkButton(
            send_buttons_frame,
            text="📢 Send Sample Config",
            command=self.send_sample_config,
            fg_color=COLORS['telegram'],
            height=40
        ).pack(side="left", padx=5)
        
        ctk.CTkButton(
            send_buttons_frame,
            text="🚀 Broadcast All Active",
            command=self.broadcast_to_telegram,
            fg_color=COLORS['success'],
            height=40
        ).pack(side="left", padx=5)
        
        self.tab_views["Telegram"] = frame

    def create_settings_tab(self):
        frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        
        ctk.CTkLabel(
            frame,
            text="Application Settings",
            font=ctk.CTkFont(size=22, weight="bold")
        ).pack(pady=20)
        
        update_frame = ctk.CTkFrame(frame, fg_color=COLORS['card'])
        update_frame.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(
            update_frame,
            text="Auto-Update Settings",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", padx=15, pady=10)
        
        ctk.CTkLabel(update_frame, text="Update Interval (minutes):").pack(anchor="w", padx=15, pady=5)
        self.update_interval_var = ctk.StringVar(value=str(self.settings['auto_update_interval']))
        interval_entry = ctk.CTkEntry(update_frame, textvariable=self.update_interval_var)
        interval_entry.pack(fill="x", padx=15, pady=5)
        
        ctk.CTkButton(
            update_frame,
            text="Apply Interval",
            command=self.apply_update_interval
        ).pack(anchor="w", padx=15, pady=10)
        
        search_frame = ctk.CTkFrame(frame, fg_color=COLORS['card'])
        search_frame.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(
            search_frame,
            text="Search Settings",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", padx=15, pady=10)
        
        ctk.CTkLabel(search_frame, text="Max Configurations:").pack(anchor="w", padx=15, pady=5)
        self.max_configs_var = ctk.StringVar(value=str(self.settings['max_configs']))
        ctk.CTkEntry(
            search_frame,
            textvariable=self.max_configs_var,
            placeholder_text="Maximum configs to fetch"
        ).pack(fill="x", padx=15, pady=5)
        
        protocol_frame = ctk.CTkFrame(frame, fg_color=COLORS['card'])
        protocol_frame.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(
            protocol_frame,
            text="Preferred Protocols",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", padx=15, pady=10)
        
        self.protocol_vars = {}
        for protocol in SUPPORTED_PROTOCOLS:
            var = ctk.BooleanVar(value=protocol in self.settings['preferred_protocols'])
            cb = ctk.CTkCheckBox(
                protocol_frame,
                text=protocol.upper(),
                variable=var
            )
            cb.pack(anchor="w", padx=15, pady=2)
            self.protocol_vars[protocol] = var
        
        ctk.CTkButton(
            frame,
            text="💾 Save All Settings",
            command=self.save_all_settings,
            height=40,
            fg_color=COLORS['success']
        ).pack(pady=20)
        
        self.tab_views["Settings"] = frame

    def create_export_tab(self):
        frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        
        ctk.CTkLabel(
            frame,
            text="Export Configurations",
            font=ctk.CTkFont(size=22, weight="bold")
        ).pack(pady=20)
        
        format_frame = ctk.CTkFrame(frame, fg_color=COLORS['card'])
        format_frame.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(
            format_frame,
            text="Export Format",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", padx=15, pady=10)
        
        self.export_format = ctk.StringVar(value="V2rayN")
        for fmt in EXPORT_FORMATS.keys():
            ctk.CTkRadioButton(
                format_frame,
                text=fmt,
                variable=self.export_format,
                value=fmt
            ).pack(anchor="w", padx=15, pady=5)
        
        ctk.CTkButton(
            frame,
            text="📤 Export Selected Configs",
            command=self.export_configs,
            height=40,
            fg_color=COLORS['success']
        ).pack(pady=20)
        
        self.tab_views["Export"] = frame

    def create_import_tab(self):
        frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        
        ctk.CTkLabel(
            frame,
            text="Import Configurations",
            font=ctk.CTkFont(size=22, weight="bold")
        ).pack(pady=20)
        
        ctk.CTkButton(
            frame,
            text="📁 Select Config File",
            command=self.import_from_file,
            height=40
        ).pack(pady=10)
        
        self.import_text = ctk.CTkTextbox(frame, height=200)
        self.import_text.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkButton(
            frame,
            text="➕ Add Text Configurations",
            command=self.import_from_text
        ).pack(pady=10)
        
        self.tab_views["Import"] = frame

    def create_ai_tab(self):
        frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        
        ctk.CTkLabel(
            frame,
            text="AI Configuration Analysis",
            font=ctk.CTkFont(size=22, weight="bold")
        ).pack(pady=20)
        
        stats_frame = ctk.CTkFrame(frame, fg_color=COLORS['card'])
        stats_frame.pack(fill="x", padx=20, pady=10)
        
        self.stats_label = ctk.CTkLabel(
            stats_frame,
            text="Click 'Run AI Analysis' to see statistics",
            font=ctk.CTkFont(size=14)
        )
        self.stats_label.pack(padx=15, pady=15)
        
        ctk.CTkButton(
            frame,
            text="🤖 Run AI Analysis",
            command=self.run_ai_analysis,
            height=40,
            fg_color=COLORS['accent']
        ).pack(pady=20)
        
        self.tab_views["AI Analysis"] = frame

    def create_configs_table(self, parent):
        table_frame = ctk.CTkFrame(parent, fg_color="transparent")
        table_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        columns = ("#", "Protocol", "Name", "Real Delay", "Quality", "AI Score", "Status", "Actions")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=20)
        
        column_widths = [50, 80, 250, 100, 80, 80, 100, 100]
        for col, width in zip(columns, column_widths):
            self.tree.heading(col, text=col)
            self.tree.column(col, width=width, anchor="center")
        
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        self.tree.bind("<Double-1>", self.on_config_double_click)

    def create_status_bar(self):
        self.status_bar = ctk.CTkFrame(self.root, height=30, fg_color=COLORS['sidebar'])
        self.status_bar.grid(row=1, column=0, columnspan=2, sticky="ew")
        
        self.status_label = ctk.CTkLabel(
            self.status_bar,
            text="Ready - Auto-Update: OFF",
            text_color=COLORS['text-secondary']
        )
        self.status_label.pack(side="left", padx=10, pady=5)
        
        self.progress_bar = ctk.CTkProgressBar(self.status_bar, height=4)
        self.progress_bar.pack(side="right", padx=10, pady=5)
        self.progress_bar.set(0)

    def show_tab(self, tab_name):
        for name, frame in self.tab_views.items():
            if name == tab_name:
                frame.pack(fill="both", expand=True)
                self.sidebar_buttons[name].configure(fg_color=COLORS['primary'])
            else:
                frame.pack_forget()
                self.sidebar_buttons[name].configure(fg_color="transparent")
        self.current_tab = tab_name

    def switch_tab(self, tab_name):
        self.show_tab(tab_name)

    def start_github_search(self):
        threading.Thread(target=self._update_configs_thread, daemon=True).start()

    def update_configs(self):
        threading.Thread(target=self._update_configs_thread, daemon=True).start()

    def _update_configs_thread(self):
        self.set_status("Fetching configurations...")
        self.progress_bar.set(0)
        
        max_configs = self.settings.get('max_configs', 500)
        configs = self.ai_manager.hunter.fetch_configs_from_sources(max_configs)
        
        if not configs:
            self.root.after(0, lambda: messagebox.showwarning("Warning", "No configurations found"))
            self.root.after(0, lambda: self.set_status("No configurations found"))
            return
        
        self.configs = []
        total = len(configs)
        
        for i, config in enumerate(configs):
            test_result = self.ai_manager.tester.test_config(config)
            config_data = {
                'uri': config,
                'protocol': test_result.get('protocol', 'Unknown'),
                'name': self.ai_manager.hunter.generate_config_name(config),
                'ping': test_result.get('ping', None),
                'status': test_result.get('status', 'Unknown'),
                'quality': test_result.get('quality', {}),
                'ai_score': 0
            }
            
            if self.settings.get('ai_filtering', True):
                config_data = self.ai_manager.smart_config_filter([config_data], self.settings)[0]
            
            self.configs.append(config_data)
            self.database.save_config(config_data)
            
            progress = (i + 1) / total
            self.root.after(0, lambda: self.progress_bar.set(progress))
        
        self.root.after(0, self.update_config_table)
        self.root.after(0, lambda: self.set_status(f"Fetched {len(self.configs)} configurations"))

    def test_all_configs(self):
        if not self.configs:
            messagebox.showwarning("Warning", "No configurations to test")
            return
        
        threading.Thread(target=self._test_all_configs_thread, daemon=True).start()

    def _test_all_configs_thread(self):
        self.set_status("Testing all configurations...")
        self.progress_bar.set(0)
        
        total = len(self.configs)
        for i, config in enumerate(self.configs):
            test_result = self.ai_manager.tester.test_config(config['uri'])
            config.update({
                'ping': test_result.get('ping', None),
                'status': test_result.get('status', 'Unknown'),
                'quality': test_result.get('quality', {}),
                'ip': test_result.get('ip', config.get('ip', 'Unknown'))
            })
            
            if self.settings.get('ai_filtering', True):
                config_data = self.ai_manager.smart_config_filter([config], self.settings)[0]
                config.update({'ai_score': config_data['ai_score']})
            
            self.database.save_config(config)
            
            progress = (i + 1) / total
            self.root.after(0, lambda: self.progress_bar.set(progress))
        
        self.root.after(0, self.update_config_table)
        self.root.after(0, lambda: self.set_status("Testing completed"))

    def update_config_table(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        for i, config in enumerate(self.configs):
            self.tree.insert("", "end", values=(
                i + 1,
                config['protocol'].upper(),
                config['name'],
                config['ping'] if config['ping'] else "N/A",
                config['quality'].get('grade', 'N/A'),
                config['ai_score'],
                config['status'],
                "View"
            ))

    def copy_selected_config(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "Please select a configuration")
            return
        
        item = self.tree.item(selected[0])
        config_index = int(item['values'][0]) - 1
        config_uri = self.configs[config_index]['uri']
        
        self.root.clipboard_clear()
        self.root.clipboard_append(config_uri)
        messagebox.showinfo("Copied", "Configuration copied to clipboard!")

    def generate_qr_for_selected(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "Please select a configuration")
            return
        
        item = self.tree.item(selected[0])
        config_index = int(item['values'][0]) - 1
        config_uri = self.configs[config_index]['uri']
        
        qr_image = self.qr_generator.generate_qr_code(config_uri)
        if qr_image:
            qr_window = ctk.CTkToplevel(self.root)
            qr_window.title("Configuration QR Code")
            qr_window.geometry("350x350")
            
            qr_photo = ImageTk.PhotoImage(qr_image)
            ctk.CTkLabel(qr_window, image=qr_photo, text="").pack(pady=10)
            qr_window.image = qr_photo  
            
            ctk.CTkButton(
                qr_window,
                text="Save QR Code",
                command=lambda: self.save_qr_code(qr_image)
            ).pack(pady=10)

    def save_qr_code(self, qr_image):
        file_path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG files", "*.png")]
        )
        if file_path:
            qr_image.save(file_path)
            messagebox.showinfo("Success", "QR Code saved successfully")

    def export_configs(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "Please select at least one configuration")
            return
        
        format_name = self.export_format.get()
        file_path = filedialog.asksaveasfilename(
            defaultextension=EXPORT_FORMATS[format_name]["extension"],
            filetypes=[(f"{format_name} files", EXPORT_FORMATS[format_name]["extension"])]
        )
        if not file_path:
            return
        
        selected_configs = []
        for item in selected:
            config_index = int(self.tree.item(item)['values'][0]) - 1
            selected_configs.append(self.configs[config_index])
        
        exported_content = self.export_manager.export_to_format(selected_configs, format_name, format_name)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(exported_content)
        
        messagebox.showinfo("Success", f"Exported {len(selected_configs)} configurations to {file_path}")

    def export_selected_config(self, app_name):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "Please select a configuration")
            return
        
        file_path = filedialog.asksaveasfilename(
            defaultextension=EXPORT_FORMATS[app_name]["extension"],
            filetypes=[(f"{app_name} files", EXPORT_FORMATS[app_name]["extension"])]
        )
        if not file_path:
            return
        
        item = self.tree.item(selected[0])
        config_index = int(item['values'][0]) - 1
        config = [self.configs[config_index]]
        
        exported_content = self.export_manager.export_to_format(config, app_name, app_name)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(exported_content)
        
        messagebox.showinfo("Success", f"Exported configuration to {file_path}")

    def import_from_file(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("Text files", "*.txt"), ("YAML files", "*.yml"), ("All files", "*.*")]
        )
        if not file_path:
            return
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            configs = self.ai_manager.hunter.extract_configs_from_text(content)
            if not configs:
                messagebox.showwarning("Warning", "No valid configurations found in file")
                return
            
            self.process_imported_configs(configs)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to import configurations: {str(e)}")

    def import_from_text(self):
        text = self.import_text.get("1.0", tk.END).strip()
        if not text:
            messagebox.showwarning("Warning", "No configurations entered")
            return
        
        configs = self.ai_manager.hunter.extract_configs_from_text(text)
        if not configs:
            messagebox.showwarning("Warning", "No valid configurations found in text")
            return
        
        self.process_imported_configs(configs)

    def process_imported_configs(self, configs):
        threading.Thread(target=self._process_imported_configs_thread, args=(configs,), daemon=True).start()

    def _process_imported_configs_thread(self, configs):
        self.set_status("Processing imported configurations...")
        self.progress_bar.set(0)
        
        total = len(configs)
        for i, config in enumerate(configs):
            test_result = self.ai_manager.tester.test_config(config)
            config_data = {
                'uri': config,
                'protocol': test_result.get('protocol', 'Unknown'),
                'name': self.ai_manager.hunter.generate_config_name(config),
                'ping': test_result.get('ping', None),
                'status': test_result.get('status', 'Unknown'),
                'quality': test_result.get('quality', {}),
                'ai_score': 0,
                'ip': test_result.get('ip', 'Unknown')
            }
            
            if self.settings.get('ai_filtering', True):
                config_data = self.ai_manager.smart_config_filter([config_data], self.settings)[0]
            
            self.configs.append(config_data)
            self.database.save_config(config_data)
            
            progress = (i + 1) / total
            self.root.after(0, lambda: self.progress_bar.set(progress))
        
        self.root.after(0, self.update_config_table)
        self.root.after(0, lambda: self.set_status(f"Imported {len(configs)} configurations"))

    def run_ai_analysis(self):
        if not self.configs:
            messagebox.showwarning("Warning", "No configurations to analyze")
            return
        
        total_configs = len(self.configs)
        active_configs = len([c for c in self.configs if c['status'] == "Active"])
        avg_ping = sum(c['ping'] for c in self.configs if c['ping']) / (active_configs or 1)
        protocol_counts = {}
        for config in self.configs:
            protocol = config['protocol']
            protocol_counts[protocol] = protocol_counts.get(protocol, 0) + 1
        
        stats_text = (
            f"Total Configurations: {total_configs}\n"
            f"Active Configurations: {active_configs}\n"
            f"Average Ping: {round(avg_ping, 1)}ms\n"
            f"Protocol Distribution:\n"
        )
        for protocol, count in protocol_counts.items():
            stats_text += f"  {protocol.upper()}: {count}\n"
        
        self.stats_label.configure(text=stats_text)

    def on_config_double_click(self, event):
        selected = self.tree.selection()
        if not selected:
            return
        
        item = self.tree.item(selected[0])
        config_index = int(item['values'][0]) - 1
        config = self.configs[config_index]
        
        details_window = ctk.CTkToplevel(self.root)
        details_window.title("Configuration Details")
        details_window.geometry("600x400")
        
        ctk.CTkLabel(
            details_window,
            text=f"Configuration: {config['name']}",
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(pady=10)
        
        details_text = (
            f"Protocol: {config['protocol'].upper()}\n"
            f"Ping: {config['ping'] if config['ping'] else 'N/A'}ms\n"
            f"Status: {config['status']}\n"
            f"Quality: {config['quality'].get('grade', 'N/A')}\n"
            f"AI Score: {config['ai_score']}\n"
            f"IP: {config.get('ip', 'Unknown')}\n\n"
            f"URI:\n{config['uri']}"
        )
        
        ctk.CTkTextbox(
            details_window,
            height=200,
            width=500,
            font=ctk.CTkFont(size=14)
        ).pack(pady=10)
        
        textbox = details_window.winfo_children()[-1]
        textbox.insert("0.0", details_text)
        textbox.configure(state="disabled")
        
        ctk.CTkButton(
            details_window,
            text="Copy Config",
            command=lambda: self.root.clipboard_append(config['uri'])
        ).pack(pady=10)
        
        qr_image = self.qr_generator.generate_qr_code(config['uri'])
        if qr_image:
            qr_photo = ImageTk.PhotoImage(qr_image)
            ctk.CTkLabel(details_window, image=qr_photo, text="").pack(pady=10)
            details_window.image = qr_photo 

    def toggle_auto_update(self):
        if self.auto_update_manager.is_running:
            self.auto_update_manager.stop_auto_update()
            self.auto_update_btn.configure(text="🔄 Auto: OFF")
            self.auto_update_status.configure(text="Auto-Update: OFF")
            self.set_status("Auto-update disabled")
        else:
            interval = self.settings.get('auto_update_interval', 30)
            self.auto_update_manager.start_auto_update(interval)
            self.auto_update_btn.configure(text="🔄 Auto: ON")
            self.auto_update_status.configure(text="Auto-Update: ON")
            self.set_status(f"Auto-update enabled ({interval} minutes)")

    def apply_update_interval(self):
        try:
            interval = int(self.update_interval_var.get())
            if interval < 1:
                messagebox.showwarning("Warning", "Interval must be at least 1 minute")
                return
            self.settings['auto_update_interval'] = interval
            self.database.save_app_settings(self.settings)
            self.auto_update_manager.set_interval(interval)
            if self.auto_update_manager.is_running:
                self.auto_update_manager.stop_auto_update()
                self.auto_update_manager.start_auto_update(interval)
            messagebox.showinfo("Success", f"Update interval set to {interval} minutes")
        except ValueError:
            messagebox.showerror("Error", "Please enter a valid number")

    def save_all_settings(self):
        try:
            max_configs = int(self.max_configs_var.get())
            if max_configs < 1:
                messagebox.showwarning("Warning", "Max configurations must be at least 1")
                return
            
            preferred_protocols = [
                proto for proto, var in self.protocol_vars.items() if var.get()
            ]
            
            self.settings.update({
                'auto_update_interval': int(self.update_interval_var.get()),
                'max_configs': max_configs,
                'preferred_protocols': preferred_protocols
            })
            
            self.database.save_app_settings(self.settings)
            messagebox.showinfo("Success", "Settings saved successfully")
        except ValueError:
            messagebox.showerror("Error", "Please enter valid numbers for settings")

    def edit_remark(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "Please select a configuration")
            return
        
        item = self.tree.item(selected[0])
        config_index = int(item['values'][0]) - 1
        config = self.configs[config_index]
        
        new_remark = ctk.CTkInputDialog(
            title="Edit Remark",
            text=f"Enter new remark for {config['name']}:"
        ).get_input()
        
        if new_remark:
            config['name'] = new_remark
            if '#' in config['uri']:
                config['uri'] = config['uri'].split('#')[0] + f'#{new_remark}'
            else:
                config['uri'] = config['uri'] + f'#{new_remark}'
            self.database.save_config(config)
            self.update_config_table()
            messagebox.showinfo("Success", "Remark updated successfully")

    def save_telegram_settings(self):
        bot_token = self.bot_token_entry.get().strip()
        channel_id = self.channel_id_entry.get().strip()
        message_template = self.message_template.get()
        
        if not bot_token or not channel_id:
            messagebox.showwarning("Warning", "Please enter both bot token and channel ID")
            return
        
        self.database.save_telegram_settings(bot_token, channel_id, message_template)
        messagebox.showinfo("Success", "Telegram settings saved successfully")

    def toggle_token_visibility(self):
        if self.token_visible:
            self.bot_token_entry.configure(show="*")
            self.token_visible = False
        else:
            self.bot_token_entry.configure(show="")
            self.token_visible = True

    def copy_channel_id(self):
        channel_id = self.channel_id_entry.get().strip()
        if channel_id:
            self.root.clipboard_clear()
            self.root.clipboard_append(channel_id)
            messagebox.showinfo("Copied", "Channel ID copied to clipboard!")

    def connect_telegram_bot(self):
        bot_token = self.bot_token_entry.get().strip()
        if not bot_token:
            messagebox.showwarning("Warning", "Please enter bot token")
            return
        
        threading.Thread(
            target=self._connect_telegram_bot_thread,
            args=(bot_token,),
            daemon=True
        ).start()

    def _connect_telegram_bot_thread(self, bot_token):
        success, message = self.telegram_manager.connect_bot(bot_token)
        self.root.after(0, lambda: self._update_connection_status(success, message))

    def _update_connection_status(self, success, message):
        if success:
            self.telegram_status_label.configure(
                text=message,
                text_color=COLORS['success']
            )
        else:
            self.telegram_status_label.configure(
                text=message,
                text_color=COLORS['danger']
            )
        self.set_status(message)

    def test_telegram_connection(self):
        bot_token = self.bot_token_entry.get().strip()
        channel_id = self.channel_id_entry.get().strip()
        
        if not bot_token or not channel_id:
            messagebox.showwarning("Warning", "Please enter both bot token and channel ID")
            return
        
        threading.Thread(
            target=self._test_telegram_connection_thread,
            args=(bot_token, channel_id),
            daemon=True
        ).start()

    def _test_telegram_connection_thread(self, bot_token, channel_id):
        success, message = self.telegram_manager.test_connection(bot_token, channel_id)
        self.root.after(0, lambda: self._update_connection_status(success, message))

    def send_test_message(self):
        if not self.telegram_manager.is_connected:
            messagebox.showwarning("Warning", "Please connect to Telegram bot first")
            return
        
        channel_id = self.channel_id_entry.get().strip()
        if not channel_id:
            messagebox.showwarning("Warning", "Please enter channel ID")
            return
        
        threading.Thread(
            target=self._send_test_message_thread,
            args=(channel_id,),
            daemon=True
        ).start()

    def _send_test_message_thread(self, channel_id):
        try:
            self.telegram_manager.bot.send_message(
                channel_id,
                "🤖 *PingRay Test Message*\n\nThis is a test message from PingRay.",
                parse_mode='Markdown'
            )
            self.root.after(0, lambda: messagebox.showinfo("Success", "Test message sent successfully"))
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Error", f"Failed to send test message: {str(e)}"))

    def send_sample_config(self):
        if not self.telegram_manager.is_connected:
            messagebox.showwarning("Warning", "Please connect to Telegram bot first")
            return
        
        channel_id = self.channel_id_entry.get().strip()
        if not channel_id:
            messagebox.showwarning("Warning", "Please enter channel ID")
            return
        
        sample_config = {
            'uri': 'vless://sample-uuid@sample.com:443?security=tls&type=tcp#Sample-Config',
            'protocol': 'vless',
            'name': 'Sample Config',
            'ping': 100,
            'status': 'Active',
            'quality': {'grade': 'A', 'score': 90},
            'ip': 'sample.com'
        }
        
        threading.Thread(
            target=self._send_sample_config_thread,
            args=(channel_id, sample_config),
            daemon=True
        ).start()

    def _send_sample_config_thread(self, channel_id, config):
        try:
            additional_text = self.additional_text_entry.get().strip()
            template = self.message_template.get()
            success, message = self.telegram_manager.send_config_to_channel(
                channel_id, config, config['name'], template, additional_text
            )
            self.root.after(0, lambda: messagebox.showinfo("Send Config", message))
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Error", f"Failed to send: {str(e)}"))

    def send_to_telegram(self):
        if not self.telegram_manager.is_connected:
            messagebox.showwarning("Warning", "Please connect to Telegram bot first")
            return
        
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "Please select a configuration")
            return
        
        channel_id = self.channel_id_entry.get().strip()
        if not channel_id:
            messagebox.showwarning("Warning", "Please enter channel ID")
            return
        
        item = self.tree.item(selected[0])
        config_index = int(item['values'][0]) - 1
        config = self.configs[config_index]
        
        threading.Thread(
            target=self._send_to_telegram_thread,
            args=(channel_id, config),
            daemon=True
        ).start()

    def _send_to_telegram_thread(self, channel_id, config):
        try:
            additional_text = self.additional_text_entry.get().strip()
            template = self.message_template.get()
            success, message = self.telegram_manager.send_config_to_channel(
                channel_id, config, config['name'], template, additional_text
            )
            self.root.after(0, lambda: messagebox.showinfo("Send Config", message))
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Error", f"Failed to send: {str(e)}"))

    def broadcast_to_telegram(self):
        if not self.telegram_manager.is_connected:
            messagebox.showwarning("Warning", "Please connect to Telegram bot first")
            return
        
        channel_id = self.channel_id_entry.get().strip()
        if not channel_id:
            messagebox.showwarning("Warning", "Please enter channel ID")
            return
        
        active_configs = [cfg for cfg in self.configs if cfg.get('status') == "Active"]
        if not active_configs:
            messagebox.showwarning("Warning", "No active configurations to broadcast")
            return
        
        threading.Thread(
            target=self._broadcast_to_telegram_thread,
            args=(active_configs,),
            daemon=True
        ).start()

    def _broadcast_to_telegram_thread(self, configs):
        self.set_status(f"Broadcasting {len(configs)} configurations to Telegram...")
        channel_id = self.channel_id_entry.get().strip()
        template = self.message_template.get()
        additional_text = self.additional_text_entry.get().strip()
        
        success_count = 0
        for i, config in enumerate(configs):
            try:
                success, message = self.telegram_manager.send_config_to_channel(
                    channel_id, config, config['name'], template, additional_text
                )
                
                if success:
                    success_count += 1
                
                progress = (i + 1) / len(configs)
                self.root.after(0, lambda: self.progress_bar.set(progress))
                
                if i < len(configs) - 1:
                    time.sleep(2)  
            except Exception as e:
                print(f"Error sending config {i+1}: {e}")
        
        self.root.after(0, lambda: messagebox.showinfo(
            "Broadcast Complete", 
            f"Successfully sent {success_count}/{len(configs)} configurations"
        ))
        self.root.after(0, lambda: self.set_status("Broadcast completed"))

    def auto_update_configs(self):
        self.update_configs()

    def load_settings(self):
        bot_token, channel_id, message_template, auto_send = self.database.load_telegram_settings()
        if bot_token:
            self.bot_token_entry.insert(0, bot_token)
        if channel_id:
            self.channel_id_entry.insert(0, channel_id)
        self.message_template.set(message_template)
        
        if auto_send and bot_token:
            threading.Thread(
                target=self._connect_telegram_bot_thread,
                args=(bot_token,),
                daemon=True
            ).start()

    def set_status(self, message):
        self.status_label.configure(text=message)
        self.progress_bar.set(0)

if __name__ == "__main__":
    app = AdvancedV2rayManager()
    app.root.mainloop()