import tkinter as tk
from tkinter import ttk
import paho.mqtt.client as mqtt
import json
from datetime import datetime

# MQTT-configuratie
mqtt_broker = "broker.emqx.io"
mqtt_port = 1883
mqtt_topic = "testtopic/42"
mqtt_history_topic = "testtopic/history"

# Functie om de ontvangen berichten te verwerken
def on_message(client, userdata, msg):
    try:
        # Ontvang JSON-bericht
        message = json.loads(msg.payload.decode())
        
        # Als het een historisch bericht is, voeg het toe aan de GUI
        if "plate_text" in message and "timestamp" in message:
            plate_text = message["plate_text"]
            timestamp = format_timestamp(message["timestamp"])
            display_message(plate_text, timestamp)
    except Exception as e:
        print(f"Fout bij het verwerken van bericht: {e}")

# Functie om de timestamp te formatteren
def format_timestamp(timestamp):
    try:
        # Converteer UNIX-tijdstempel naar datetime-object
        dt = datetime.fromtimestamp(float(timestamp))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError) as e:
        print(f"Fout bij het converteren van timestamp: {e}")
        return str(timestamp)  # Geef de originele waarde terug bij een fout

# Functie om het bericht in de GUI te tonen
def display_message(plate_text, timestamp):
    # Voeg een nieuwe rij toe aan de treeview (tabel)
    tree.insert("", "end", values=(plate_text, timestamp))

# Functie om de historische gegevens op te vragen van de server
def request_history():
    # Stuur een verzoek naar de broker om de historische gegevens op te halen
    client.publish(mqtt_history_topic, "request_history")
    print("Verzoek voor historische gegevens verzonden.")

# Instellen van de GUI
root = tk.Tk()
root.title("Nummerplaat Detectie")

# Maak een frame voor de tabel
frame = ttk.Frame(root)
frame.pack(padx=10, pady=10)

# Maak een Treeview widget (tabel)
columns = ("Nummerplaat", "Tijd")
tree = ttk.Treeview(frame, columns=columns, show="headings")
tree.heading("Nummerplaat", text="Nummerplaat")
tree.heading("Tijd", text="Tijd")

# Voeg de Treeview toe aan de GUI
tree.pack()

# Maak een 'Refresh' knop die historische gegevens opvraagt
refresh_button = ttk.Button(root, text="Refresh", command=request_history)
refresh_button.pack(pady=10)

# Instellen van de MQTT client
client = mqtt.Client()

# Verbind met de MQTT broker
client.connect(mqtt_broker, mqtt_port, 60)

# Stel de callback voor ontvangen berichten in
client.on_message = on_message

# Subscribe op het juiste topic
client.subscribe(mqtt_topic)
client.subscribe(mqtt_history_topic)

# Start de MQTT loop in een aparte thread
client.loop_start()

# Start de GUI
root.mainloop()
