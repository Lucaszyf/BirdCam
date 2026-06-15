from flask import Flask, render_template_string, send_from_directory, request, jsonify
import os
from datetime import datetime
import requests

app = Flask(__name__)

# --- VPS Configuration ---
DETECTIONS_DIR = "./detections" # Saves in the same folder you run this script from
os.makedirs(DETECTIONS_DIR, exist_ok=True)

# Your exact Discord Webhook
DISCORD_WEBHOOK_URL = "YOUR DISCORD WEBHOOK"
# Your VPS Public IP (Used for the clickable link in Discord)
VPS_PUBLIC_URL = "http://your-vps-public-ip:5000" 

# --- HTML Dashboard Template ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Birdcam Dashboard</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f0f2f5; margin: 0; padding: 20px; color: #333; }
        h1 { text-align: center; color: #2c3e50; margin-bottom: 30px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 20px; max-width: 1200px; margin: 0 auto; }
        .card { background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 10px rgba(0,0,0,0.05); transition: 0.2s; }
        .card:hover { transform: translateY(-3px); box-shadow: 0 6px 15px rgba(0,0,0,0.1); }
        .card img { width: 100%; height: 220px; object-fit: cover; background: #e0e0e0; }
        .info { padding: 15px; }
        .species { font-size: 1.2rem; font-weight: bold; color: #1e3799; text-transform: capitalize; margin: 0 0 8px 0; }
        .time { font-size: 0.85rem; color: #7f8c8d; margin: 0; }
        .empty { text-align: center; grid-column: 1/-1; color: #7f8c8d; padding: 50px; font-size: 1.2rem; }
        
        /* Modal Styles */
        .bird-thumbnail { cursor: pointer; transition: 0.2s; }
        .bird-thumbnail:hover { opacity: 0.8; }
        .modal { display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; overflow: auto; background-color: rgba(0,0,0,0.85); backdrop-filter: blur(5px); }
        .modal-content { margin: auto; display: block; max-width: 90vw; max-height: 90vh; width: auto; height: auto; object-fit: contain; position: relative; top: 50%; transform: translateY(-50%); border-radius: 12px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); animation-name: zoom; animation-duration: 0.25s; }
        @keyframes zoom { from {transform: translateY(-50%) scale(0.95); opacity: 0;} to {transform: translateY(-50%) scale(1); opacity: 1;} }
    </style>
</head>
<body>
    <h1>Birdcam Detections</h1>
    <div class="grid">
        {% for bird in birds %}
        <div class="card">
            <img src="/images/{{ bird.filename }}" alt="Bird photo" class="bird-thumbnail" onclick="openModal(this.src)">
            <div class="info">
                <p class="species">{{ bird.species }}</p>
                <p class="time"> {{ bird.time }}</p>
            </div>
        </div>
        {% else %}
        <div class="empty">No birds detected yet! Waiting for visitors...</div>
        {% endfor %}
    </div>

    <div id="imageModal" class="modal" onclick="closeModal()">
        <img class="modal-content" id="fullResImage">
    </div>

    <script>
        function openModal(imageSrc) {
            var modal = document.getElementById("imageModal");
            var modalImg = document.getElementById("fullResImage");
            modal.style.display = "block";
            modalImg.src = imageSrc;
        }
        function closeModal() {
            var modal = document.getElementById("imageModal");
            modal.style.display = "none";
        }
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    birds = []
    if os.path.exists(DETECTIONS_DIR):
        files = [f for f in os.listdir(DETECTIONS_DIR) if f.endswith('.jpg')]
        files.sort(reverse=True) # Sort chronologically, newest first
        
        for filename in files:
            parts = filename.replace(".jpg", "").split("_")
            if len(parts) >= 3:
                date_part, time_part = parts[0], parts[1]
                species_name = "_".join(parts[2:]).replace("-", " ")
                try:
                    dt = datetime.strptime(f"{date_part}_{time_part}", "%Y%m%d_%H%M%S")
                    formatted_time = dt.strftime("%b %d, %Y at %I:%M %p")
                except ValueError:
                    formatted_time = "Unknown Date"
                    
                birds.append({
                    'filename': filename,
                    'species': species_name,
                    'time': formatted_time
                })
                
    return render_template_string(HTML_TEMPLATE, birds=birds)

@app.route('/webhook', methods=['POST'])
def webhook_relay():
    """Acts as a middleman: catches the payload from the Pi, saves it, and forwards to Discord."""
    if 'file' not in request.files:
        return jsonify({"error": "No file included in webhook"}), 400
        
    file = request.files['file']
    content = request.form.get('content', 'New Bird Detected!')
    
    if file.filename == '':
        return jsonify({"error": "Empty filename"}), 400

    # 1. Save the image locally on the VPS for the website gallery
    save_path = os.path.join(DETECTIONS_DIR, file.filename)
    file.save(save_path)
    print(f"[+] Webhook caught! Saved locally: {file.filename}")
    
    # 2. Forward the exact same payload to the REAL Discord webhook
    try:
        with open(save_path, "rb") as f:
            files = {"file": (file.filename, f, "image/jpeg")}
            payload = {"content": content}
            
            discord_resp = requests.post(DISCORD_WEBHOOK_URL, data=payload, files=files)
            if discord_resp.status_code in [200, 204]:
                print("[Discord] Notification sent successfully!")
            else:
                print(f"[Discord Error] Failed to forward. Status {discord_resp.status_code}")
    except Exception as e:
        print(f"[Discord Error] Exception during forward: {e}")
        
    return jsonify({"status": "success"}), 200

@app.route('/images/<filename>')
def serve_image(filename):
    return send_from_directory(DETECTIONS_DIR, filename)

if __name__ == '__main__':
    # Binds to 0.0.0.0 so the VPS can accept incoming connections from the outside world
    app.run(host='0.0.0.0', port=5000, debug=False)
