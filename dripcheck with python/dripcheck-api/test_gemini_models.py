import urllib.request
import json
import ssl

api_key = "AIzaSyCrY0KUM7OJcXbqmwQW1DN8NUhs0lBuqMo"

# Use SSL without verification to avoid cert issues in test scripts
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def test_models():
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    req = urllib.request.Request(url, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, context=ctx) as response:
            data = json.loads(response.read().decode('utf-8'))
            print("Image or Imagen models:")
            for model in data.get('models', []):
                name = model['name']
                if "image" in name.lower() or "imagen" in name.lower():
                    print(f"- {name} (Supported actions: {model.get('supportedGenerationMethods')})")
    except Exception as e:
        print(f"Error calling Gemini API: {e}")

if __name__ == '__main__':
    test_models()
