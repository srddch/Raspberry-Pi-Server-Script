import RPi.GPIO as GPIO
import socket
import threading
import time

in1 = 24
in2 = 23
en = 25
temp1 = 1

SEED_SENSOR_PIN = 17

HOST = ''
PORT = 65432
BUFFER_SIZE = 1024

seed_empty = False
last_seed_state = None
seed_check_interval = 0.5

GPIO.setmode(GPIO.BCM)
GPIO.setup(in1, GPIO.OUT)
GPIO.setup(in2, GPIO.OUT)
GPIO.setup(en, GPIO.OUT)
GPIO.setup(SEED_SENSOR_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

GPIO.output(in1, GPIO.LOW)
GPIO.output(in2, GPIO.LOW)
p = GPIO.PWM(en, 1000)
p.start(12.5)

print("\n")
print("Motor control server started...")
print("Waiting for commands from Android app...")
print("\n")


def check_seed_status():
    global seed_empty, last_seed_state

    current_state = GPIO.input(SEED_SENSOR_PIN)

    if current_state != last_seed_state:
        last_seed_state = current_state

        if current_state == GPIO.HIGH:
            seed_empty = True
            print("Seed status: Empty (sensor blocked)")
            return "SEED_STATUS:EMPTY"
        else:
            seed_empty = False
            print("Seed status: Available (sensor uncovered)")
            return "SEED_STATUS:NORMAL"

    return None


def seed_monitor_thread():
    while True:
        try:
            status_message = check_seed_status()
            if status_message and current_connection:
                try:
                    current_connection.sendall((status_message + "\n").encode())
                    print(f"Sent seed status: {status_message}")
                except:
                    print("Failed to send status update")

            time.sleep(seed_check_interval)
        except Exception as e:
            print(f"Seed monitor error: {e}")
            time.sleep(1)


def control_motor(command):
    global temp1

    if command == "START":
        if seed_empty:
            print("Cannot start: No seeds in hopper!")
            return "ERROR:NO_SEEDS"

        print("Motor running")
        p.ChangeDutyCycle(100)
        if temp1 == 1:
            GPIO.output(in1, GPIO.HIGH)
            GPIO.output(in2, GPIO.LOW)
            print("Direction: Forward")
        else:
            GPIO.output(in1, GPIO.LOW)
            GPIO.output(in2, GPIO.HIGH)
            print("Direction: Backward")
        return "OK"

    elif command == "STOP":
        print("Motor stopped")
        GPIO.output(in1, GPIO.LOW)
        GPIO.output(in2, GPIO.LOW)
        return "OK"

    elif command == "FORWARD":
        print("Direction set to Forward")
        GPIO.output(in1, GPIO.HIGH)
        GPIO.output(in2, GPIO.LOW)
        temp1 = 1
        return "OK"

    elif command == "BACKWARD":
        print("Direction set to Backward")
        GPIO.output(in1, GPIO.LOW)
        GPIO.output(in2, GPIO.HIGH)
        temp1 = 0
        return "OK"

    elif command == "LOW":
        print("Speed: Low")
        p.ChangeDutyCycle(20)
        return "OK"

    elif command == "MEDIUM":
        print("Speed: Medium")
        p.ChangeDutyCycle(50)
        return "OK"

    elif command == "HIGH":
        print("Speed: High")
        p.ChangeDutyCycle(75)
        return "OK"

    elif command == "EXIT":
        print("Cleaning up GPIO")
        GPIO.cleanup()
        return "EXIT"

    else:
        print(f"<<< Unknown command: {command} >>>")
        return "ERROR"


current_connection = None
connection_lock = threading.Lock()


def handle_client(conn, addr):
    global current_connection

    with connection_lock:
        current_connection = conn

    print('Connected by', addr)
    try:
        initial_status = "SEED_STATUS:EMPTY" if seed_empty else "SEED_STATUS:NORMAL"
        conn.sendall((initial_status + "\n").encode())
        print(f"Sent initial seed status: {initial_status}")

        while True:
            data = conn.recv(BUFFER_SIZE).decode().strip()
            if not data:
                break

            print("Received command:", data)
            response = control_motor(data)

            if response == "EXIT":
                break

            conn.sendall((response + "\n").encode())

    except ConnectionResetError:
        print("Client disconnected unexpectedly")
    except Exception as e:
        print(f"Client handling error: {e}")
    finally:
        with connection_lock:
            if current_connection == conn:
                current_connection = None
        conn.close()
        print('Connection closed')


def run_server():
    seed_thread = threading.Thread(target=seed_monitor_thread)
    seed_thread.daemon = True
    seed_thread.start()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen()
        print(f"Listening on port {PORT}...")

        try:
            while True:
                conn, addr = s.accept()
                client_thread = threading.Thread(target=handle_client, args=(conn, addr))
                client_thread.daemon = True
                client_thread.start()
                print(f"Active connections: {threading.active_count() - 1}")

        except KeyboardInterrupt:
            print("\nServer shutting down...")
        except Exception as e:
            print(f"Server error: {e}")
        finally:
            s.close()
            GPIO.cleanup()
            print("Server stopped")


if __name__ == "__main__":
    initial_status = check_seed_status()
    if initial_status:
        print(f"Initial seed status: {initial_status}")

    run_server()