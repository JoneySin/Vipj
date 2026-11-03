# 1. सबसे लेटेस्ट और स्टेबल बेस इमेज का उपयोग
FROM python:3.11-slim-bookworm

# 2. सिस्टम डिपेंडेंसीज इंस्टॉल करना (जरूरी टूल्स)
RUN apt-get update && apt-get install -y \
    git \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# 3. वर्किंग डायरेक्टरी सेट करना
WORKDIR /app

# 4. पहले requirements.txt कॉपी करें (कैश का फायदा लेने के लिए)
COPY requirements.txt .

# 5. बिना कैश के डिपेंडेंसीज इंस्टॉल करें और pip को अपडेट करें
RUN pip install --no-cache-dir -U pip && \
    pip install --no-cache-dir -r requirements.txt

# 6. अब बाकी का पूरा कोड कॉपी करें
COPY . .

# 7. बॉट स्टार्ट करने की कमांड
CMD ["python3", "bot.py"]
