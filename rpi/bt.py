# Standard imports
from pathlib import Path
from typing import Optional
import logging
import re
import subprocess
import textwrap
import time

# Third-party imports
from dbus.mainloop.glib import DBusGMainLoop, threads_init
import dbus
import dbus.service


class BT_Interface:
    """
    Interface for Bluetooth device control via D-Bus and audio routing to PulseAudio.
    """

    # Define threshold for marking hardfault conditions based on consecutive operation failures
    __FAILURE_THRESHOLD: int = 5

    # D-Bus service and object path constants
    __BLUEZ_SERVICE: str = 'org.bluez'
    __ADAPTER_PATH: str = '/org/bluez/hci0'
    __DEVICE_PREFIX: str = '/org/bluez/hci0/dev_'

    def __init__(self, logger: logging.Logger) -> None:
        """
        Initialize Bluetooth interface with D-Bus connection.
        
        Parameters
        ----------
        logger : logging.Logger
            Logger instance for recording Bluetooth events and errors
            
        Returns
        -------
        None
        """
        # Initialize instance variables
        self.__logger = logger
        self.__pulseaudio_sink: Optional[dbus.Interface] = None
        self.__paplay_process: Optional[subprocess.Popen[bytes]] = None
        self.__connected_mac: Optional[str] = None

        # Define hardfault flag and error tracking
        self.__hardfault: bool = False
        self.__consecutive_failures: int = 0
        
        # Initialize D-Bus event loop for asynchronous operations
        DBusGMainLoop(set_as_default=True)
        threads_init()
        
        # Attempt to establish D-Bus connection and get Bluetooth adapter
        try:
            # Connect to system D-Bus
            self.__bus = dbus.SystemBus()

            # Get D-Bus object for the Bluetooth adapter at /org/bluez/hci0
            adapter_obj = self.__bus.get_object(self.__BLUEZ_SERVICE, self.__ADAPTER_PATH)

            # Wrap object in D-Bus interface for method calls
            self.__adapter =  dbus.Interface(adapter_obj, self.__BLUEZ_SERVICE + '.Adapter1')

            # Log successful initialization
            self.__logger.info("BT Interface initialized with D-Bus API")

        # Catch any D-Bus exceptions during initialization and log them
        except dbus.exceptions.DBusException as e:

            # Log the error with detailed context and set hardfault to signal failure
            self.__logger.error(f"Failed to initialize D-Bus: {str(e)}")

            # Mark as hardfault since Bluetooth interface cannot function without D-Bus connection
            self.__hardfault = True
    
    def __get_device(self, mac: str) -> Optional[dbus.Interface]:
        """
        Get device object interface for a given MAC address.
        
        Parameters
        ----------
        mac : str
            Bluetooth device MAC address (e.g., "BC:87:FA:57:47:0E")
            
        Returns
        -------
        dbus.Interface
            D-Bus interface for the Bluetooth device
        """

        # Set device to None by default in case of failure
        device = None

        # Construct D-Bus device path from MAC address, replacing colons with underscores
        device_path = self.__DEVICE_PREFIX + mac.replace(':', '_').upper()

        # Attempt to get the D-Bus object for the device and wrap it in an interface
        try:
            # Get D-Bus object for the device
            device_obj = self.__bus.get_object(self.__BLUEZ_SERVICE, device_path)

            # Wrap object in D-Bus interface for method calls
            device = dbus.Interface(device_obj, self.__BLUEZ_SERVICE + '.Device1')

        # Catch D-Bus exceptions when trying to access the device and log them with context
        except dbus.exceptions.DBusException as e:

            # Log the error with detailed context and re-raise the exception to signal failure
            self.__logger.error(f"Failed to get device {mac} at path {device_path}: {str(e)}")

        finally:
            # Return the device interface or None if retrieval failed
            return device
    
    def power_on(self) -> bool:
        """
        Power on the Bluetooth adapter.

        Parameters
        ----------
        None
        
        Returns
        -------
        bool
            True if adapter powered on successfully, False otherwise
        """

        # Set return value to False by default in case of failure
        ret_code = False

        # Attempt to power on the Bluetooth adapter via D-Bus
        try:
            # Get D-Bus Properties interface for the Bluetooth adapter
            adapter_props = dbus.Interface(
                self.__bus.get_object(self.__BLUEZ_SERVICE, self.__ADAPTER_PATH),
                'org.freedesktop.DBus.Properties'
            )
            
            # Set Powered property to True via D-Bus
            adapter_props.Set(self.__BLUEZ_SERVICE + '.Adapter1', 'Powered', dbus.Boolean(True))
            
            # Verify that Powered property was successfully set
            powered = adapter_props.Get(self.__BLUEZ_SERVICE + '.Adapter1', 'Powered')
            if powered:
                # Log successful power on
                self.__logger.info("Bluetooth adapter powered on")

                # Set return value to True on success
                ret_code = True
            
            else:
                # Log failure to power on
                self.__logger.error("Adapter failed to power on")
        
        # Catch D-Bus exceptions during power on attempt
        except dbus.exceptions.DBusException as e:
            # Log unsuccessful power on
            self.__logger.error(f"Power on failed: {str(e)}")

        finally:
            # Return the result of the power on attempt
            return ret_code
    
    def power_off(self) -> bool:
        """
        Power off the Bluetooth adapter.

        Parameters
        ----------
        None
        
        Returns
        -------
        bool
            True if adapter powered off successfully, False otherwise
        """

        # Set return value to False by default in case of failure
        ret_code = False

        # Attempt to power off the Bluetooth adapter via D-Bus
        try:
            # Get D-Bus Properties interface for the Bluetooth adapter
            adapter_props = dbus.Interface(
                self.__bus.get_object(self.__BLUEZ_SERVICE, self.__ADAPTER_PATH),
                'org.freedesktop.DBus.Properties'
            )

            # Set Powered property to False via D-Bus
            adapter_props.Set(self.__BLUEZ_SERVICE + '.Adapter1', 'Powered', dbus.Boolean(False))
            
            # Verify that Powered property was successfully cleared
            powered = adapter_props.Get(self.__BLUEZ_SERVICE + '.Adapter1', 'Powered')
            if not powered:
                # Log successful power off
                self.__logger.info("Bluetooth adapter powered off")
                
                # Set return value to True on success
                ret_code = True
            
            else:
                # Log failure to power off
                self.__logger.error("Adapter failed to power off")
        
        # Catch D-Bus exceptions during power on attempt
        except dbus.exceptions.DBusException as e:
            # Log unsuccessful power off
            self.__logger.error(f"power_off failed: {str(e)}")
        
        finally:
            # Return the result of the power off attempt
            return ret_code
    
    def agent_on(self) -> bool:
        """
        Enable pairing on the Bluetooth adapter.

        Parameters
        ----------
        None
        
        Returns
        -------
        bool
            True if pairing enabled successfully, False otherwise
        """

        # Set return value to False by default in case of failure
        ret_code = False

        # Attempt to enable pairing mode on the Bluetooth adapter via D-Bus
        try:
            # Get D-Bus Properties interface for the Bluetooth adapter
            adapter_props = dbus.Interface(
                self.__bus.get_object(self.__BLUEZ_SERVICE, self.__ADAPTER_PATH),
                'org.freedesktop.DBus.Properties'
            )

            # Set Pairable property to True to enable pairing mode
            adapter_props.Set(self.__BLUEZ_SERVICE + '.Adapter1', 'Pairable', dbus.Boolean(True))
            
            # Verify that Pairable property was successfully set
            pairable = adapter_props.Get(self.__BLUEZ_SERVICE + '.Adapter1', 'Pairable')
            if pairable:
                # Log successful enabling of pairing mode
                self.__logger.info("Bluetooth pairing enabled")

                # Set return value to True on success
                ret_code = True
            
            else:
                # Log failure to enable pairing
                self.__logger.error("Failed to enable pairing")
        
        # Catch D-Bus exceptions during pairing mode enable attempt
        except dbus.exceptions.DBusException as e:
            # Log unsuccessful attempt to enable pairing
            self.__logger.error(f"agent_on failed: {str(e)}")

        finally:
            # Return the result of the pairing mode enable attempt
            return ret_code
    
    def agent_off(self) -> bool:
        """
        Disable pairing on the Bluetooth adapter.

        Parameters
        ----------
        None
        
        Returns
        -------
        bool
            True if pairing disabled successfully, False otherwise
        """

        # Set return value to False by default in case of failure
        ret_code = False

        # Attempt to disable pairing mode on the Bluetooth adapter via D-Bus
        try:
            # Get D-Bus Properties interface for the Bluetooth adapter
            adapter_props = dbus.Interface(
                self.__bus.get_object(self.__BLUEZ_SERVICE, self.__ADAPTER_PATH),
                'org.freedesktop.DBus.Properties'
            )

            # Set Pairable property to False to disable pairing mode
            adapter_props.Set(self.__BLUEZ_SERVICE + '.Adapter1', 'Pairable', dbus.Boolean(False))
            
            # Verify that Pairable property was successfully cleared
            pairable = adapter_props.Get(self.__BLUEZ_SERVICE + '.Adapter1', 'Pairable')
            if not pairable:
                # Log successful disabling of pairing mode
                self.__logger.info("Bluetooth pairing disabled")
                
                # Set return value to True on success
                ret_code = True

            else:
                # Log failure to disable pairing
                self.__logger.error("Failed to disable pairing")

        # Catch D-Bus exceptions during pairing mode disable attempt 
        except dbus.exceptions.DBusException as e:
            # Log unsuccessful attempt to disable pairing
            self.__logger.error(f"agent_off failed: {str(e)}")

        finally:
            # Return the result of the pairing mode disable attempt
            return ret_code
    
    def pair(self, mac: str) -> bool:
        """
        Pair with a Bluetooth device.
        
        Parameters
        ----------
        mac : str
            Device MAC address to pair with
            
        Returns
        -------
        bool
            True if pairing successful or already paired, False otherwise
        """

        # Set return value to False by default in case of failure
        ret_code = False

        # Attempt to pair with the Bluetooth device via D-Bus
        try:
            # Get device interface for the target MAC address
            device = self.__get_device(mac)

            # Initiate pairing with 60 second timeout
            device.Pair(timeout=60000)

            # Log successful pairing
            self.__logger.info(f"Successfully paired with {mac}")

            # Set return value to True on success
            ret_code = True
        
        # Catch D-Bus exceptions during pairing attempt
        except dbus.exceptions.DBusException as e:
            # Device may already be paired, which is fine
            if "Already paired" in str(e):
                # Log that device is already paired and treat as success
                self.__logger.info(f"Device {mac} already paired")
                
                # Set return value to True since device is already paired
                ret_code = True

            else:
                # Log unsuccessful pairing attempt with detailed context
                self.__logger.error(f"pair failed for {mac}: {str(e)}")

        finally:
            # Return the result of the pairing attempt
            return ret_code
    
    def unpair(self, mac: str) -> bool:
        """
        Unpair from a Bluetooth device.
        
        Parameters
        ----------
        mac : str
            Device MAC address to unpair from
            
        Returns
        -------
        bool
            True if unpairing successful or device not found, False otherwise
        """

        # Set return value to False by default in case of failure
        ret_code = False

        # Attempt to unpair with the Bluetooth device via D-Bus
        try:
            # Construct D-Bus device path from MAC address
            device_path = self.__DEVICE_PREFIX + mac.replace(':', '_').upper()

            # Remove device via adapter's RemoveDevice method
            self.__adapter.RemoveDevice(device_path)

            # Log successful unpairing
            self.__logger.info(f"Successfully unpaired from {mac}")
            
            # Set return value to True on success
            ret_code = True
        
        # Catch D-Bus exceptions during unpairing attempt
        except dbus.exceptions.DBusException as e:
            # Device not found is acceptable (not paired to begin with)
            if "Not found" in str(e):
                # Log that device was not found and treat as success
                self.__logger.info(f"Device {mac} not found (not paired)")

                # Set return value to True since device is effectively unpaired
                ret_code = True

            else:
                # Log unsuccessful unpairing attempt with detailed context
                self.__logger.error(f"unpair failed for {mac}: {str(e)}")
        
        finally:
            # Return the result of the unpairing attempt
            return ret_code
    
    def trust(self, mac: str) -> bool:
        """
        Trust a Bluetooth device to connect automatically.
        
        Parameters
        ----------
        mac : str
            Device MAC address to trust
            
        Returns
        -------
        bool
            True if device trusted successfully, False otherwise
        """

        # Set return value to False by default in case of failure
        ret_code = False

        # Attempt to trust the Bluetooth device via D-Bus
        try:
            # Get D-Bus Properties interface for the device
            device_props = dbus.Interface(
                self.__bus.get_object(
                    self.__BLUEZ_SERVICE,
                    self.__DEVICE_PREFIX + mac.replace(':', '_').upper(),
                ),
                'org.freedesktop.DBus.Properties',
            )

            # Set Trusted property to True via D-Bus
            device_props.Set(self.__BLUEZ_SERVICE + '.Device1', 'Trusted', dbus.Boolean(True))
            
            # Verify that Trusted property was successfully set
            trusted = device_props.Get(self.__BLUEZ_SERVICE + '.Device1', 'Trusted')
            if trusted:
                # Log successful trusting of the device
                self.__logger.info(f"Device {mac} trusted")
                
                # Set return value to True on success
                ret_code = True
            
            else:
                # Log failure to trust the device
                self.__logger.error(f"Failed to set trusted property for {mac}")
        
        # Catch D-Bus exceptions during trust attempt
        except dbus.exceptions.DBusException as e:
            # Log unsuccessful attempt to trust the device with detailed context
            self.__logger.error(f"trust failed for {mac}: {str(e)}")
        
        finally:
            # Return the result of the trust attempt
            return ret_code

    def untrust(self, mac: str) -> bool:
        """
        Untrust a Bluetooth device.
        
        Parameters
        ----------
        mac : str
            Device MAC address to untrust
            
        Returns
        -------
        bool
            True if device untrusted successfully, False otherwise
        """

        # Set return value to False by default in case of failure
        ret_code = False

        # Attempt to untrust the Bluetooth device via D-Bus
        try:
            # Get D-Bus Properties interface for the device
            device_props = dbus.Interface(
                self.__bus.get_object(
                    self.__BLUEZ_SERVICE,
                    self.__DEVICE_PREFIX + mac.replace(':', '_').upper(),
                ),
                'org.freedesktop.DBus.Properties',
            )
            
            # Set Trusted property to False via D-Bus
            device_props.Set(self.__BLUEZ_SERVICE + '.Device1', 'Trusted', dbus.Boolean(False))
            
            # Verify that Trusted property was successfully cleared
            trusted = device_props.Get(self.__BLUEZ_SERVICE + '.Device1', 'Trusted')
            if not trusted:
                # Log successful untrusing of the device
                self.__logger.info(f"Device {mac} untrusted")
                
                # Set return value to True on success
                ret_code = True
            
            else:
                # Log failure to untrust the device
                self.__logger.error(f"Failed to unset trusted property for {mac}")
        
        # Catch D-Bus exceptions during untrust attempt
        except dbus.exceptions.DBusException as e:
            # Log unsuccessful attempt to untrust the device with detailed context
            self.__logger.error(f"untrust failed for {mac}: {str(e)}")
        
        finally:
            # Return the result of the untrust attempt
            return ret_code
    
    def connect(self, mac: str, fs: int) -> bool:
        """
        Connect to a Bluetooth device and establish audio routing.
        
        Parameters
        ----------
        mac : str
            Device MAC address to connect to
        fs : int
            Sample rate for audio streaming (e.g., 16000 Hz)
            
        Returns
        -------
        bool
            True if connection and audio routing successful, False otherwise
        """

        # Set return value to False by default in case of failure
        ret_code = False

        # Attempt to connect to the Bluetooth device
        try:
            # Check if already connected to the same device
            if self.__connected_mac == mac:
                # Log that we are already connected to this device and treat as success
                self.__logger.info(f"Already connected to {mac}")

                # Reset failure counter on success
                self.__consecutive_failures = 0

                # Set return value to True since we are already connected to the target device
                ret_code = True
            
            # Prevent connecting to multiple devices simultaneously
            elif self.__connected_mac is not None:

                # Log that we are already connected to a different device and treat as failure
                self.__logger.warning(f"Already connected to {self.__connected_mac}")

                # Increment failure counter since we cannot connect to multiple devices at once
                self.__consecutive_failures += 1

                # Check pattern of consecutive failures
                if self.__consecutive_failures >= self.__FAILURE_THRESHOLD:
                    # Mark as hardfault if multiple unexpected errors occur
                    self.__hardfault = True

                    # Log hardfault condition with context about multiple connection attempts
                    self.__logger.error(f"BT interface hardfault")
            
            else:
                # Get device interface
                device = self.__get_device(mac)

                # Initiate connection with 30 second timeout
                device.Connect(timeout=30000)
                
                # Find the PulseAudio sink corresponding to this Bluetooth device
                sink_name = self.__get_pulseaudio_sink(mac)

                # Check if a valid PulseAudio sink was found for the device
                if not sink_name:
                    # Log that no sink was found for the device and treat as failure
                    self.__logger.error(f"No PulseAudio sink found for {mac}")

                    # Increment failure counter since we cannot route audio without a sink
                    self.__consecutive_failures += 1

                    # Check pattern of consecutive failures
                    if self.__consecutive_failures >= self.__FAILURE_THRESHOLD:
                        # Mark as hardfault if multiple unexpected errors occur
                        self.__hardfault = True

                        # Log hardfault condition with context about multiple connection attempts
                        self.__logger.error(f"BT interface hardfault")
                
                else:
                    # Attempt to start persistent paplay process for continuous audio streaming
                    try:
                        # Start paplay with appropriate parameters for raw audio streaming
                        self.__paplay_process = subprocess.Popen(
                            [
                                'paplay',
                                '--device', sink_name,
                                '--format', 's16le',
                                '--rate', str(fs),
                                '--channels', '1',
                                '--raw'
                            ],
                            stdin=subprocess.PIPE,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE
                        )

                        # Log successful start of paplay process
                        self.__logger.info(f"Started paplay process for {sink_name}")

                        # Store PulseAudio sink and MAC for audio writing and cleanup
                        self.__pulseaudio_sink = sink_name
                        self.__connected_mac = mac
                        
                        # Reset failure counter on successful connection
                        self.__consecutive_failures = 0
                        
                        # Log successful connection and audio routing setup
                        self.__logger.info(f"Connected to {mac} with PulseAudio sink {sink_name}")
                        
                        # Set return value to True on successful connection and audio routing setup
                        ret_code = True
                    
                    # Catch FileNotFoundError if paplay command is not found
                    except FileNotFoundError:
                        # Log that paplay command is missing and treat as failure
                        self.__logger.error("paplay command not found. Install pulseaudio-utils.")

                        # Mark as hardfault since we cannot route audio without paplay
                        self.__hardfault = True
        
        # Catch D-Bus exceptions during connection attempt
        except dbus.exceptions.DBusException as e:
            # Device may already be connected, which is acceptable
            if "Already connected" in str(e):
                # Log that we are already connected to this device and treat as success
                self.__logger.info(f"Already connected to {mac}")

                # Reset failure counter on success
                self.__consecutive_failures = 0

                # Set return value to True since we are already connected to the target device
                ret_code = True
            
            else:
                # Log unsuccessful connection attempt with detailed context
                self.__logger.error(f"Connect failed for {mac}: {str(e)}")

                # Increment failure counter since connection attempt failed
                self.__consecutive_failures += 1

                # Check pattern of consecutive failures
                if self.__consecutive_failures >= self.__FAILURE_THRESHOLD:
                    # Mark as hardfault if multiple unexpected errors occur
                    self.__hardfault = True

                    # Log hardfault condition with context about multiple connection attempts
                    self.__logger.error(f"BT interface hardfault")
        
        # Catch any other exceptions that may occur during the connection attempt
        except Exception as e:
            # Log unexpected errors during connection attempt with detailed context
            self.__logger.error(f"Error setting up audio routing: {str(e)}")

            # Increment failure counter since connection attempt failed
            self.__consecutive_failures += 1

            # Check pattern of consecutive failures
            if self.__consecutive_failures >= self.__FAILURE_THRESHOLD:
                # Mark as hardfault if multiple unexpected errors occur
                self.__hardfault = True

                # Log hardfault condition with context about multiple connection attempts
                self.__logger.error(f"BT interface hardfault")
        
        finally:
            # Return the result of the connection attempt
            return ret_code
    
    def disconnect(self, mac: str) -> bool:
        """
        Disconnect from a Bluetooth device and close audio routing.
        
        Parameters
        ----------
        mac : str
            Device MAC address to disconnect from
            
        Returns
        -------
        bool
            True if disconnection successful or not connected, False otherwise
        """

        # Set return value to False by default in case of failure
        ret_code = False

        # Attempt to disconnect from the Bluetooth device
        try:
            # Close persistent paplay process if running
            if self.__paplay_process is not None:
                # Attempt shutdown of paplay process
                try:
                    # Close stdin to signal process termination
                    self.__paplay_process.stdin.close()

                    # Wait up to 2 seconds for process to finish
                    self.__paplay_process.wait(timeout=2)

                    # Log successful closure of paplay process
                    self.__logger.info("Closed paplay process")

                # Catch exceptions during paplay shutdown and log them with context
                except Exception as e:
                    # Log any errors that occur during paplay shutdown but continue with cleanup
                    self.__logger.warning(f"Error closing paplay process: {str(e)}")

                    # Attempt to terminate the process if it is still running
                    try:
                        # Terminate the paplay process if it is still running
                        self.__paplay_process.terminate()

                    # Catch any exceptions during process termination
                    except:
                        # Ignore any errors during process termination in a failure state
                        pass
                
                finally:
                    # Clear process reference regardless of success/failure
                    self.__paplay_process = None
            
            # Clear audio routing variables
            if self.__pulseaudio_sink is not None:
                self.__pulseaudio_sink = None
                self.__connected_mac = None
            
            # Disconnect from device via D-Bus
            device = self.__get_device(mac)
            device.Disconnect()

            # Log successful disconnection
            self.__logger.info(f"Disconnected from {mac}")
            
            # Set return value to True on success
            ret_code = True
        
        # Catch D-Bus exceptions during disconnect attempt
        except dbus.exceptions.DBusException as e:
            # Not connected or already disconnected is acceptable
            if "Not connected" in str(e):
                # Log that device was not connected and treat as success
                self.__logger.info(f"Device {mac} not connected")
                
                # Set return value to True since device is effectively disconnected
                ret_code = True
            
            else:
                # Log unsuccessful disconnection attempt with detailed context
                self.__logger.error(f"disconnect failed for {mac}: {str(e)}")
        
        finally:
            # Return the result of the disconnect attempt
            return ret_code
    
    def info(self, mac: str) -> dict:
        """
        Get device information via D-Bus.
        
        Parameters
        ----------
        mac : str
            Device MAC address
            
        Returns
        -------
        dict
            Device properties (Name, Address, Paired, Trusted, Connected, etc.)
            Empty dict if retrieval fails
        """

        # Set return value to empty dict by default in case of failure
        device_info = {}

        # Attempt to retrieve device information via D-Bus
        try:
            # Get D-Bus Properties interface for the device
            device_props = dbus.Interface(
                self.__bus.get_object(self.__BLUEZ_SERVICE, self.__DEVICE_PREFIX + mac.replace(':', '_').upper()),
                'org.freedesktop.DBus.Properties'
            )
            
            # Retrieve all properties for the device via D-Bus
            all_props = device_props.GetAll(self.__BLUEZ_SERVICE + '.Device1')
            
            # Log retrieved device information with context about the target MAC address
            self.__logger.info(f"Retrieved info for {mac}")

            # Convert D-Bus properties to regular dict for easier access
            device_info = dict(all_props)
            
        except dbus.exceptions.DBusException as e:
            # Log unsuccessful retrieval of device information with detailed context
            self.__logger.error(f"info failed for {mac}: {str(e)}")
        
        finally:
            # Return the retrieved device information or empty dict if retrieval failed
            return device_info
    
    def devices(self, audio_sink: bool = True) -> dict:
        """
        Get list of paired Bluetooth devices.
        
        Parameters
        ----------
        audio_sink : bool, optional
            If True, only return audio sink devices. Default is True.
            
        Returns
        -------
        dict
            Dictionary with MAC addresses as keys and device names as values
            Empty dict if retrieval fails
        """

        # Set return value to empty dict by default in case of failure
        devices_dict = {}

        # Attempt to retrieve list of paired devices via D-Bus
        try:
            # Get D-Bus ObjectManager interface to query all Bluez objects
            om = dbus.Interface(
                self.__bus.get_object(self.__BLUEZ_SERVICE, '/'),
                'org.freedesktop.DBus.ObjectManager'
            )
            
            # Retrieve all managed objects from Bluez daemon
            managed_objs = om.GetManagedObjects()
            
            # Iterate through all objects looking for paired audio sink devices
            for path, interfaces in managed_objs.items():
                # Check if this object has Device1 interface
                device_iface = interfaces.get(self.__BLUEZ_SERVICE + '.Device1')
                if device_iface:
                    # Filter for paired devices
                    if device_iface.get('Paired'):
                        # Check if device is audio sink (or include all if audio_sink=False)
                        if self.__is_audio_sink(device_iface) or not audio_sink:
                            # Extract MAC address and name
                            address = device_iface.get('Address')
                            name = device_iface.get('Name', 'Unknown')
                            devices_dict[address] = name

            # Log discovered devices
            log_str = f"Found {len(devices_dict)} paired audio sinks:\n"
            for address, name in devices_dict.items():
                log_str += f"\t{str(address)}: {name}\n"
            self.__logger.info(log_str)
        
        # Catch D-Bus exceptions during device listing attempt
        except dbus.exceptions.DBusException as e:
            # Log unsuccessful retrieval of paired devices with detailed context
            self.__logger.error(f"Failed to list devices: {str(e)}")
        
        finally:
            # Return the dictionary of paired devices or empty dict if retrieval failed
            return devices_dict
    
    def __is_audio_sink(self, device_props) -> bool:
        """
        Check if a device is an audio sink.
        
        Parameters
        ----------
        device_props : dict
            Device properties from D-Bus GetAll()
            
        Returns
        -------
        bool
            True if device is an audio sink, False otherwise
        """
        # Set return value to False by default in case of failure
        is_sink = False

        # Audio Sink service UUID for A2DP
        audio_sink_uuid = '0000110b-0000-1000-8000-00805f9b34fb'

        # Major audio device class for fallback check
        audio_major_class = 0x04

        # Check if device advertises the Audio Sink UUID
        uuids = device_props.get('UUIDs', [])
        if audio_sink_uuid in uuids:
            is_sink = True

        # Alternative check: Major device class 0x04 = Audio device
        device_class = device_props.get('Class', 0)
        major_device_class = (device_class >> 8) & 0xFF
        if major_device_class == audio_major_class:
            is_sink = True
        
        # Return the result of the audio sink check
        return is_sink
    
    def scan(self, duration: int, audio_sink: bool = True) -> dict:
        """
        Scan for nearby Bluetooth devices.
        
        Parameters
        ----------
        duration : int
            Scan duration in seconds
        audio_sink : bool, optional
            If True, only return audio sink devices. Default is True.
            
        Returns
        -------
        dict
            Dictionary with MAC addresses as keys and device names as values
            Empty dict if scan fails
        """

        # Set return value to empty dict by default in case of failure
        devices_dict = {}

        # Attempt to perform Bluetooth device discovery via D-Bus
        try:
            # Start Bluetooth device discovery via D-Bus
            self.__adapter.StartDiscovery()

            # Log that discovery has started with context about the scan duration
            self.__logger.info(f"Starting discovery for {duration} seconds")
            
            # Wait for devices to advertise themselves
            time.sleep(duration)
            
            # Attempt to stop discovery after the specified duration to save power
            try:
                # Stop discovery to save power
                self.__adapter.StopDiscovery()

            # Catch D-Bus exceptions during StopDiscovery and log them with context
            except dbus.exceptions.DBusException as e:
                # It's okay if discovery wasn't running
                if "No discovery started" not in str(e):
                    # Log that discovery was not running when attempting to stop it
                    self.__logger.info("Discovery was not running when attempting to stop it")

                else:
                    # Log errors that occur during StopDiscovery with detailed context
                    self.__logger.error(f"Error stopping discovery: {str(e)}")
            
            # Get D-Bus ObjectManager to query discovered devices
            om = dbus.Interface(
                self.__bus.get_object(self.__BLUEZ_SERVICE, '/'),
                'org.freedesktop.DBus.ObjectManager'
            )

            # Retrieve all managed objects from Bluez
            managed_objs = om.GetManagedObjects()
            
            # Filter for audio sink devices discovered during scan
            for path, interfaces in managed_objs.items():
                # Check if this object has Device1 interface
                device_iface = interfaces.get(self.__BLUEZ_SERVICE + '.Device1')
                if device_iface:
                    # Include only audio sink devices (or all if audio_sink=False)
                    if self.__is_audio_sink(device_iface) or not audio_sink:
                        # Extract MAC address and name
                        address = device_iface.get('Address')
                        name = device_iface.get('Name', 'Unknown')
                        devices_dict[address] = name

            # Log discovered devices
            log_str = f"Discovery found {len(devices_dict)} audio sink devices:\n"
            for address, name in devices_dict.items():
                log_str += f"\t{str(address)}: {name}\n"
            self.__logger.info(log_str)
        
        # Catch D-Bus exceptions during discovery attempt
        except dbus.exceptions.DBusException as e:
            # Log unsuccessful discovery attempt with detailed context
            self.__logger.error(f"scan failed: {str(e)}")
        
        finally:
            # Return the dictionary of discovered devices or empty dict if discovery failed
            return devices_dict
    
    def write_audio(self, audio_bytes: bytes) -> bool:
        """
        Write raw audio bytes to the connected Bluetooth A2DP device.
        
        Parameters
        ----------
        audio_bytes : bytes
            Raw audio data (int16 PCM format, 16kHz, mono)
            
        Returns
        -------
        bool
            True if audio written successfully, False otherwise
        """

        # Set return value to False by default in case of failure
        ret_code = False

        # Attempt to write audio data to the connected device
        try:
            # Check if device is connected and paplay is running
            if self.__paplay_process is None or self.__connected_mac is None:
                # Log that no device is connected and treat as failure
                self.__logger.error("No device connected. Call connect() first.")

                # Increment failure counter since audio cannot be written without connection
                self.__consecutive_failures += 1

                # Check pattern of consecutive failures
                if self.__consecutive_failures >= self.__FAILURE_THRESHOLD:
                    # Mark as hardfault if multiple unexpected errors occur
                    self.__hardfault = True
            
            # Check if process is still alive by checking exit status
            elif self.__paplay_process.poll() is not None:
                # Log that paplay process has terminated unexpectedly and treat as failure
                self.__logger.error("paplay process terminated unexpectedly")

                # Clear process reference since it is no longer valid
                self.__paplay_process = None

                # Increment failure counter since audio cannot be written without paplay
                self.__consecutive_failures += 1

                # Check pattern of consecutive failures
                if self.__consecutive_failures >= self.__FAILURE_THRESHOLD:
                    # Mark as hardfault if multiple unexpected errors occur
                    self.__hardfault = True
            
            else:
                # Attempt to write audio data to paplay's stdin for streaming
                try:
                    # Write audio data to paplay's stdin pipe for continuous streaming
                    self.__paplay_process.stdin.write(audio_bytes)

                    # Flush immediately to avoid buffering delays in audio output
                    self.__paplay_process.stdin.flush()
                    
                    # Reset failure counter on successful audio write
                    self.__consecutive_failures = 0

                    # Log successful audio write with context about the number of bytes written
                    ret_code = True
                
                # Catch BrokenPipeError to handle cases where paplay process has closed its stdin
                except BrokenPipeError:
                    # Log that the pipe to paplay is broken, which likely means the device disconnected
                    self.__logger.error("paplay pipe broken (device may have disconnected)")

                    # Clear process reference since it is no longer valid
                    self.__paplay_process = None

                    # Increment failure counter since audio cannot be written without paplay
                    self.__consecutive_failures += 1

                    # Check pattern of consecutive failures
                    if self.__consecutive_failures >= self.__FAILURE_THRESHOLD:
                        # Mark as hardfault if multiple unexpected errors occur
                        self.__hardfault = True
        
        # Catch general exceptions during audio write attempt        
        except Exception as e:
            # Log any unexpected errors that occur during the audio write attempt
            self.__logger.error(f"Error writing audio to PulseAudio: {str(e)}")

            # Increment failure counter since audio write attempt failed
            self.__consecutive_failures += 1

            # Check pattern of consecutive failures
            if self.__consecutive_failures >= self.__FAILURE_THRESHOLD:
                # Mark as hardfault if multiple unexpected errors occur
                self.__hardfault = True
        
        finally:
            # Return the result of the audio write attempt
            return ret_code
    
    def __get_pulseaudio_sink(self, mac: str) -> str:
        """
        Get the PulseAudio sink name for a Bluetooth device.
        
        Parameters
        ----------
        mac : str
            Bluetooth device MAC address
            
        Returns
        -------
        str
            PulseAudio sink name if found, None otherwise
        """

        # Set return value to None by default in case of failure
        sink_name = None

        # Attempt to query PulseAudio for the sink corresponding to the Bluetooth device
        try:
            # Query PulseAudio daemon for all available sinks
            result = subprocess.run(
                ['pactl', 'list', 'sinks'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            # Check if pactl command executed successfully
            if result.returncode != 0:
                # Log error output from pactl command for debugging
                self.__logger.error(f"pactl error: {result.stderr}")
            
            else:
                # Normalize MAC address to match PulseAudio format
                mac_normalized = mac.replace(':', '_')
                
                # Parse pactl output to find matching Bluetooth sink
                for line in result.stdout.split('\n'):
                    # Remove leading/trailing whitespace for easier parsing
                    line = line.strip()
                    
                    # Look for Name field in sink properties
                    if line.startswith('Name:'):
                        # Extract sink name
                        name = line.split('Name:', 1)[1].strip()
                        
                        # Check if this is a Bluetooth sink containing our device's MAC address
                        if 'bluez' in name.lower() and mac_normalized in name:
                            # Log that matching PulseAudio sink was found for the device
                            self.__logger.info(f"Found PulseAudio sink: {name}")

                            # Set matching sink for this device and break from loop
                            sink_name = name
                            break
                else:
                    # Log warning with all available sinks for debugging
                    self.__logger.warning(f"No PulseAudio sink found for {mac}. Available sinks:\n{result.stdout}")
        
        # Catch FileNotFoundError if pactl command is not found and log it with context
        except FileNotFoundError:
            # Log that pactl command is missing
            self.__logger.error("pactl command not found. Install pulseaudio-utils.")

            # Mark as hardfault since we cannot route audio without pactl
            self.__hardfault = True

        # Catch subprocess.TimeoutExpired if pactl takes too long to respond
        except subprocess.TimeoutExpired:
            # Log that pactl command timed out
            self.__logger.error("pactl command timed out")

        # Catch any other exceptions that may occur during the pactl query
        except Exception as e:
            # Log any unexpected errors that occur during the pactl query
            self.__logger.error(f"Error querying PulseAudio sinks: {str(e)}")
        
        finally:
            # Return the result of the sink query attempt
            return sink_name
    
    @property
    def hardfault(self) -> bool:
        """
        Check if the Bluetooth interface has encountered an unrecoverable error.

        Parameters
        ----------
        None
        
        Returns
        -------
        bool
            True if a hardfault condition has been detected, False otherwise
        """

        # Return the current hardfault status
        return self.__hardfault

    def properties(self, mac: str) -> dict:
        try:
            device_props = dbus.Interface(
                self.__bus.get_object(BLUEZ_SERVICE, DEVICE_PREFIX + mac.replace(':', '_').upper()),
                'org.freedesktop.DBus.Properties'
            )
            return dict(device_props.GetAll(BLUEZ_SERVICE + '.Device1'))
        except dbus.exceptions.DBusException as e:
            self.__log_failure("properties", device=mac, error=str(e))
            return {}
