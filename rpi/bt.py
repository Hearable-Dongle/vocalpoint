# Standard imports
import subprocess
import time
import select

class BT_Interface():

    def __init__(self) -> None:
        # Start bluetoothctl process
        self.__process = subprocess.Popen(
            ["bluetoothctl"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        # Consume initial prompt
        self.__process.stdout.readline()

    def __execute_command(self, cmd: str) -> str:
        if self.__process.stdin is None or self.__process.stdout is None:
            raise RuntimeError("Process pipes not available")

        self.__process.stdin.write(cmd + "\n")
        self.__process.stdin.flush()

        output = []
        line_timeout = 1.0  # seconds to wait for each line

        while True:
            ready, _, _ = select.select([self.__process.stdout], [], [], line_timeout)

            if not ready:
                # No more output within timeout
                break

            line = self.__process.stdout.readline().strip()
            if line.startswith("[bluetoothctl]>"):
                break
            output.append(line)

        return "\n".join(output)
    
    def power_on(self) -> bool:
        # Set return code to False by default
        ret_code = False

        # Build bluetoothctl command to power on Bluetooth
        on_cmd = "power on\n"
        show_cmd = "show\n"
        
        try:
            # Execute commands
            _ = self.__execute_command(on_cmd)
            output = self.__execute_command(show_cmd)

            # Verify output
            if "Powered: yes" in output:
                ret_code = True

        except RuntimeError:
            # Ignore error and return False if command failed
            pass

        # Return False if command failed and True if command executed successfully
        return ret_code

    def power_off(self) -> bool:
        # Set return code to False by default
        ret_code = False

        # Build bluetoothctl command to power off Bluetooth
        off_cmd = "power off\n"
        show_cmd = "show\n"
        
        try:
            # Execute commands
            _ = self.__execute_command(off_cmd)
            output = self.__execute_command(show_cmd)

            # Verify output
            if "Powered: no" in output:
                ret_code = True

        except RuntimeError:
            # Ignore error and return False if command failed
            pass

        # Return False if command failed and True if command executed successfully
        return ret_code
        
    def pair(self, mac: str) -> bool:
        # Build bluetoothctl command to pair with device
        cmd = f"pair {mac}\n"
        
        try:
            # Execute command
            self.__execute_command(cmd)

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
            self.__execute_command(cmd)

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
            self.__execute_command(cmd)

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
            self.__execute_command(cmd)

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
            self.__execute_command(cmd)

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
            self.__execute_command(cmd)

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
            output = self.__execute_command(cmd)

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
            output = self.__execute_command(cmd)

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