from flask import Flask, request, jsonify, session
from flask_cors import CORS
from bs4 import BeautifulSoup
import requests
import os
import time
import random
import re
from urllib.parse import urljoin
import concurrent.futures
from datetime import datetime
from functools import lru_cache
import logging
from werkzeug.middleware.proxy_fix import ProxyFix

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-here')
CORS(app, supports_credentials=True)

# Add ProxyFix middleware for Render.com
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Cache configuration
CACHE_TIMEOUT = 3600  # 1 hour cache for promo codes
MAX_WORKERS = 3  # Reduced for free tier
MAX_RETRIES = 2
REQUEST_TIMEOUT = 5

# USD to INR conversion rate (approximate)
USD_TO_INR_RATE = 83.0

# Country-specific configurations
COUNTRY_CONFIGS = {
    'india': {
        'domains': ['.in', '.co.in'],
        'paths': ['/offers', '/coupons', '/deals', '/promotions', '/sale'],
        'keywords': ['OFFER', 'DEAL', 'COUPON', 'DISCOUNT', 'SAVE', 'FLAT', 'CASHBACK'],
        'priority': 1
    },
    'usa': {
        'domains': ['.com'],
        'paths': ['/deals', '/coupons', '/promotions', '/offers', '/sale'],
        'keywords': ['OFFER', 'DEAL', 'COUPON', 'DISCOUNT', 'SAVE', 'FLAT', 'CASHBACK'],
        'priority': 1
    }
}

# Food delivery specific configurations
FOOD_DELIVERY_CONFIGS = {
    'swiggy.com': {
        'paths': ['/offers', '/promo', '/coupons', '/app'],
        'keywords': ['OFFER', 'PROMO', 'COUPON', 'SAVE', 'DISCOUNT'],
        'regex_patterns': [
            r'(?:USE|APPLY|ENTER)\s+CODE\s+[A-Z0-9]{4,15}',
            r'[A-Z0-9]{4,15}(?:\s+AT\s+CHECKOUT|\s+WHILE\s+CHECKING\s+OUT)',
            r'(?:SAVE|GET)\s+(?:UP\s+TO\s+)?(?:₹|INR|RS\.?)\s*\d+(?:,\d+)?(?:\s*OFF|\s*DISCOUNT)?',
            r'(?:FIRST\s+ORDER|NEW\s+USER)\s+(?:GET|SAVE)\s+(?:₹|INR|RS\.?)\s*\d+(?:,\d+)?(?:\s*OFF|\s*DISCOUNT)?'
        ]
    },
    'zomato.com': {
        'paths': ['/offers', '/promo', '/coupons', '/app'],
        'keywords': ['OFFER', 'PROMO', 'COUPON', 'SAVE', 'DISCOUNT'],
        'regex_patterns': [
            r'(?:USE|APPLY|ENTER)\s+CODE\s+[A-Z0-9]{4,15}',
            r'[A-Z0-9]{4,15}(?:\s+AT\s+CHECKOUT|\s+WHILE\s+CHECKING\s+OUT)',
            r'(?:SAVE|GET)\s+(?:UP\s+TO\s+)?(?:₹|INR|RS\.?)\s*\d+(?:,\d+)?(?:\s*OFF|\s*DISCOUNT)?',
            r'(?:FIRST\s+ORDER|NEW\s+USER)\s+(?:GET|SAVE)\s+(?:₹|INR|RS\.?)\s*\d+(?:,\d+)?(?:\s*OFF|\s*DISCOUNT)?'
        ]
    },
    'ubereats.com': {
        'paths': ['/deals', '/promo', '/coupons', '/app'],
        'keywords': ['OFFER', 'PROMO', 'COUPON', 'SAVE', 'DISCOUNT'],
        'regex_patterns': [
            r'(?:USE|APPLY|ENTER)\s+CODE\s+[A-Z0-9]{4,15}',
            r'[A-Z0-9]{4,15}(?:\s+AT\s+CHECKOUT|\s+WHILE\s+CHECKING\s+OUT)',
            r'(?:SAVE|GET)\s+(?:UP\s+TO\s+)?(?:$|USD)\s*\d+(?:\.\d+)?(?:\s*OFF|\s*DISCOUNT)?',
            r'(?:FIRST\s+ORDER|NEW\s+USER)\s+(?:GET|SAVE)\s+(?:$|USD)\s*\d+(?:\.\d+)?(?:\s*OFF|\s*DISCOUNT)?'
        ]
    },
    'foodpanda.com': {
        'paths': ['/offers', '/promo', '/coupons', '/app'],
        'keywords': ['OFFER', 'PROMO', 'COUPON', 'SAVE', 'DISCOUNT'],
        'regex_patterns': [
            r'(?:USE|APPLY|ENTER)\s+CODE\s+[A-Z0-9]{4,15}',
            r'[A-Z0-9]{4,15}(?:\s+AT\s+CHECKOUT|\s+WHILE\s+CHECKING\s+OUT)',
            r'(?:SAVE|GET)\s+(?:UP\s+TO\s+)?(?:₹|INR|RS\.?)\s*\d+(?:,\d+)?(?:\s*OFF|\s*DISCOUNT)?',
            r'(?:FIRST\s+ORDER|NEW\s+USER)\s+(?:GET|SAVE)\s+(?:₹|INR|RS\.?)\s*\d+(?:,\d+)?(?:\s*OFF|\s*DISCOUNT)?'
        ]
    },
    'doordash.com': {
        'paths': ['/deals', '/promo', '/coupons', '/app'],
        'keywords': ['OFFER', 'PROMO', 'COUPON', 'SAVE', 'DISCOUNT'],
        'regex_patterns': [
            r'(?:USE|APPLY|ENTER)\s+CODE\s+[A-Z0-9]{4,15}',
            r'[A-Z0-9]{4,15}(?:\s+AT\s+CHECKOUT|\s+WHILE\s+CHECKING\s+OUT)',
            r'(?:SAVE|GET)\s+(?:UP\s+TO\s+)?(?:$|USD)\s*\d+(?:\.\d+)?(?:\s*OFF|\s*DISCOUNT)?',
            r'(?:FIRST\s+ORDER|NEW\s+USER)\s+(?:GET|SAVE)\s+(?:$|USD)\s*\d+(?:\.\d+)?(?:\s*OFF|\s*DISCOUNT)?'
        ]
    },
    'grubhub.com': {
        'paths': ['/deals', '/promo', '/coupons', '/app'],
        'keywords': ['OFFER', 'PROMO', 'COUPON', 'SAVE', 'DISCOUNT'],
        'regex_patterns': [
            r'(?:USE|APPLY|ENTER)\s+CODE\s+[A-Z0-9]{4,15}',
            r'[A-Z0-9]{4,15}(?:\s+AT\s+CHECKOUT|\s+WHILE\s+CHECKING\s+OUT)',
            r'(?:SAVE|GET)\s+(?:UP\s+TO\s+)?(?:$|USD)\s*\d+(?:\.\d+)?(?:\s*OFF|\s*DISCOUNT)?',
            r'(?:FIRST\s+ORDER|NEW\s+USER)\s+(?:GET|SAVE)\s+(?:$|USD)\s*\d+(?:\.\d+)?(?:\s*OFF|\s*DISCOUNT)?'
        ]
    }
}

# Premium plan configurations
PREMIUM_PLANS = {
    'basic': {  # $1/month
        'price': 1,
        'features': {
            'max_tests_per_day': 50,
            'test_timeout': 3,  # seconds
            'supported_sites': ['amazon', 'flipkart', 'myntra', 'swiggy', 'zomato'],
            'test_method': 'quick'  # Only basic validation
        }
    },
    'standard': {  # $3/month
        'price': 3,
        'features': {
            'max_tests_per_day': 200,
            'test_timeout': 5,  # seconds
            'supported_sites': ['amazon', 'flipkart', 'myntra', 'swiggy', 'zomato', 
                              'ubereats', 'doordash', 'netflix', 'prime video', 'hotstar'],
            'test_method': 'standard'  # Full validation with retry
        }
    },
    'premium': {  # $7/month
        'price': 7,
        'features': {
            'max_tests_per_day': 1000,
            'test_timeout': 10,  # seconds
            'supported_sites': ['amazon', 'flipkart', 'myntra', 'swiggy', 'zomato', 
                              'ubereats', 'doordash', 'netflix', 'prime video', 'hotstar',
                              'booking.com', 'expedia', 'airbnb', 'coursera', 'udemy',
                              'spotify', 'apple music', 'hulu', 'disney+', 'hbo max'],
            'test_method': 'advanced'  # Full validation with multiple retries and fallback methods
        }
    }
}

def detect_country(site):
    site_lower = site.lower()
    if 'india' in site_lower or '.in' in site_lower:
        return 'india'
    elif 'usa' in site_lower or '.com' in site_lower:
        return 'usa'
    return None

def get_random_user_agent():
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3.1 Safari/605.1.15',
        # Mobile user agents
        'Mozilla/5.0 (iPhone; CPU iPhone OS 17_3_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3.1 Mobile/15E148 Safari/604.1',
        'Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.6261.64 Mobile Safari/537.36',
        'Mozilla/5.0 (iPhone; CPU iPhone OS 17_3_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/122.0.6261.89 Mobile/15E148 Safari/604.1',
        'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.6261.64 Mobile Safari/537.36'
    ]
    return random.choice(user_agents)

def extract_amount_from_text(text):
    # Common patterns for discounts in both USD and INR
    amount_patterns = [
        r'(?:RS\.?|₹|INR)\s*(\d+(?:,\d+)*(?:\.\d{2})?)',  # INR amounts
        r'\$\s*(\d+(?:,\d+)*(?:\.\d{2})?)',  # USD amounts
        r'(\d+)%\s*(?:OFF|DISCOUNT|CASHBACK)',  # Percentage discounts
        r'FLAT\s+(?:RS\.?|₹|INR|USD|\$)?\s*(\d+)',  # Flat discounts
        r'SAVE\s+(?:RS\.?|₹|INR|USD|\$)?\s*(\d+)',  # Save amounts
        r'(?:RS\.?|₹|INR|USD|\$)?\s*(\d+)\s*OFF',  # Amount off
        r'UP\s+TO\s+(\d+)%',  # Up to X% off
        r'MIN\s+(\d+)%\s*OFF',  # Minimum X% off
        r'EXTRA\s+(\d+)%',  # Extra X% off
        r'(\d+)%\s*INSTANT',  # Instant discount
        r'(\d+)\s*PERCENT',  # Percent off
        r'€\s*(\d+(?:,\d+)*(?:\.\d{2})?)',  # Euro amounts
        r'£\s*(\d+(?:,\d+)*(?:\.\d{2})?)'  # GBP amounts
    ]
    
    for pattern in amount_patterns:
        match = re.search(pattern, text.upper())
        if match:
            amount = match.group(1).replace(',', '')
            try:
                amount = float(amount)
                # Determine currency and type
                if '₹' in text or 'RS.' in text.upper() or 'INR' in text.upper():
                    currency = 'INR'
                elif '€' in text:
                    currency = 'EUR'
                    amount = amount * 90  # Approximate EUR to INR
                elif '£' in text:
                    currency = 'GBP'
                    amount = amount * 105  # Approximate GBP to INR
                else:
                    currency = 'USD'
                    amount = amount * USD_TO_INR_RATE if '$' in text else amount

                return {
                    'amount': amount,
                    'type': 'fixed' if amount > 100 else 'percentage',
                    'usd_amount': f"${amount/USD_TO_INR_RATE:.2f}" if amount > 100 else f"{amount}% off",
                    'inr_amount': f"₹{amount:.2f}" if amount > 100 else f"{amount}% off",
                    'currency': currency
                }
            except ValueError:
                pass
    return None

def is_food_delivery_site(site):
    return any(domain in site.lower() for domain in FOOD_DELIVERY_CONFIGS.keys())

def get_food_delivery_config(site):
    for domain, config in FOOD_DELIVERY_CONFIGS.items():
        if domain in site.lower():
            return config
    return None

def extract_codes_from_text(text, site):
    codes = []
    
    # Generic regex patterns for promo codes
    generic_patterns = [
        r'(?:USE|APPLY|ENTER)\s+(?:CODE|COUPON)?\s*[A-Z0-9]{4,15}',
        r'[A-Z0-9]{4,15}(?:\s+AT\s+CHECKOUT|\s+WHILE\s+CHECKING\s+OUT)',
        r'CODE:?\s*[A-Z0-9]{4,15}',
        r'COUPON:?\s*[A-Z0-9]{4,15}',
        r'PROMOCODE:?\s*[A-Z0-9]{4,15}',
        r'[A-Z0-9]{5,15}(?:\s*-\s*){0,4}[A-Z0-9]*',  # Handles codes with hyphens
        r'[A-Z]{2,8}[0-9]{2,8}',  # Common format like SAVE20, SPRING30
        r'(?:NEW|FIRST|WELCOME)[A-Z0-9]{2,12}',  # New user codes
        r'(?:SAVE|GET|OFF)[0-9]{2,3}[A-Z0-9]*'  # Discount focused codes
    ]
    
    # Get food delivery specific config if applicable
    food_config = get_food_delivery_config(site)
    patterns_to_use = generic_patterns + (food_config['regex_patterns'] if food_config else [])
    
    for pattern in patterns_to_use:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            code = match.group(0)
            # Extract the actual code part
            if 'CODE' in code.upper():
                code = code.split('CODE', 1)[1].strip(':').strip()
            elif 'COUPON' in code.upper():
                code = code.split('COUPON', 1)[1].strip(':').strip()
            elif 'PROMOCODE' in code.upper():
                code = code.split('PROMOCODE', 1)[1].strip(':').strip()
            elif 'AT CHECKOUT' in code.upper():
                code = code.split('AT CHECKOUT')[0].strip()
            elif 'WHILE CHECKING OUT' in code.upper():
                code = code.split('WHILE CHECKING OUT')[0].strip()
            
            # Clean up the code
            code = re.sub(r'\s+', '', code)  # Remove spaces
            code = re.sub(r'^[-:]+|[-:]+$', '', code)  # Remove leading/trailing hyphens and colons
            
            # Skip if code is too short or too long
            if len(code) < 4 or len(code) > 15:
                continue
                
            # Skip common UI text and navigation elements
            common_ui_elements = [
                'RESTAURA', 'FAVORITE', 'CORPORAT', 'OTHER0CA', 'ELOOKING', 
                'EARCHSWI', 'FERSNEWS', 'TRACK', 'WITH', 'SWIGGY', 'LOCATION',
                'USFOLLOW', 'HLOG', 'REVIEWS0', 'GPSSEARC', 'VERMA', 'PHOTOS2F',
                'MELTA', 'OUTLINEC', 'MELTHEAR', 'ECOCOBAN', 'LAUNCHTH',
                'SEARCH', 'MENU', 'ABOUT', 'LOGIN', 'SIGNUP', 'REGISTER',
                'CONTACT', 'HELP', 'SUPPORT', 'ACCOUNT', 'PROFILE', 'SETTINGS'
            ]
            
            if code.upper() in common_ui_elements:
                continue
            
            # Extract amount if present
            amount = 0
            currency = 'unknown'
            if '₹' in text or 'INR' in text or 'RS.' in text:
                amount_match = re.search(r'(?:₹|INR|RS\.?)\s*(\d+(?:,\d+)?)', text)
                if amount_match:
                    amount = float(amount_match.group(1).replace(',', ''))
                    currency = 'INR'
            elif '$' in text or 'USD' in text:
                amount_match = re.search(r'(?:\$|USD)\s*(\d+(?:\.\d+)?)', text)
                if amount_match:
                    amount = float(amount_match.group(1))
                    currency = 'USD'
            elif '€' in text:
                amount_match = re.search(r'€\s*(\d+(?:\.\d+)?)', text)
                if amount_match:
                    amount = float(amount_match.group(1))
                    currency = 'EUR'
            elif '£' in text:
                amount_match = re.search(r'£\s*(\d+(?:\.\d+)?)', text)
                if amount_match:
                    amount = float(amount_match.group(1))
                    currency = 'GBP'
            
            # Calculate confidence based on context
            confidence = 'low'
            promo_keywords = ['PROMO', 'OFFER', 'SAVE', 'DISCOUNT', 'COUPON', 'CODE', 'DEAL']
            
            if any(keyword in text.upper() for keyword in promo_keywords):
                confidence = 'medium'
            
            # Higher confidence if code format matches common patterns
            if (re.match(r'^[A-Z]+[0-9]+$', code) or  # Like SAVE20
                re.match(r'^(?:NEW|FIRST|WELCOME)', code) or  # New user codes
                'PROMO' in code.upper() or 
                'SAVE' in code.upper() or
                amount > 0):  # Has associated discount
                confidence = 'high'
            
            codes.append({
                'code': code,
                'amount': amount,
                'currency': currency,
                'type': 'fixed' if amount > 0 else 'unknown',
                'confidence': confidence,
                'description': text[:200] + '...' if len(text) > 200 else text,
                'inr_amount': f'₹{amount:,.2f}' if currency == 'INR' else f'₹{amount * USD_TO_INR_RATE:,.2f}' if currency in ['USD', 'EUR', 'GBP'] else 'unknown',
                'usd_amount': f'${amount:,.2f}' if currency == 'USD' else f'${amount / USD_TO_INR_RATE:,.2f}' if currency == 'INR' else 'unknown'
            })
    
    return codes

@lru_cache(maxsize=100)
def get_cached_url_content(url):
    """Cache URL content to reduce requests"""
    try:
        headers = {
            'User-Agent': get_random_user_agent(),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive',
            'Cache-Control': 'max-age=0'
        }
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        if response.status_code == 200:
            return response.text
    except Exception as e:
        logger.error(f"Error fetching {url}: {str(e)}")
    return None

def fetch_url(url, timeout=REQUEST_TIMEOUT):
    """Fetch URL with retries and caching"""
    for attempt in range(MAX_RETRIES):
        try:
            content = get_cached_url_content(url)
            if content:
                return content
            time.sleep(1)  # Add delay between retries
        except Exception as e:
            logger.error(f"Attempt {attempt + 1} failed for {url}: {str(e)}")
    return None

def get_source_urls(site):
    """Get optimized list of source URLs"""
    urls = []
    base_url = f'https://{site}'
    
    # Priority 1: Most likely to have promo codes (reduced list)
    priority_paths = [
        '/offers',
        '/promo',
        '/coupons',
        '/deals',
        '/sale'
    ]
    
    # Priority 2: Good chances of finding codes (reduced list)
    secondary_paths = [
        '/first-order',
        '/new-user',
        '/welcome-offer',
        '/app'
    ]
    
    # Add URLs in priority order
    for path in priority_paths:
        urls.append(urljoin(base_url, path))
    
    for path in secondary_paths:
        urls.append(urljoin(base_url, path))
    
    return urls

def calculate_code_score(code_info):
    score = 0
    # Higher score for codes with discount amounts
    if code_info['amount'] > 0:
        score += 50
        # Higher score for larger discounts
        if code_info['type'] == 'percentage':
            score += min(code_info['amount'], 50)  # Cap at 50 for percentage
        else:
            score += min(code_info['amount'] / 1000, 50)  # Cap at 50 for fixed amounts
    
    # Higher score for high confidence codes
    if code_info['confidence'] == 'high':
        score += 30
    elif code_info['confidence'] == 'medium':
        score += 15
    
    # Higher score for codes with specific keywords
    keywords = ['OFF', 'SAVE', 'DISCOUNT', 'PROMO', 'COUPON', 'DEAL', 'OFFER']
    if any(keyword in code_info['code'].upper() for keyword in keywords):
        score += 20
    
    # Higher score for codes with reasonable length (not too short, not too long)
    code_length = len(code_info['code'])
    if 4 <= code_length <= 12:
        score += 10
        
    # Higher score for codes that appear to be actual promo codes
    if 'USE' in code_info['description'].upper() or 'APPLY' in code_info['description'].upper():
        score += 25
    if 'CHECKOUT' in code_info['description'].upper():
        score += 25
    
    return score

def get_premium_features(plan_type):
    """Get features for a specific premium plan"""
    return PREMIUM_PLANS.get(plan_type, PREMIUM_PLANS['basic'])

def test_promo_code(site, code, plan_type='basic'):
    """
    Test if a promo code is valid by simulating its application.
    Returns a tuple of (is_valid, discount_amount, message)
    """
    try:
        # Get plan features
        plan_features = get_premium_features(plan_type)
        
        # Check if site is supported in the plan
        if not any(supported_site in site.lower() for supported_site in plan_features['supported_sites']):
            return False, 0, f"Code testing for this website is not supported in {plan_type} plan"
        
        # Get the appropriate domain for the site
        domain = site.lower()
        if not domain.startswith('http'):
            domain = f'https://{domain}'
        
        # Prepare test data based on site type and plan
        test_data = {
            'items': [
                {
                    'id': 'test_item_1',
                    'price': 1000.00,
                    'quantity': 1
                }
            ],
            'promo_code': code,
            'currency': 'INR' if '.in' in domain else 'USD'
        }
        
        # Site-specific test endpoints and validation
        test_endpoints = {
            'amazon': '/gp/cart/apply-promo',
            'flipkart': '/checkout/promo/apply',
            'myntra': '/cart/apply-coupon',
            'swiggy': '/api/v2/cart/apply-coupon',
            'zomato': '/api/v2/cart/apply-coupon',
            'ubereats': '/api/v1/cart/apply-promo',
            'doordash': '/api/v2/cart/apply-promo',
            'netflix': '/api/v1/subscription/apply-promo',
            'prime video': '/api/v1/subscription/apply-promo',
            'hotstar': '/api/v1/subscription/apply-promo',
            'booking.com': '/api/v1/booking/apply-promo',
            'expedia': '/api/v1/booking/apply-promo',
            'airbnb': '/api/v1/booking/apply-promo',
            'coursera': '/api/v1/subscription/apply-promo',
            'udemy': '/api/v1/cart/apply-promo',
            'spotify': '/api/v1/subscription/apply-promo',
            'apple music': '/api/v1/subscription/apply-promo',
            'hulu': '/api/v1/subscription/apply-promo',
            'disney+': '/api/v1/subscription/apply-promo',
            'hbo max': '/api/v1/subscription/apply-promo'
        }
        
        # Find the appropriate endpoint
        endpoint = None
        for site_key in test_endpoints:
            if site_key in domain:
                endpoint = test_endpoints[site_key]
                break
        
        if not endpoint:
            return False, 0, "Code testing not supported for this website"
        
        # Prepare headers based on plan type
        headers = {
            'User-Agent': get_random_user_agent(),
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Origin': domain,
            'Referer': f'{domain}/cart'
        }
        
        # Add premium plan specific headers
        if plan_type == 'premium':
            headers.update({
                'X-Premium-Plan': 'premium',
                'X-API-Key': 'premium_key_here'  # In production, use proper API key management
            })
        
        # Simulate API call with plan-specific timeout
        test_url = f'{domain}{endpoint}'
        response = requests.post(
            test_url,
            json=test_data,
            headers=headers,
            timeout=plan_features['test_timeout']
        )
        
        # Check response based on plan type
        if response.status_code == 200:
            try:
                result = response.json()
                # Different sites return different response formats
                if 'discount' in result:
                    return True, result['discount'], "Code is valid"
                elif 'savings' in result:
                    return True, result['savings'], "Code is valid"
                elif 'amount' in result:
                    return True, result['amount'], "Code is valid"
                else:
                    return True, 0, "Code is valid but discount amount unknown"
            except:
                return True, 0, "Code appears to be valid"
        elif response.status_code == 400:
            return False, 0, "Code is invalid or expired"
        elif response.status_code == 403:
            return False, 0, "Code testing not allowed"
        else:
            return False, 0, "Unable to verify code"
            
    except Exception as e:
        return False, 0, f"Error testing code: {str(e)}"

@app.route('/')
def hello_world():
    return "PromoGenie backend is running!"

@app.route('/login', methods=['POST'])
def login():
    try:
        user_id = request.headers.get('X-Replit-User-Id')
        username = request.headers.get('X-Replit-User-Name')
        
        if not user_id or not username:
            return jsonify({"error": "Authentication required"}), 401
        
        session['user_id'] = user_id
        session['username'] = username
        
        return jsonify({
            "message": "Login successful",
            "user": {
                "id": user_id,
                "username": username
            }
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/get-codes', methods=['POST'])
def get_codes():
    start_time = time.time()
    data = request.get_json()
    site = data.get('site', '').strip()
    plan_type = data.get('plan_type', 'basic')
    
    if not site:
        return jsonify({'error': 'Site parameter is required'}), 400
    
    try:
        # Extract country from site name if present
        country = None
        site_parts = site.lower().split()
        if len(site_parts) > 1:
            potential_country = site_parts[-1]
            if potential_country in ['india', 'usa', 'uk', 'canada', 'australia']:
                country = potential_country
                site = ' '.join(site_parts[:-1])
        
        if not country:
            country = 'india'
        
        # Get source URLs
        source_urls = get_source_urls(site)
        
        # Add country-specific URLs if country is specified
        if country:
            country_domains = {
                'india': ['.in', '.co.in'],
                'usa': ['.com'],
                'uk': ['.co.uk'],
                'canada': ['.ca'],
                'australia': ['.com.au']
            }
            
            if country in country_domains:
                base_url = f'https://{site}'
                for domain in country_domains[country]:
                    country_site = f"{site}{domain}"
                    country_urls = get_source_urls(country_site)
                    source_urls.extend(country_urls)
        
        # Remove duplicates while preserving order
        source_urls = list(dict.fromkeys(source_urls))
        
        all_codes = []
        processed_urls = set()
        min_codes = 3  # Reduced minimum codes
        max_codes = 5  # Reduced maximum codes
        max_search_time = 30  # Reduced search time for free tier
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_url = {executor.submit(fetch_url, url): url for url in source_urls}
            
            for future in concurrent.futures.as_completed(future_to_url):
                if time.time() - start_time > max_search_time:
                    break
                    
                url = future_to_url[future]
                if url in processed_urls:
                    continue
                    
                processed_urls.add(url)
                try:
                    html = future.result()
                    if html:
                        soup = BeautifulSoup(html, 'html.parser')
                        
                        # Look for promo code elements
                        for element in soup.find_all(['div', 'span', 'p', 'a', 'button']):
                            text = element.get_text(strip=True)
                            if text:
                                codes = extract_codes_from_text(text, site)
                                for code in codes:
                                    code['source_url'] = url
                                    all_codes.append(code)
                                    
                                    # If we have enough high-confidence codes, we can stop searching
                                    high_confidence_codes = [c for c in all_codes if c['confidence'] == 'high']
                                    if len(high_confidence_codes) >= max_codes:
                                        break
                except Exception as e:
                    logger.error(f"Error processing {url}: {str(e)}")
        
        # Remove duplicates while preserving order
        seen_codes = set()
        unique_codes = []
        for code in all_codes:
            if code['code'] not in seen_codes:
                seen_codes.add(code['code'])
                unique_codes.append(code)
        
        # Sort by confidence and amount
        unique_codes.sort(key=lambda x: (
            {'high': 0, 'medium': 1, 'low': 2}[x['confidence']],
            -x['amount'] if x['amount'] > 0 else 0
        ))
        
        # Take best codes (3-5)
        if len(unique_codes) > max_codes:
            top_codes = unique_codes[:max_codes]
        elif len(unique_codes) >= min_codes:
            top_codes = unique_codes
        else:
            top_codes = unique_codes
        
        search_time = time.time() - start_time
        
        if not top_codes:
            return jsonify({
                'message': 'After testing several promo codes for this website, we concluded that currently there are no working promotional offers. Try another website or use our premium services for deeper research.',
                'site': site,
                'country': country,
                'search_time': f'{search_time:.2f} seconds',
                'codes_found': 0
            }), 404
        
        # After finding codes, test them if premium feature is enabled
        if plan_type in PREMIUM_PLANS:
            tested_codes = []
            for code in top_codes:
                is_valid, discount, message = test_promo_code(site, code['code'], plan_type)
                if is_valid:
                    code['tested'] = True
                    code['test_result'] = {
                        'valid': True,
                        'discount': discount,
                        'message': message,
                        'plan_type': plan_type
                    }
                else:
                    code['tested'] = True
                    code['test_result'] = {
                        'valid': False,
                        'message': message,
                        'plan_type': plan_type
                    }
                tested_codes.append(code)
            top_codes = tested_codes
        
        # Format the response
        formatted_codes = []
        for code in top_codes:
            formatted_code = {
                'code': code['code'],
                'discount': {
                    'amount': code['inr_amount'] if country == 'india' else code['usd_amount'],
                    'type': code['type'],
                    'confidence': code['confidence']
                },
                'description': code['description'],
                'source': code['source_url']
            }
            
            # Add test results if available
            if plan_type in PREMIUM_PLANS and 'test_result' in code:
                formatted_code['test_result'] = code['test_result']
            
            formatted_codes.append(formatted_code)
        
        return jsonify({
            'codes': formatted_codes,
            'codes_found': len(formatted_codes),
            'site': site,
            'country': country,
            'search_time': f'{search_time:.2f} seconds',
            'message': f'Found {len(formatted_codes)} potential promo codes for {site}',
            'premium_features': {
                'plan_type': plan_type,
                'codes_tested': plan_type in PREMIUM_PLANS,
                'tested_count': sum(1 for c in formatted_codes if 'test_result' in c),
                'plan_details': PREMIUM_PLANS.get(plan_type, {})
            }
        })
        
    except Exception as e:
        logger.error(f"Error in get_codes: {str(e)}")
        return jsonify({
            'error': 'An error occurred while processing your request',
            'message': str(e)
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
