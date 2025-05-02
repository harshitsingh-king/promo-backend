from flask import Flask, request, jsonify, session
from flask_cors import CORS
from bs4 import BeautifulSoup
import requests
import os

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  # Change this to a strong secret key
CORS(app, supports_credentials=True)

@app.route('/')
def hello_world():
    return "PromoGenie backend is running!"

@app.route('/login', methods=['POST'])
def login():
    try:
        user_id = request.headers.get('X-Replit-User-Id')
        if not user_id:
            return jsonify({'error': 'Not authenticated'}), 401

        session['user'] = {
            'id': user_id,
            'name': request.headers.get('X-Replit-User-Name')
        }
        return jsonify({'success': True})
    except KeyError:
        return jsonify({'error': 'Missing required headers'}), 400
    except Exception as e:
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@app.route('/get-codes', methods=['POST'])
def get_codes():
    try:
        if not request.is_json:
            return jsonify({"error": "Request must be JSON"}), 400

        data = request.json
        if not data or 'site' not in data:
            return jsonify({"error": "Missing 'site' parameter"}), 400

        site = data['site'].strip().replace("https://", "").replace("www.", "").split('/')[0]
        if not site:
            return jsonify({"error": "Invalid site URL"}), 400

        codes = []
        url = f"https://www.retailmenot.com/view/{site}"
        headers = {'User-Agent': 'Mozilla/5.0'}

        try:
            r = requests.get(url, headers=headers, timeout=10)
            r.raise_for_status()
        except requests.Timeout:
            return jsonify({"error": "Request timed out"}), 504
        except requests.RequestException as e:
            return jsonify({"error": f"Failed to fetch codes: {str(e)}"}), 502

        try:
            soup = BeautifulSoup(r.text, 'html.parser')
        except Exception:
            return jsonify({"error": "Failed to parse response"}), 500

        for tag in soup.select('[data-clipboard-text]'):
            try:
                code = tag['data-clipboard-text']
                if code and code not in codes:
                    codes.append(code)
            except (KeyError, AttributeError):
                continue

        if not codes:
            return jsonify({
                "site": site,
                "error": "No codes found for this site"
            }), 404

        return jsonify({
            "site": site,
            "codes_found": len(codes),
            "codes": codes
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))  # Required for Render
    app.run(host='0.0.0.0', port=port)
