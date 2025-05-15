from flask import Flask

app = Flask(__name__)

@app.route('/health')
def health():
    return {"status": "healthy"}, 200

@app.route('/telegram', methods=['POST'])
def telegram_webhook():
    return {"status": "success", "message": "Webhook received"}, 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))