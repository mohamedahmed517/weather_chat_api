# app.py
import os
import re
import requests
from flask_cors import CORS # type: ignore
import google.generativeai as genai
from datetime import date, timedelta
from flask import Flask, request, jsonify

app = Flask(__name__)
CORS(app)

GEMINI_API_KEY = os.environ.get("AIzaSyDLZHwrN889sw8ZQawZd3XuKOUpiD8MLHI")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel('gemini-1.5-flash')
else:
    gemini_model = None
    print("تحذير: GEMINI_API_KEY غير موجود")

IPV4_PRIVATE = re.compile(r'^(127\.0\.0\.1|10\.|172\.(1[6-9]|2[0-9]|3[0-1])\.|192\.168\.)')

def is_private_ip(ip: str) -> bool:
    return bool(IPV4_PRIVATE.match(ip))

def get_user_ip() -> str:
    headers = ["CF-Connecting-IP", "True-Client-IP", "X-Real-IP", "X-Forwarded-For", "X-Client-IP", "Forwarded"]
    for h in headers:
        val = request.headers.get(h)
        if val:
            ips = [i.strip() for i in val.replace('"', '').split(",")]
            for ip in ips:
                if ip and not is_private_ip(ip):
                    return ip
    return request.remote_addr or "127.0.0.1"

def get_location(ip: str):
    try:
        r = requests.get(f"http://ip-api.com/json/{ip}?fields=city,lat,lon,timezone", timeout=8)
        r.raise_for_status()
        d = r.json()
        return {
            "city": d.get("city", "غير معروف"),
            "lat": d.get("lat"),
            "lon": d.get("lon"),
            "timezone": d.get("timezone", "Africa/Cairo")
        }
    except:
        return None

def fetch_weather(lat, lon, tz):
    start = date.today()
    end = start + timedelta(days=16)
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max,temperature_2m_min,precipitation_sum&start_date={start.isoformat()}&end_date={end.isoformat()}&timezone={tz}"
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        return r.json()["daily"]
    except:
        return None

def suggest_outfit(temp, rain):
    if rain > 2.0: return "مطر – خُد شمسية"
    if temp < 10: return "برد جدًا – جاكيت تقيل"
    if temp < 18: return "بارد – جاكيت خفيف"
    if temp < 26: return "معتدل – تيشيرت وجينز"
    if temp < 32: return "دافئ – تيشيرت خفيف"
    return "حر – شورت ومياه كتير"

@app.route("/")
def home():
    return jsonify({"message": "Weather Chat AI شغال!", "endpoint": "/api/chat"})

@app.route("/api/chat", methods=["POST"])
def chat():
    if not gemini_model:
        return jsonify({"error": "الدردشة غير مفعلة – مفتاح Gemini مفقود"}), 503

    try:
        user_message = request.json.get("message", "").strip()
        if not user_message:
            return jsonify({"error": "الرسالة فارغة"}), 400

        user_ip = get_user_ip()
        location = get_location(user_ip)
        if not location:
            return jsonify({"error": "لا يمكن تحديد موقعك"}), 400

        city = location["city"]
        weather_data = fetch_weather(location["lat"], location["lon"], location["timezone"])
        if not weather_data:
            return jsonify({"error": "لا يوجد بيانات طقس"}), 500

        today = date.today()
        forecast_lines = []
        for i in range(min(7, len(weather_data["time"]))):
            d = (today + timedelta(days=i)).strftime("%d-%m")
            t_max = weather_data["temperature_2m_max"][i]
            t_min = weather_data["temperature_2m_min"][i]
            temp = round((t_max + t_min) / 2, 1)
            rain = weather_data["precipitation_sum"][i]
            outfit = suggest_outfit(temp, rain)
            forecast_lines.append(f"{d}: {temp}°C – {outfit}")

        forecast_text = "\n".join(forecast_lines)

        prompt = f"""
أنت مساعد ذكي، ودود، ومصري أصيل.
المستخدم في: {city}
توقعات الطقس:
{forecast_text}

الرسالة: "{user_message}"
رد بطريقة طبيعية، ممتعة، ومفيدة. لا تذكر أنك AI.
"""

        ai_reply = gemini_model.generate_content(prompt).text.strip()

        return jsonify({
            "reply": ai_reply,
            "city": city,
            "type": "chat"
        })

    except Exception as e:
        return jsonify({"error": f"خطأ: {str(e)}"}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))

    app.run(host="0.0.0.0", port=port)
