import cv2
import pytesseract
from pytesseract import Output
import re
import time
import os
import numpy as np
import paho.mqtt.client as mqtt
import json
import csv

# Tesseract en haarcascade configuratie
pytesseract.pytesseract.tesseract_cmd = '/opt/homebrew/Cellar/tesseract/5.5.0/bin/tesseract'  # tekst detecteren in afbeeldingen
plate_cascade_path = '/Users/jaspermaes/Documents/3de_Jaar_EAICT/ImageProcessing/HW/haarcascade_russian_plate_number.xml'  # om te detecteren dat het een nummerplaat is (maar getraind op Russische nummerplaten)
plate_cascade = cv2.CascadeClassifier(plate_cascade_path)

# Zorg dat de map 'images' bestaat
image_dir = "images"
if not os.path.exists(image_dir):
    os.makedirs(image_dir)

# CSV-logbestand configureren
log_file = "log.csv"
if not os.path.exists(log_file):
    with open(log_file, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(["Datum", "Tijd", "Nummerplaat", "Status"])

# MQTT-configuratie
mqtt_broker = "broker.emqx.io"
mqtt_port = 1883
mqtt_topic = "testtopic/42"
mqtt_history_topic = "testtopic/history"

# Functies
def clean_plate_text(text):
    text = re.sub(r'[^A-Za-z0-9\-]', '', text)  # verwijdert alle karakters behalve letters, cijfers en het koppelteken -
    text = text.replace('B', '8')
    text = re.sub(r'(\d)-(\d)', r'\1-\2', text)
    return text

def validate_plate_format(plate_text):
    if re.match(r'^\d-[A-Z]{3}-\d{3}$', plate_text): 
        return plate_text
    return None

def save_detected_plate(frame, x, y, w, h, plate_text):
    # Snijd de nummerplaat uit en sla deze op
    plate = frame[y:y + h, x:x + w]
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    filename = os.path.join(image_dir, f"{plate_text}_{timestamp}.jpg")
    cv2.imwrite(filename, plate)
    print(f"Foto opgeslagen: {filename}")
    return filename

def log_detection(plate_text, status):
    # Log detectie naar CSV
    datum = time.strftime("%Y-%m-%d")
    tijd = time.strftime("%H:%M:%S")
    with open(log_file, mode='a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([datum, tijd, plate_text, status])
    print(f"Nummerplaat gelogd: {plate_text}, Status: {status}")

def filter_dark_red(frame):
    # Filter donkerrode kleuren in het HSV-spectrum
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    lower_red = np.array([0, 50, 50])
    upper_red = np.array([10, 255, 255])
    mask1 = cv2.inRange(hsv, lower_red, upper_red)
    lower_red2 = np.array([170, 50, 50])
    upper_red2 = np.array([180, 255, 255])
    mask2 = cv2.inRange(hsv, lower_red2, upper_red2)
    combined_mask = cv2.bitwise_or(mask1, mask2)

    # Inverseer de kleuren: wit -> zwart en zwart -> wit
    inverted_mask = cv2.bitwise_not(combined_mask)

    # Open een venster om het omgekeerde masker te zien
    cv2.imshow("Omgekeerd Masker (Zwart Tekst)", inverted_mask)

    return inverted_mask


def publish_detection(plate_text):
    # Verzend detectie via MQTT
    client = mqtt.Client()
    client.connect(mqtt_broker, mqtt_port, 60)
    timestamp = time.time()
    log_message = {
        "plate_text": plate_text,
        "timestamp": timestamp
    }
    client.publish(mqtt_topic, json.dumps(log_message))
    client.disconnect()
    print(f"Log verzonden naar MQTT broker: {log_message}")

def publish_history():
    # Verzend volledige historiek naar logviewer
    client = mqtt.Client()
    client.connect(mqtt_broker, mqtt_port, 60)
    with open(log_file, mode='r') as file:
        reader = csv.DictReader(file)
        for row in reader:
            history_entry = {
                "plate_text": row["Nummerplaat"],
                "timestamp": time.mktime(time.strptime(f"{row['Datum']} {row['Tijd']}", "%Y-%m-%d %H:%M:%S"))
            }
            client.publish(mqtt_history_topic, json.dumps(history_entry))
            time.sleep(0.1)  # Voorkom overbelasting van de broker
    client.disconnect()
    print("Historiek verzonden naar logviewer.")

# Callback voor MQTT
def on_message(client, userdata, msg):
    # Controleer op historiekverzoek
    if msg.payload.decode() == "request_history":
        publish_history()

# MQTT-client instellen
client = mqtt.Client()
client.on_message = on_message
client.connect(mqtt_broker, mqtt_port, 60)
client.subscribe(mqtt_history_topic)
client.loop_start()

# Hoofdprogramma
cap = cv2.VideoCapture(0)
detected_plates = {}  # Dictionary voor de detectietijden van nummerplaten

while True:
    ret, frame = cap.read()
    if not ret:
        break

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)
    
    plates = plate_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30)) #detecteerd waar de nummerplaat staat in het frame

    for (x, y, w, h) in plates:
        plate_region = frame[y:y + h, x:x + w]
        dark_red_mask = filter_dark_red(plate_region)  # Laat het masker zien in een venster
        plate_text = pytesseract.image_to_string(dark_red_mask, config='--psm 6 --oem 3') #zet image om naar tekst
        plate_text = clean_plate_text(plate_text)
        plate_text = validate_plate_format(plate_text)

        if plate_text:
            current_time = time.time()
            # Controleer of de nummerplaat al binnen 30 seconden gedetecteerd is
            if plate_text in detected_plates:
                last_detected_time = detected_plates[plate_text]
                if current_time - last_detected_time < 30:
                    print(f"Nummerplaat '{plate_text}' al gedetecteerd binnen 30 seconden, overslaan.")
                    continue

            # Verwerk en publiceer de detectie
            if plate_text in detected_plates:
                # Auto rijdt weg
                publish_detection(plate_text)
                log_detection(plate_text, "out")
                del detected_plates[plate_text]
            else:
                # Nieuwe detectie
                publish_detection(plate_text)
                log_detection(plate_text, "in")
                detected_plates[plate_text] = current_time

            # Sla de nummerplaat op
            save_detected_plate(frame, x, y, w, h, plate_text)
            print(f"Nummerplaat gedetecteerd: {plate_text}")

    # Toon de videostream
    cv2.imshow('Nummerplaat Detectie', frame)

    # Sluit met 'q'
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()