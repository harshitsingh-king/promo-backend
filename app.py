from flask import Flask, request, jsonify
from flask_cors import CORS
from bs4 import BeautifulSoup
import requests
import os

app = Flask(__name__)
CORS(app)

@app.route('/')
def home():
    return "PromoGenie backend is running!"

@app.route('/get-codes', methods=['POST'])
def get_codes():
    try:
        data = request.get_json()
        if not data or 'site' not in data:
            return jsonify({"error": "Missing 'site' parameter"}), 400

        site = data['site'].strip().replace("https://", "").replace("www.", "").split('/')[0]
        search_url = f"https://www.couponbirds.com/codes/{site}"

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        }

        response = requests.get(search_url, headers=headers, timeout=10)
        if response.status_code != 200:
            return jsonify({"error": f"Failed to fetch: HTTP {response.status_code}"}), response.status_code

        soup = BeautifulSoup(response.text, 'html.parser')
        codes = []

        for div in soup.select('.code-list .code-item .code-text'):
            code = div.get_text(strip=True)
            if code and code not in codes:
                codes.append(code)

        if not codes:
            return jsonify({"site": site, "codes": [], "error": "No codes found"}), 404

        return jsonify({
            "site": site,
            "codes_found": len(codes),
            "codes": codes
        })
    except Exception as e:
        return jsonify({"error": f"Server error: {str(e)}"}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
