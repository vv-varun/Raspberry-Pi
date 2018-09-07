import sys
import time

import json
import requests

from sense_hat import SenseHat
from modules.config import vi
from modules.gps_poller import gps_poller
from modules.database  import mysql_db

config_broker='1e4bcf9a-3f25-45c3-85e2-f3a486ad18f6.canary.cp.iot.sap'
config_alternate_id_device='Varun_Pi01'
cap_location_update = 'RIL_LocationUpdate'
cap_fuel_update = 'RIL_FuelLevel'
cap_engine_alert = 'RIL_EngineAlert'
config_alternate_id_sensor='Pi_Car'

#sys.path.append('/home/pi/Pi-Projects/modules')
#from database  import mysql_db

# as an additional / non standard module pre-condition: 
# install Paho MQTT lib e.g. from https://github.com/eclipse/paho.mqtt.python
import paho.mqtt.client as mqtt

# Global Variables
sense = SenseHat()

# GPS
gpsp = gps_poller.GpsPoller()
gpsp.start()

global send_data
send_data = False

global prev_time
global fuel_level

# ========================================================================
def get_fuel_estimation(speed) :
	if speed <= 5 : return 1
	elif  speed > 5 and speed <= 10 : return speed / 8
	elif  speed > 10 and speed <= 20 : return speed / 9
	elif  speed > 20 and speed <= 30 : return speed / 10
	elif  speed > 30 and speed <= 40 : return speed / 11
	elif  speed > 40 and speed <= 50 : return speed / 12
	elif  speed > 50 and speed <= 60 : return speed / 14
	elif  speed > 60 : return speed / 16
	else : return 1

def get_current_fuel_value() :
	mysql_cur = mysql_db.get_cursor()
	query = "SELECT FuelLevel FROM `vehicle_data` WHERE VehicleID = 'KA53MB6956'"
	mysql_cur.execute(query)
	row = mysql_cur.fetchone()
	return row[0]

def update_fuel_value(fuel_value) :
	value_set = []
	value_set.append(fuel_value)
	mysql_cur = mysql_db.get_cursor()
	query = "UPDATE `vehicle_data` SET `FuelLevel` = %s WHERE VehicleID = 'KA53MB6956'"
	mysql_cur.execute(query, value_set)
	mysql_db.commit_data()


def send_location_update():
        global fuel_level
        global prev_time
        gps_data = gpsp.get_current_value()
	now = time.time()
	
	measures = {}
	measures["lat"] = gps_data.fix.latitude
	measures["lgt"] = gps_data.fix.longitude
	measures["spd"] = gps_data.fix.speed * 3.6	#mps to kmph
	
	lph = get_fuel_estimation(measures["spd"])		#Get Fuel consumption in lph
	fuel_consumed = lph * (now - prev_time) / 3600
	fuel_level = fuel_level - fuel_consumed
	
	payload = {}
	payload["capabilityAlternateId"] = cap_location_update
	payload["sensorAlternateId"] = config_alternate_id_sensor
	payload["measures"] = measures
	
	result=client.publish(my_publish_topic, json.dumps(payload), qos=0)
	prev_time = now

def send_ignition_status_to_vi(igni_status) :
	gps_data = gpsp.get_current_value()
	
	measures = {}
	measures["lat"] = gps_data.fix.latitude
	measures["lgt"] = gps_data.fix.longitude
	measures["vlu"] = igni_status
	
	payload = {}
	payload["capabilityAlternateId"] = cap_engine_alert
	payload["sensorAlternateId"] = config_alternate_id_sensor
	payload["measures"] = measures
	
def send_fuel_data_to_vi(fuel_data) :
	
	measures = {}
	measures["ltr"] = fuel_data
	
	payload = {}
	payload["capabilityAlternateId"] = cap_fuel_update
	payload["sensorAlternateId"] = config_alternate_id_sensor
	payload["measures"] = measures
	
	result=client.publish(my_publish_topic, json.dumps(payload), qos=0)
	
def on_connect_broker(client, userdata, flags, rc):
	print('Connected to MQTT broker with result code: ' + str(rc))
	sys.stdout.flush()

def on_subscribe(client, obj, message_id, granted_qos):
	print('on_subscribe - message_id: ' + str(message_id) + ' / qos: ' + str(granted_qos))
	sys.stdout.flush()

def on_message(client, obj, msg):
        global send_data
        global fuel_level
        global prev_time
        
	payload = json.loads(msg.payload)
	command = payload["command"]["command"]
	#print(command)
	sys.stdout.flush()
	
	if command == 'Start':
            prev_time = time.time()
            fuel_level = get_current_fuel_value()
            send_ignition_status_to_vi("On")
            send_fuel_data_to_vi(fuel_level)
            send_data = True
            
        elif command == 'Stop':
            send_fuel_data_to_vi(fuel_level)
            send_ignition_status_to_vi("Off")
            update_fuel_value(fuel_level)
            send_data = False
            
        else:
	    print(command)
            #send_location_update()
            #sense.show_message(command,scroll_speed = 0.10)
   
# ========================================================================

# === main starts here ===================================================

config_crt_4_landscape='./eu10cpiotsap.crt'
config_credentials_key='./credentials.key'
config_credentials_crt='./credentials.crt'

broker=config_broker
broker_port=8883

# Add delay of 10 seconds
#time.sleep(1)

my_device=config_alternate_id_device
client=mqtt.Client(client_id=my_device)
client.on_connect=on_connect_broker
client.on_subscribe=on_subscribe
client.on_message=on_message

client.tls_set(config_crt_4_landscape, certfile=config_credentials_crt, keyfile=config_credentials_key)

not_connected=True
while not_connected:
# {
	try:
		client.connect(broker, broker_port, 60)
		not_connected=False
	except:
		print("not connected yet")
		sys.stdout.flush()
		time.sleep(5)
# } while

print("connected to broker now")
sys.stdout.flush()

my_publish_topic='measures/' + my_device
my_subscription_topic='commands/' + my_device
client.subscribe(my_subscription_topic, 0)

client.loop_start()
#client.loop_forever()

# MySQL Connection
mysql_db.open_connection()

counter = 0

while 1 == 1:
    
    if send_data == True :
        print('in main loop')
        send_location_update()
        counter = counter + 1
        
        if counter % 20 == 0 :
            update_fuel_value(fuel_level)
            send_fuel_data_to_vi(fuel_level)
        
	time.sleep(3)
        