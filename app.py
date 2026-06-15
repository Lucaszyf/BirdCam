from flask import Flask, render_template_string, send_from_directory
import os
from datetime import datetime

app = Flask(__name__)

DETECTIONS_DIR = "detections"

# Simple HTML layout bakes straight into the Python file to avoid template clutter
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

        /* --- MODAL STYLES --- */
        .bird-thumbnail { cursor: pointer; transition: 0.2s; }
        .bird-thumbnail:hover { opacity: 0.8; }
        
        .modal {
            display: none; 
            position: fixed; 
            z-index: 1000; 
            left: 0; 
            top: 0; 
            width: 100%; 
            height: 100%; 
            overflow: auto; 
            background-color: rgba(0,0,0,0.85); 
            backdrop-filter: blur(5px); 
        }
        
        /* SCALING FIX APPLIED HERE */
        .modal-content {
            margin: auto;
            display: block;
            max-width: 90vw; /* Max 90% of screen width */
            max-height: 90vh; /* Max 90% of screen height */
            width: auto;
            height: auto;
            object-fit: contain; /* Scale proportionally to fit bounds */
            position: relative;
            top: 50%;
            transform: translateY(-50%);
            border-radius: 12px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.5);
            animation-name: zoom;
            animation-duration: 0.25s;
        }
        
        @keyframes zoom {
            from {transform: translateY(-50%) scale(0.95); opacity: 0;}
            to {transform: translateY(-50%) scale(1); opacity: 1;}
        }
    </style>
</head>
<body>
    <h1>Local Birdcam Detections</h1>
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
        
        # Sort files chronologically, newest first
        files.sort(reverse=True)
        
        for filename in files:
            # Parse names matching our format: YYYYMMDD_HHMMSS_Species-Name.jpg
            parts = filename.replace(".jpg", "").split("_")
            if len(parts) >= 3:
                date_part, time_part = parts[0], parts[1]
                species_name = "_".join(parts[2:]).replace("-", " ")
                
                # Format timestamp for display
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

@app.route('/images/<filename>')
def serve_image(filename):
    """Safely serves the cropped image directly out of your detections directory."""
    return send_from_directory(DETECTIONS_DIR, filename)

if __name__ == '__main__':
    # Run server on port 5000, visible to your local Wi-Fi network
    app.run(host='0.0.0.0', port=5000, debug=False)
