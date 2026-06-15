import os
import time

# --- Hardware Optimization for Pi Zero 2 W ---
# Limits PyTorch to 2 threads to prevent camera/network timeouts
os.environ["OMP_NUM_THREADS"] = "2"
os.environ["MKL_NUM_THREADS"] = "2"

print("[-] Waking up the Pi Zero 2 W...")
print("[-] Loading AI libraries...")

from ultralytics import YOLO
import shutil
from datetime import datetime
import requests

# --- Load the Standard PyTorch Model ---
model = YOLO("best.pt")

QUEUE_DIR = "queue"
HIGHRES_DIR = "highres_cache"
OUTPUT_DIR = "detections"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# --- Global Species Cooldown ---
GLOBAL_COOLDOWN = 300.0  
global_species_log = {}  

# --- Target VPS Configuration ---
VPS_WEBHOOK_URL = "ENTER YOUR WEBHOOK URL"

def send_to_vps_webhook(image_path, species_name):
    print(f"[Network] Firing webhook to VPS for {species_name}...")
    try:
        with open(image_path, "rb") as f:
            filename = os.path.basename(image_path)
            files = {"file": (filename, f, "image/jpeg")}
            
            message_content = (
                f"**New Visitor Alert!** A **{species_name.replace('-', ' ')}** has arrived!\n"
                f"**View Gallery:** ENTER YOUR WEBPAGE URL"
            )
            payload = {"content": message_content}
            
            # 15-second timeout to give the Pi Zero network stack a little extra leniency
            response = requests.post(VPS_WEBHOOK_URL, data=payload, files=files, timeout=15)
            if response.status_code == 200:
                print("[Network] Webhook successfully relayed through VPS!")
            else:
                print(f"[Network Error] VPS returned status {response.status_code}")
    except Exception as e:
        print(f"[Network Error] Failed to connect to VPS: {e}")

print("[-] Pi Zero 2 W 5-Frame Verification Engine Active and Listening!")

while True:
    events = {}
    
    # 1. Group incoming burst files by Event ID
    for filename in os.listdir(QUEUE_DIR):
        if filename.startswith("BATCH_") and filename.endswith(".jpg"):
            parts = filename.replace(".jpg", "").split("_")
            if len(parts) >= 4:
                event_id, slot_id = parts[1], parts[2]
                if event_id not in events:
                    events[event_id] = {'slot_id': slot_id, 'files': []}
                events[event_id]['files'].append(filename)
                
    # 2. Process complete bursts
    for event_id, data in events.items():
        file_paths = [os.path.join(QUEUE_DIR, f) for f in data['files']]
        
        # Cleanup incomplete bursts older than 60 seconds
        if len(file_paths) < 5:
            try:
                age = time.time() - os.path.getmtime(file_paths[0])
                if age > 60:
                    print(f"[Cleanup] Purging incomplete burst for Event {event_id}")
                    for f in data['files']:
                        try: os.remove(os.path.join(QUEUE_DIR, f))
                        except Exception: pass
                        try: os.remove(os.path.join(HIGHRES_DIR, f))
                        except Exception: pass
            except Exception:
                pass
            continue

        # Strictly enforce the 5-frame requirement
        if len(file_paths) >= 5:
            slot_id = data['slot_id']
            print(f"\n--- Analyzing Event {event_id} (Slot {slot_id}) ---")
            
            valid_results = []
            votes = []
            
            # Run inference sequentially on the 5 files
            for f_path in file_paths[:5]:
                filename_short = os.path.basename(f_path)
                
                start_time = time.perf_counter()
                
                # Downscale to 640 before math to prevent Pi Zero CPU lockups
                results = model.predict(source=f_path, conf=0.15, verbose=False, imgsz=640)
                
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                print(f"[Timer] {filename_short} inference took: {elapsed_ms:.2f} ms")
                
                if len(results) > 0:
                    r = results[0]
                    if r.boxes is not None and len(r.boxes) > 0:
                        class_id = int(r.boxes[0].cls[0].item())
                        species = model.names[class_id].replace(" ", "-")
                        votes.append(species)
                        valid_results.append(r)

            # 3. Mode Evaluation & Global Cooldown Check
            should_log = False
            mode_species = None
            
            if len(votes) == 0:
                print("[Result] Drop Frame: Model marked frames as unidentified.")
            else:
                mode_species = max(set(votes), key=votes.count)
                mode_count = votes.count(mode_species)
                
                print(f"[YOLO Votes] {votes}")
                
                if mode_count == 1 and len(votes) > 1:
                    print("[Result] Drop Frame: Conflicting species tie-vote.")
                else:
                    print(f"[Mode Passed] Detected: {mode_species} ({mode_count}/{len(votes)} votes)")
                    current_time = time.time()
                    
                    if mode_species not in global_species_log:
                        should_log = True
                    else:
                        time_since_last_seen = current_time - global_species_log[mode_species]
                        if time_since_last_seen > GLOBAL_COOLDOWN:
                            should_log = True
                        else:
                            print(f"[Rule Triggered] {mode_species} skipped (Cooldown: {int(GLOBAL_COOLDOWN - time_since_last_seen)}s remaining).")
                    
                    if should_log:
                        best_idx = votes.index(mode_species)
                        best_filename = data['files'][best_idx]
                        highres_source = os.path.join(HIGHRES_DIR, best_filename)
                        
                        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                        save_name = f"{timestamp_str}_{mode_species}.jpg"
                        save_path = os.path.join(OUTPUT_DIR, save_name)
                        
                        attempts = 0
                        while not os.path.exists(highres_source) and attempts < 10:
                            time.sleep(0.1)
                            attempts += 1
                            
                        if os.path.exists(highres_source):
                            shutil.copy(highres_source, save_path)
                            print(f"[SUCCESS] High-res clean frame saved: {save_name}")
                            send_to_vps_webhook(save_path, mode_species)
                            global_species_log[mode_species] = current_time
                        else:
                            print(f"[Fallback] High-res missing! Saving YOLO visualization instead.")
                            valid_results[best_idx].save(filename=save_path)
                            send_to_vps_webhook(save_path, mode_species)
                            global_species_log[mode_species] = current_time

            # 4. Cleanup temporary files
            for f in data['files']:
                try: os.remove(os.path.join(QUEUE_DIR, f))
                except Exception: pass
                try: os.remove(os.path.join(HIGHRES_DIR, f))
                except Exception: pass
            
    time.sleep(0.2)
