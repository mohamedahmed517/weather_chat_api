import os
import re
import requests
from datetime import date, timedelta
from flask import Flask, request, jsonify
from flask_cors import CORS # type: ignore

app = Flask(__name__)
CORS(app)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyCPlscgXwy6CtQ1Co_fUxuuIvZCNXQU_Qc")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"

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
        r = requests.get(f"https://ipwho.is/{ip}", timeout=8)
        r.raise_for_status()
        d = r.json()
        return {
            "city": d.get("city"),
            "lat": d.get("latitude"),
            "lon": d.get("longitude"),
            "timezone": d.get("timezone", {}).get("id", "Africa/Cairo")
        }
    except Exception as e:
        print(f"فشل تحديد الموقع: {e}")
        return None

# ====================== جلب الطقس ======================
def fetch_weather(lat, lon, tz):
    start = date.today()
    end = start + timedelta(days=16)
    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}"
        f"&daily=temperature_2m_max,temperature_2m_min,precipitation_sum"
        f"&start_date={start.isoformat()}&end_date={end.isoformat()}"
        f"&timezone=auto"
    )
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        return r.json()["daily"]
    except Exception as e:
        print(f"فشل جلب الطقس: {e}")
        return None

# ====================== نصيحة ملابس ======================
def suggest_outfit(temp, rain):
    if rain > 2.0: return "مطر – خُد شمسية"
    if temp < 10: return "برد جدًا – جاكيت تقيل"
    if temp < 18: return "بارد – جاكيت خفيف"
    if temp < 26: return "معتدل – تيشيرت وجينز"
    if temp < 32: return "دافئ – تيشيرت خفيف"
    return "حر – شورت ومياه كتير"

# ====================== استدعاء Gemini عبر REST ======================
def gemini_generate(prompt: str) -> str:
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.7,
            "topK": 40,
            "topP": 0.95,
            "maxOutputTokens": 1024
        }
    }
    try:
        r = requests.post(GEMINI_URL, json=payload, timeout=20)
        r.raise_for_status()
        data = r.json()
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        print(f"خطأ في Gemini: {e}")
        return "عذرًا، فيه مشكلة في الرد. حاول تاني!"

# ====================== Routes ======================
@app.route("/")
def home():
    return jsonify({"message": "Weather Chat AI شغال 100%!", "endpoint": "/api/chat"})

@app.route("/api/chat", methods=["POST"])
def chat():
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
أنت مساعد ذكي، ودود، ومصري أصيل. تتكلم بالعامية المصرية.
المستخدم في: {city}
توقعات الطقس:
{forecast_text}

الرسالة: "{user_message}"
رد بطريقة طبيعية، ممتعة، ومفيدة. لا تذكر أنك AI.
"""

        ai_reply = gemini_generate(prompt)

        return jsonify({
            "reply": ai_reply,
            "city": city,
            "type": "chat"
        })

    except Exception as e:
        print(f"خطأ عام: {e}")
        return jsonify({"error": "خطأ داخلي"}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)



