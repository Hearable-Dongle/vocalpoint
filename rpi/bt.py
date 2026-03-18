# Standard imports
import subprocess
import time
import select
import datetime
import textwrap
import re

class BT_Interface():

    def __init__(self, logger) -> None:
        # Store logger instance
        self.__logger = logger
        
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

        # Log initialization
        self.__logger.info("BT_Interface initialized")

    def __execute_command(self, cmd: str, timeout: float = 5.0) -> str:
        # Check if process pipes are available
        if self.__process.stdin is None or self.__process.stdout is None:
            raise RuntimeError("Process pipes not available")

        # Send command to bluetoothctl (remove trailing newline since we add it)
        self.__process.stdin.write(cmd + "\n")
        self.__process.stdin.flush()

        # Read output until prompt is reached or timeout expires
        output = []
        prompt_count = 0
        while True:
            # Use select to wait for output with timeout
            ready, _, _ = select.select([self.__process.stdout], [], [], timeout)

            # If no output is ready within timeout, break loop
            if not ready:
                break

            # Read line from bluetoothctl output
            line = self.__process.stdout.readline().strip()

            # If line starts with prompt, increment counter
            if line.startswith("[bluetoothctl]>"):
                prompt_count += 1
                # Wait for second prompt to ensure we get the full response
                if prompt_count >= 2:
                    break
                continue

            # Append line to output list (skip empty lines at the end)
            if line:
                output.append(line)

        # Join output lines into single string and return
        return "\n".join(output)
    
    def __strip_ansi(self, text: str) -> str:
        # Remove ANSI escape codes from text
        ansi_escape = re.compile(r'\x1b\[[0-9;]*m|\[K')
        return ansi_escape.sub('', text)
    
    def __log_failure(self, operation: str, device: str = "", output: str = "", error: str = "") -> None:
        # Log failure with context
        log_entry = f"\nOperation: {operation}"
        if device:
            log_entry += f"\nDevice: {device}"
        if output:
            # Strip ANSI codes and indent output
            cleaned_output = self.__strip_ansi(output)
            indented_output = textwrap.indent(cleaned_output, "\t")
            log_entry += f"\nOutput:\n{indented_output}"
        if error:
            # Strip ANSI codes and indent error
            cleaned_error = self.__strip_ansi(error)
            indented_error = textwrap.indent(cleaned_error, "\t")
            log_entry += f"\nError:\n{indented_error}"
        
        self.__logger.error(log_entry)
    
    
    def power_on(self) -> bool:
        # Set return code to False by default
        ret_code = False

        # Build bluetoothctl command to power on Bluetooth
        on_cmd = "power on"
        show_cmd = "show"
        
        try:
            # Execute commands
            _ = self.__execute_command(on_cmd)
            output = self.__execute_command(show_cmd)

            # Verify output
            if "Powered: yes" in output:
                ret_code = True
            else:
                self.__log_failure("power_on", output=output)

        except RuntimeError as e:
            # Ignore error and return False if command failed
            self.__log_failure("power_on", error=str(e))

        # Return False if command failed and True if command executed successfully
        return ret_code

    def power_off(self) -> bool:
        # Set return code to False by default
        ret_code = False

        # Build bluetoothctl command to power off Bluetooth
        off_cmd = "power off"
        show_cmd = "show"
        
        try:
            # Execute commands
            _ = self.__execute_command(off_cmd)
            output = self.__execute_command(show_cmd)

            # Verify output
            if "Powered: no" in output:
                ret_code = True
            else:
                self.__log_failure("power_off", output=output)

        except RuntimeError as e:
            # Ignore error and return False if command failed
            self.__log_failure("power_off", error=str(e))

        # Return False if command failed and True if command executed successfully
        return ret_code
    
    def agent_on(self) -> bool:
        # Set return code to False by default
        ret_code = False

        # Build bluetoothctl command to enable agent
        cmd = "agent on"
        
        try:
            # Execute command
            output = self.__execute_command(cmd)

            # Verify output
            if "Agent registered" in output or "Agent is already registered" in output:
                ret_code = True
            else:
                self.__log_failure("agent_on", output=output)

        except RuntimeError as e:
            # Ignore error and return False if command failed
            self.__log_failure("agent_on", error=str(e))

        # Return False if command failed and True if command executed successfully
        return ret_code
    
    def agent_off(self) -> bool:
        # Set return code to False by default
        ret_code = False

        # Build bluetoothctl command to enable agent
        cmd = "agent off"
        
        try:
            # Execute command
            output = self.__execute_command(cmd)

            # Verify output
            if "Agent unregistered" in output or "Agent is not registered" in output:
                ret_code = True
            else:
                self.__log_failure("agent_off", output=output)

        except RuntimeError as e:
            # Ignore error and return False if command failed
            self.__log_failure("agent_off", error=str(e))

        # Return False if command failed and True if command executed successfully
        return ret_code

    def pair(self, mac: str) -> bool:
        # Set return code to False by default
        ret_code = False

        # Build bluetoothctl command to pair with device
        cmd = f"pair {mac}"
        
        try:
            # Execute command
            output = self.__execute_command(cmd)
            print(output)

            # Verify output
            if "Paired: yes" in output or "Pairing successful" in output:
                ret_code = True
            else:
                self.__log_failure("pair", device=mac, output=output)

        except RuntimeError as e:
            # Ignore error and return False if command failed
            self.__log_failure("pair", device=mac, error=str(e))

        # Return False if command failed and True if command executed successfully
        return ret_code
        
    def unpair(self, mac: str) -> bool:
        # Set return code to False by default
        ret_code = False

        # Build bluetoothctl command to unpair device
        cmd = f"remove {mac}"
        
        try:
            # Execute command
            output = self.__execute_command(cmd)

            # Verify output
            if "Device has been removed" in output or "Device is not paired" in output:
                ret_code = True
            else:
                self.__log_failure("unpair", device=mac, output=output)

        except RuntimeError as e:
            # Ignore error and return False if command failed
            self.__log_failure("unpair", device=mac, error=str(e))

        # Return False if command failed and True if command executed successfully
        return ret_code
    
    def trust(self, mac: str) -> bool:
        # Set return code to False by default
        ret_code = False

        # Build bluetoothctl command to trust device
        cmd = f"trust {mac}"
        
        try:
            # Execute command
            output = self.__execute_command(cmd)
            print(output)

            # Verify output
            if "Trusted: yes" in output or "Device is already trusted" in output:
                ret_code = True
            else:
                self.__log_failure("trust", device=mac, output=output)

        except RuntimeError as e:
            # Return False if command failed
            self.__log_failure("trust", device=mac, error=str(e))
            return False

        # Return False if command failed and True if command executed successfully
        return ret_code

    def untrust(self, mac: str) -> bool:
        # Set return code to False by default
        ret_code = False

        # Build bluetoothctl command to untrust device
        cmd = f"untrust {mac}"
        
        try:
            # Execute command
            output = self.__execute_command(cmd)

            # Verify output
            if "Trusted: no" in output or "Device is not trusted" in output:
                ret_code = True
            else:
                self.__log_failure("untrust", device=mac, output=output)

        except RuntimeError as e:
            # Ignore error and return False if command failed
            self.__log_failure("untrust", device=mac, error=str(e))

        # Return False if command failed and True if command executed successfully
        return ret_code

    def connect(self, mac: str) -> bool:
        # Set return code to False by default
        ret_code = False

        # Build bluetoothctl command to connect to device
        cmd = f"connect {mac}"
        
        try:
            # Execute command
            output = self.__execute_command(cmd)
            print(output)

            # Verify output
            if "Connection successful" in output or "Already connected" in output:
                ret_code = True
            else:
                self.__log_failure("connect", device=mac, output=output)

        except RuntimeError as e:
            # Ignore error and return False if command failed
            self.__log_failure("connect", device=mac, error=str(e))

        # Return False if command failed and True if command executed successfully
        return ret_code

    def disconnect(self, mac: str) -> bool:
        # Set return code to False by default
        ret_code = False

        # Build bluetoothctl command to disconnect from device
        cmd = f"disconnect {mac}"
        
        try:
            # Execute command
            output = self.__execute_command(cmd)

            # Verify output
            if "Successful disconnected" in output or "Already disconnected" in output:
                ret_code = True
            else:
                self.__log_failure("disconnect", device=mac, output=output)

        except RuntimeError as e:
            # Ignore error and return False if command failed
            self.__log_failure("disconnect", device=mac, error=str(e))

        # Return False if command failed and True if command executed successfully
        return ret_code
        
    def info(self, mac: str) -> str:
        # Set return value to empty string by default
        ret_val = ""

        # Build bluetoothctl command to get device info
        cmd = f"info {mac}"
        
        try:
            # Execute command
            ret_val = self.__execute_command(cmd, timeout = 2.0)

        except RuntimeError as e:
            # Return empty string if command failed
            self.__log_failure("info", device=mac, error=str(e))

        # Return device info if command executed successfully and empty string if command failed
        return ret_val
        
    def devices(self) -> dict[str, str]:
        # Set return value to empty dict by default
        ret_val = {}

        # Build bluetoothctl command to list devices
        cmd = "paired-devices"
        
        try:
            # Execute command
            output = self.__execute_command(cmd, timeout = 2.0)

            # Parse output into dictionary
            lines = output.strip().split('\n')
            for line in lines:
                if line.startswith('Device '):
                    parts = line.split()
                    if len(parts) >= 3:
                        mac = parts[1]
                        name = ' '.join(parts[2:])
                        ret_val[mac] = name

        except RuntimeError as e:
            # Return empty dict if command failed
            self.__log_failure("devices", error=str(e))

        # Return paired devices if command executed successfully and empty dict otherwise
        return ret_val

    def scan(self, duration: int) -> dict[str, str]:
        # Scan for nearby Bluetooth devices for the given duration in seconds
        devices = {}

        try:
            # Start scan
            self.__process.stdin.write("scan on\n")
            self.__process.stdin.flush()

            # Read scan output until duration expires
            output = []
            start_time = time.time()
            while time.time() - start_time < duration:
                # Read line from bluetoothctl output
                line = self.__process.stdout.readline()

                # If no line is read, wait briefly and continue
                if not line:
                    time.sleep(0.01)
                    continue

                output.append(line)

            # Stop scan and quit
            self.__process.stdin.write("scan off\n")
            self.__process.stdin.flush()

            for line in output:
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

        except Exception as e:
            # Return empty dict if scan failed
            self.__log_failure("scan", error=str(e))
            devices = {}
        
        # Return dictionary of found devices if scan completed successfully
        return devices
