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

def try_model_generate_content(model_name):
    print(f"\n--- Trying generateContent with model: {model_name} ---")
    with open(input_image_path, "rb") as f:
        image_bytes = f.read()
    image_b64 = base64.b64encode(image_bytes).decode('utf-8')
    
    prompt = (
        "Generate a clean e-commerce style studio shot of the same red shirt from the input image. "
        "Remove the background. Solid pure white background."
    )
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    
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
            "responseModalities": ["IMAGE"]
        }
    }
    
    req_body = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=req_body, headers={'Content-Type': 'application/json'})
    
    try:
        with urllib.request.urlopen(req, context=ctx) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            print("Success!")
            print(json.dumps(res_data, indent=2)[:500])
            return True
    except Exception as e:
        print(f"Failed with exception: {e}")
        if hasattr(e, 'read'):
            try:
                print("Error details:", e.read().decode('utf-8'))
            except:
                pass
        return False

def try_imagen_predict(model_name):
    print(f"\n--- Trying predict (Imagen) with model: {model_name} ---")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:predict?key={api_key}"
    
    # Imagen predict format usually takes prompt and config
    payload = {
        "instances": [
            {"prompt": "A beautiful red t-shirt on a pure white background, e-commerce studio shot"}
        ],
        "parameters": {
            "sampleCount": 1,
            "aspectRatio": "1:1",
            "outputMimeType": "image/png"
        }
    }
    
    req_body = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=req_body, headers={'Content-Type': 'application/json'})
    
    try:
        with urllib.request.urlopen(req, context=ctx) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            print("Success!")
            # Print keys or summary
            print(res_data.keys())
            if "predictions" in res_data:
                print(f"Generated {len(res_data['predictions'])} images!")
            return True
    except Exception as e:
        print(f"Failed with exception: {e}")
        if hasattr(e, 'read'):
            try:
                print("Error details:", e.read().decode('utf-8'))
            except:
                pass
        return False

if __name__ == '__main__':
    # Try gemini models
    for m in ["gemini-3.1-flash-image-preview", "gemini-3-pro-image-preview"]:
        try_model_generate_content(m)
        
    # Try imagen models
    for m in ["imagen-4.0-generate-001", "imagen-4.0-fast-generate-001"]:
        try_imagen_predict(m)
