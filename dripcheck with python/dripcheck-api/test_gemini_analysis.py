import urllib.request
import json
import base64
import ssl
import os

api_key = "AIzaSyCrY0KUM7OJcXbqmwQW1DN8NUhs0lBuqMo"
input_image_path = r"C:\Users\acer\.gemini\antigravity\brain\8b5a7391-7beb-4640-91cd-5ae9fbbeede6\user_shirt_photo_1779723435521.png"

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def test_image_analysis():
    print(f"Reading input image from: {input_image_path}")
    if not os.path.exists(input_image_path):
        print("Input image not found!")
        return

    with open(input_image_path, "rb") as f:
        image_bytes = f.read()
    
    image_b64 = base64.b64encode(image_bytes).decode('utf-8')
    
    prompt = (
        "Analyze this image of a clothing item. Return a JSON object with the following fields: "
        "1. name: a short descriptive name of the item. "
        "2. primary_color: the dominant color. "
        "3. secondary_color: secondary color (or null). "
        "4. color_family: one of ['Neutral', 'Earth', 'Dark', 'Bold', 'Pastel', 'Warm']. "
        "5. pattern: one of ['Solid', 'Stripes', 'Checks', 'Graphic', 'Floral', 'Abstract']. "
        "6. fit: one of ['Slim', 'Regular', 'Relaxed', 'Oversized', 'Cropped', 'Baggy', 'Tapered']. "
        "7. occasion_type: list containing one or more of ['Casual', 'Formal', 'Business', 'Party', 'Gym', 'Date Night', 'Weekend']. "
        "8. season: one of ['Summer', 'Winter', 'Monsoon', 'All-season']. "
        "9. formality_level: integer from 1 to 10. "
        "10. style_tags: list of matching styles from ['Minimalist', 'Streetwear', 'Sporty', 'Vintage', 'Bohemian', 'Classic', 'Business Casual', 'Y2K', 'Preppy', 'Grunge', 'Monochrome', 'Techwear', 'Cottagecore', 'Bold', 'Layered', 'Designer']. "
        "11. mood_tags: list of 2-3 mood words. "
        "12. aesthetic_tone: a brief description of the visual style. "
        "Return ONLY valid JSON."
    )
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {
                        "inlineData": {
                            "mimeType": "image/png",
                            "data": image_b64
                        }
                    }
                ]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json"
        }
    }
    
    req_body = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=req_body,
        headers={'Content-Type': 'application/json'}
    )
    
    print("Sending request to Gemini 2.0 Flash...")
    try:
        with urllib.request.urlopen(req, context=ctx) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            print("Received response!")
            text_out = res_data["candidates"][0]["content"]["parts"][0]["text"]
            print("JSON Output from model:")
            print(text_out)
    except Exception as e:
        print(f"Error calling Gemini API: {e}")
        if hasattr(e, 'read'):
            try:
                print("Error details:", e.read().decode('utf-8'))
            except:
                pass

if __name__ == '__main__':
    test_image_analysis()
