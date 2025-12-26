#!/usr/bin/env python3

import argparse
import ipaddress
import json
import os
import sys
import time
import pwd
import grp
import stat
from smbus2 import SMBus, i2c_msg
import paho.mqtt.client as mqtt


TARGET_BUS_NAME = "CH341 I2C USB bus"

AHT20_ADDR = 0x38
BMP280_ADDR = 0x77


def find_i2c_bus():
    base = "/sys/bus/i2c/devices"
    for entry in os.listdir(base):
        if not entry.startswith("i2c-"):
            continue
        name_file = os.path.join(base, entry, "name")
        try:
            with open(name_file, "r") as f:
                name = f.read().strip()
            if TARGET_BUS_NAME in name:
                return int(entry.split("-")[1])
        except IOError:
            pass
    return None


def check_i2c_permissions(devnode):
    # Root always succeeds
    if os.geteuid() == 0:
        return

    # Fast path
    if os.access(devnode, os.R_OK | os.W_OK):
        return

    st = os.stat(devnode)
    mode = st.st_mode
    uid = os.geteuid()
    user = pwd.getpwuid(uid).pw_name

    print(f"ERROR: No read/write access to {devnode}")

    # Check owner permissions
    if st.st_uid == uid and (mode & stat.S_IRUSR) and (mode & stat.S_IWUSR):
        print("You are the device owner but access still failed.")
        print("Check SELinux/AppArmor.")
        sys.exit(1)

    # Check group permissions
    if (mode & stat.S_IRGRP) and (mode & stat.S_IWGRP):
        group = grp.getgrgid(st.st_gid).gr_name

        user_groups = {g.gr_name for g in grp.getgrall() if user in g.gr_mem}
        primary_group = grp.getgrgid(pwd.getpwuid(uid).pw_gid).gr_name
        user_groups.add(primary_group)

        if group not in user_groups:
            print(f"The device is writable by group '{group}'.")
            print("Add yourself with:")
            print(f"  sudo usermod -aG {group} {user}")
            print("Then log out and back in.")
        else:
            print(f"You are already in group '{group}', but access still failed.")
            print("Check SELinux/AppArmor or container restrictions.")
        sys.exit(1)

    # Check world permissions
    if (mode & stat.S_IROTH) and (mode & stat.S_IWOTH):
        print("Device is world-writable, but access still failed.")
        print("This is unusual; check security policies.")
        sys.exit(1)

    print("The device has no read/write permissions for your user or group.")
    print("Check udev rules for i2c-dev.")
    sys.exit(1)


def check_dev_node(busno):
    dev = f"/dev/i2c-{busno}"
    if not os.path.exists(dev):
        print(f"ERROR: {dev} not found.")
        print("Hint: sudo modprobe i2c-dev")
        sys.exit(1)

    check_i2c_permissions(dev)
    return dev


# ---------------- AHT20 ----------------

def read_aht20(bus):
    # Trigger measurement
    bus.write_i2c_block_data(AHT20_ADDR, 0xAC, [0x33, 0x00])
    time.sleep(0.08)

    data = bus.read_i2c_block_data(AHT20_ADDR, 0x00, 6)

    if data[0] & 0x80:
        raise RuntimeError("AHT20: measurement not ready")

    raw_hum = ((data[1] << 16) | (data[2] << 8) | data[3]) >> 4
    raw_tmp = ((data[3] & 0x0F) << 16) | (data[4] << 8) | data[5]

    humidity = raw_hum * 100.0 / (1 << 20)
    temperature = raw_tmp * 200.0 / (1 << 20) - 50.0

    return temperature, humidity


# ---------------- BMP280 ----------------

def bmp280_read_calibration(bus):
    calib = bus.read_i2c_block_data(BMP280_ADDR, 0x88, 24)

    def u16(i):
        return calib[i] | (calib[i + 1] << 8)

    def s16(i):
        v = u16(i)
        return v - 65536 if v & 0x8000 else v

    return {
        "T1": u16(0),
        "T2": s16(2),
        "T3": s16(4),
        "P1": u16(6),
        "P2": s16(8),
        "P3": s16(10),
        "P4": s16(12),
        "P5": s16(14),
        "P6": s16(16),
        "P7": s16(18),
        "P8": s16(20),
        "P9": s16(22),
    }


def bmp280_read_raw(bus):
    data = bus.read_i2c_block_data(BMP280_ADDR, 0xF7, 6)
    adc_p = (data[0] << 12) | (data[1] << 4) | (data[2] >> 4)
    adc_t = (data[3] << 12) | (data[4] << 4) | (data[5] >> 4)
    return adc_t, adc_p


def bmp280_compensate(adc_t, adc_p, c):
    var1 = (((adc_t >> 3) - (c["T1"] << 1)) * c["T2"]) >> 11
    var2 = (((((adc_t >> 4) - c["T1"]) * ((adc_t >> 4) - c["T1"])) >> 12) * c["T3"]) >> 14
    t_fine = var1 + var2
    temperature = (t_fine * 5 + 128) >> 8

    var1 = t_fine - 128000
    var2 = var1 * var1 * c["P6"]
    var2 += (var1 * c["P5"]) << 17
    var2 += c["P4"] << 35
    var1 = ((var1 * var1 * c["P3"]) >> 8) + ((var1 * c["P2"]) << 12)
    var1 = (((1 << 47) + var1) * c["P1"]) >> 33

    if var1 == 0:
        pressure = 0
    else:
        p = 1048576 - adc_p
        p = (((p << 31) - var2) * 3125) // var1
        var1 = (c["P9"] * (p >> 13) * (p >> 13)) >> 25
        var2 = (c["P8"] * p) >> 19
        pressure = ((p + var1 + var2) >> 8) + (c["P7"] << 4)

    return temperature / 100.0, pressure / 256.0


def read_bmp280(bus):
    # ctrl_meas: temp+press oversampling x1, normal mode
    bus.write_byte_data(BMP280_ADDR, 0xF4, 0x27)
    # config: standby 0.5ms, filter off
    bus.write_byte_data(BMP280_ADDR, 0xF5, 0x00)
    time.sleep(0.05)

    calib = bmp280_read_calibration(bus)
    adc_t, adc_p = bmp280_read_raw(bus)
    return bmp280_compensate(adc_t, adc_p, calib)


# ---------------- MQTT ----------------

DISCOVERY_PREFIX = "homeassistant"
NODE_ID = "barrbro_sensors_01"
COMPONENT = "sensor"


def config_topic(object_id):
    return f"{DISCOVERY_PREFIX}/{COMPONENT}/{NODE_ID}/{object_id}/config"


def state_topic(object_id):
    return f"{DISCOVERY_PREFIX}/{COMPONENT}/{NODE_ID}/{object_id}/state"


DISCOVERY = {
    "temperature": {
        "name": "Barrbro Temperature",
        "device_class": "temperature",
        "unit": "°C",
    },
    "humidity": {
        "name": "Barrbro Humidity",
        "device_class": "humidity",
        "unit": "%",
    },
    "pressure": {
        "name": "Barrbro Pressure",
        "device_class": "pressure",
        "unit": "hPa",
    },
}


def publish_json(client, topic, payload, retain=False):
    payload_str = json.dumps(payload)
    result = client.publish(topic, payload_str, retain=retain)
    result.wait_for_publish()
    if result.rc != mqtt.MQTT_ERR_SUCCESS:
        print(f"Publish error on {topic}: rc={result.rc}")


def main(broker_ip, test_only):
    busno = find_i2c_bus()
    if busno is None:
        print("ERROR: CH341 I2C USB bus not found")
        sys.exit(1)

    check_dev_node(busno)

    with SMBus(busno) as bus:
        aht_temp, aht_hum = read_aht20(bus)
        bmp_temp, bmp_press_pa = read_bmp280(bus)

    bmp_press_hpa = bmp_press_pa / 100.0

    if test_only:
        print(f"AHT20:")
        print(f"  Temperature: {aht_temp:.2f} °C")
        print(f"  Humidity:    {aht_hum:.2f} %RH")

        print(f"BMP280:")
        print(f"  Temperature: {bmp_temp:.2f} °C")
        print(f"  Pressure:    {bmp_press_pa / 100:.2f} hPa")
        return

    client = mqtt.Client(protocol=mqtt.MQTTv311, callback_api_version=2)
    client.connect(broker_ip, 1883, keepalive=60)
    client.loop_start()

    # ---- Discovery ----
    for object_id, meta in DISCOVERY.items():
        payload = {
            "name": meta["name"],
            "state_topic": state_topic(object_id),
            "unique_id": f"{NODE_ID}_{object_id}",
            "device_class": meta["device_class"],
            "unit_of_measurement": meta["unit"],
            "expire_after": 3600,
            "device": {
                "identifiers": [NODE_ID],
                "name": "Barometer",
                "manufacturer": "Custom",
                "model": "AHT20 + BMP280",
            },
        }
        publish_json(client, config_topic(object_id), payload, retain=True)

    time.sleep(1)

    # ---- State updates ----
    client.publish(state_topic("temperature"), f"{aht_temp:.2f}").wait_for_publish()
    client.publish(state_topic("humidity"), f"{aht_hum:.2f}").wait_for_publish()
    client.publish(state_topic("pressure"), f"{bmp_press_hpa:.2f}").wait_for_publish()

    time.sleep(0.5)
    client.loop_stop()
    client.disconnect()


def valid_ip(value):
    try:
        ipaddress.ip_address(value)
        return value
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{value}' is not a valid IP address")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Barrbro, a barometer MQTT client"
    )
    parser.add_argument(
        "--broker-ip",
        type=valid_ip,
        help="IP address of the MQTT broker (required, unless test)."
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Print the measured values from the sensors and then quit"
    )

    args = parser.parse_args()

    if not args.test and not args.broker_ip:
        parser.error("--broker-ip is required unless --test is specified")

    main(args.broker_ip, args.test)
