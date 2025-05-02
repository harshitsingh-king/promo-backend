# PromoGenie Backend

A Flask-based backend service for finding and testing promotional codes across various websites.

## Features

- Find promo codes for any website
- Premium plans with code testing capabilities
- Support for multiple countries
- Optimized for Render.com free tier hosting

## Deployment on Render.com

1. Fork or clone this repository
2. Create a new Web Service on Render.com
3. Connect your repository
4. The service will automatically deploy using the configuration in `render.yaml`

### Environment Variables

The following environment variables are automatically set by Render.com:
- `SECRET_KEY`: Automatically generated
- `PORT`: Set to 10000
- `PYTHON_VERSION`: Set to 3.9.0

## Local Development

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run the development server:
```bash
python app.py
```

## API Endpoints

- `GET /`: Health check endpoint
- `POST /login`: User authentication
- `POST /get-codes`: Get promo codes for a website

## Premium Plans

- Basic ($1/month): 50 tests/day, 5 major sites
- Standard ($3/month): 200 tests/day, 10 sites
- Premium ($7/month): 1000 tests/day, 20 sites

## License

MIT License 