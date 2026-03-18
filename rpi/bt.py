# Standard imports
import subprocess
import time

class BT_Interface():

    def __init__(self) -> None:
        pass

    def __execute_command(self, cmd: str, timeout: int) -> str:
        # Execute bluetoothctl command with provided input and return output
        result = subprocess.run(
            ["bluetoothctl"],
            input = cmd,
            text = True,
            capture_output = True,
            timeout = timeout,
        )

        # Verify command executed successfully
        if result.returncode != 0:
            raise RuntimeError(f"Bluetoothctl command failed: {result.stderr.strip()}")
        
        # Return command output
        return result.stdout.strip()
    
    def power_on(self) -> bool:
        # Set return code to False by default
        ret_code = False

        # Build bluetoothctl command to power on Bluetooth
        on_cmd = "power on\n"
        show_cmd = "show\n"
        
        try:
            # Execute commands
            _ = self.__execute_command(on_cmd, timeout = 5)
            output = self.__execute_command(show_cmd, timeout = 5)
            print(output)

            if "Powered: yes" in output:
                ret_code = True

        except RuntimeError:
            # Ignore error and return False if command failed
            pass

        # Return False if command failed and True if command executed successfully
        return ret_code

    def power_off(self) -> bool:
        # Build bluetoothctl command to power off Bluetooth
        off_cmd = "power off\n"
        show_cmd = "show\n"
        
        try:
            # Execute command
            output = self.__execute_command(show_cmd, timeout = 5)
            print(output)
            self.__execute_command(off_cmd, timeout = 5)

            # Return True if command executed successfully
            return True

        except RuntimeError:
            # Return False if command failed
            return False
        
    def pair(self, mac: str) -> bool:
        # Build bluetoothctl command to pair with device
        cmd = f"pair {mac}\n"
        
        try:
            # Execute command
            self.__execute_command(cmd, timeout = 10)

            # Return True if command executed successfully
            return True

        except RuntimeError:
            # Return False if command failed
            return False
        
    def unpair(self, mac: str) -> bool:
        # Build bluetoothctl command to unpair device
        cmd = f"remove {mac}\n"
        
        try:
            # Execute command
            self.__execute_command(cmd, timeout = 10)

            # Return True if command executed successfully
            return True

        except RuntimeError:
            # Return False if command failed
            return False
    
    def trust(self, mac: str) -> bool:
        # Build bluetoothctl command to trust device
        cmd = f"trust {mac}\n"
        
        try:
            # Execute command
            self.__execute_command(cmd, timeout = 10)

            # Return True if command executed successfully
            return True

        except RuntimeError:
            # Return False if command failed
            return False
        
    def untrust(self, mac: str) -> bool:
        # Build bluetoothctl command to untrust device
        cmd = f"untrust {mac}\n"
        
        try:
            # Execute command
            self.__execute_command(cmd, timeout = 10)

            # Return True if command executed successfully
            return True

        except RuntimeError:
            # Return False if command failed
            return False

    def connect(self, mac: str) -> bool:
        # Build bluetoothctl command to connect to device
        cmd = f"connect {mac}\n"
        
        try:
            # Execute command
            self.__execute_command(cmd, timeout = 10)

            # Return True if command executed successfully
            return True

        except RuntimeError:
            # Return False if command failed
            return False
        

    def disconnect(self, mac: str) -> bool:
        # Build bluetoothctl command to disconnect from device
        cmd = f"disconnect {mac}\n"
        
        try:
            # Execute command
            self.__execute_command(cmd, timeout = 10)

            # Return True if command executed successfully
            return True

        except RuntimeError:
            # Return False if command failed
            return False
        
    def info(self, mac: str) -> str:
        # Build bluetoothctl command to get device info
        cmd = f"info {mac}\n"
        
        try:
            # Execute command
            output = self.__execute_command(cmd, timeout = 10)

            # Return device info output if command executed successfully
            return output

        except RuntimeError:
            # Return empty string if command failed
            return ""
        
    def devices(self) -> dict[str, str]:
        # Build bluetoothctl command to list devices
        cmd = "paired-devices\n"
        
        try:
            # Execute command
            output = self.__execute_command(cmd, timeout = 10)

            # Parse output into dictionary
            devices_dict = {}
            lines = output.strip().split('\n')
            for line in lines:
                if line.startswith('Device '):
                    parts = line.split()
                    if len(parts) >= 3:
                        mac = parts[1]
                        name = ' '.join(parts[2:])
                        devices_dict[mac] = name
            return devices_dict

        except RuntimeError:
            # Return empty dict if command failed
            return {}

    def scan(self, duration: int) -> dict[str, str]:
        # Scan for nearby Bluetooth devices for the given duration in seconds
        devices = {}

        try:
            # Start bluetoothctl process
            process = subprocess.Popen(
                ["bluetoothctl"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            # Verify process started successfully
            if process.stdin is None or process.stdout is None:
                return {}

            # Start scan
            process.stdin.write("scan on\n")
            process.stdin.flush()

            # Read scan output until duration expires
            temp = []
            start_time = time.time()
            while time.time() - start_time < duration:
                # Read line from bluetoothctl output
                line = process.stdout.readline()

                # If no line is read, wait briefly and continue
                if not line:
                    time.sleep(0.01)
                    continue

                temp.append(line)

            for line in temp:
                # Strip whitespace from line
                line = line.strip()

                # Parse lines ([NEW] Device AA:BB:CC:DD:EE:FF Device Name)
                if "Device " in line:
                    # Find index of "Device" in parts
                    parts = line.split()
                    try:
                        device_index = parts.index("Device")
                    except ValueError:
                        continue
                    
                    # If there are enough parts after "Device", extract MAC and name
                    if len(parts) > device_index + 2:
                        mac = parts[device_index + 1]
                        name = " ".join(parts[device_index + 2:])
                        devices[mac] = name

            # Stop scan and quit
            process.stdin.write("scan off\n")
            process.stdin.flush()

            try:
                # Wait for process to exit
                process.wait(timeout = 5)

            except subprocess.TimeoutExpired:
                # If process doesn't exit, terminate it
                process.terminate()

            # Return dictionary of found devices if scan completed successfully
            return devices

        except Exception:
            # Return empty dict if scan failed
            return {}