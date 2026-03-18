# Standard imports
import dbus
import dbus.service
import textwrap
import re
import time
from pathlib import Path
from dbus.mainloop.glib import DBusGMainLoop, threads_init

# D-Bus object paths
BLUEZ_SERVICE = 'org.bluez'
ADAPTER_PATH = '/org/bluez/hci0'
DEVICE_PREFIX = '/org/bluez/hci0/dev_'

class BT_Interface:

    def __init__(self, logger) -> None:
        # Store logger instance
        self.__logger = logger
        
        # Initialize D-Bus
        DBusGMainLoop(set_as_default=True)
        threads_init()
        
        try:
            self.__bus = dbus.SystemBus()
            self.__adapter = self.__get_adapter()
            self.__logger.info("BT_Interface initialized with D-Bus API")
        except dbus.exceptions.DBusException as e:
            self.__logger.error(f"Failed to initialize D-Bus: {str(e)}")
            raise RuntimeError(f"D-Bus initialization failed: {e}")
    
    def __get_adapter(self):
        """Get the Bluetooth adapter interface"""
        try:
            adapter_obj = self.__bus.get_object(BLUEZ_SERVICE, ADAPTER_PATH)
            return dbus.Interface(adapter_obj, BLUEZ_SERVICE + '.Adapter1')
        except dbus.exceptions.DBusException as e:
            self.__logger.error(f"Failed to get adapter: {str(e)}")
            raise
    
    def __get_device(self, mac: str):
        """Get device object interface for a given MAC address"""
        device_path = DEVICE_PREFIX + mac.replace(':', '_').upper()
        try:
            device_obj = self.__bus.get_object(BLUEZ_SERVICE, device_path)
            return dbus.Interface(device_obj, BLUEZ_SERVICE + '.Device1')
        except dbus.exceptions.DBusException as e:
            self.__logger.error(f"Failed to get device {mac} at path {device_path}: {str(e)}")
            raise

    
    def __strip_ansi(self, text: str) -> str:
        """Remove ANSI escape codes from text"""
        ansi_escape = re.compile(r'\x1b\[[0-9;]*m|\[K')
        return ansi_escape.sub('', text)
    
    def __log_failure(self, operation: str, device: str = "", output: str = "", error: str = "") -> None:
        """Log failure with context"""
        log_entry = f"\nOperation: {operation}"
        if device:
            log_entry += f"\nDevice: {device}"
        if output:
            cleaned_output = self.__strip_ansi(output)
            indented_output = textwrap.indent(cleaned_output, "\t")
            log_entry += f"\nOutput:\n{indented_output}"
        if error:
            cleaned_error = self.__strip_ansi(error)
            indented_error = textwrap.indent(cleaned_error, "\t")
            log_entry += f"\nError:\n{indented_error}"
        
        self.__logger.error(log_entry)
    
    def power_on(self) -> bool:
        """Power on the Bluetooth adapter"""
        try:
            # Get adapter properties
            adapter_props = dbus.Interface(
                self.__bus.get_object(BLUEZ_SERVICE, ADAPTER_PATH),
                'org.freedesktop.DBus.Properties'
            )
            # Set Powered to True
            adapter_props.Set(BLUEZ_SERVICE + '.Adapter1', 'Powered', dbus.Boolean(True))
            
            # Verify it's powered on
            powered = adapter_props.Get(BLUEZ_SERVICE + '.Adapter1', 'Powered')
            if powered:
                self.__logger.info("Bluetooth adapter powered on")
                return True
            else:
                self.__log_failure("power_on", error="Adapter failed to power on")
                return False
                
        except dbus.exceptions.DBusException as e:
            self.__log_failure("power_on", error=str(e))
            return False
    
    def power_off(self) -> bool:
        """Power off the Bluetooth adapter"""
        try:
            adapter_props = dbus.Interface(
                self.__bus.get_object(BLUEZ_SERVICE, ADAPTER_PATH),
                'org.freedesktop.DBus.Properties'
            )
            adapter_props.Set(BLUEZ_SERVICE + '.Adapter1', 'Powered', dbus.Boolean(False))
            
            powered = adapter_props.Get(BLUEZ_SERVICE + '.Adapter1', 'Powered')
            if not powered:
                self.__logger.info("Bluetooth adapter powered off")
                return True
            else:
                self.__log_failure("power_off", error="Adapter failed to power off")
                return False
                
        except dbus.exceptions.DBusException as e:
            self.__log_failure("power_off", error=str(e))
            return False
    
    def agent_on(self) -> bool:
        """Enable pairing agent"""
        try:
            # For D-Bus, agent management is handled differently
            # We'll just set pairable mode on the adapter
            adapter_props = dbus.Interface(
                self.__bus.get_object(BLUEZ_SERVICE, ADAPTER_PATH),
                'org.freedesktop.DBus.Properties'
            )
            adapter_props.Set(BLUEZ_SERVICE + '.Adapter1', 'Pairable', dbus.Boolean(True))
            
            pairable = adapter_props.Get(BLUEZ_SERVICE + '.Adapter1', 'Pairable')
            if pairable:
                self.__logger.info("Bluetooth pairing enabled")
                return True
            else:
                self.__log_failure("agent_on", error="Failed to enable pairing")
                return False
                
        except dbus.exceptions.DBusException as e:
            self.__log_failure("agent_on", error=str(e))
            return False
    
    def agent_off(self) -> bool:
        """Disable pairing agent"""
        try:
            adapter_props = dbus.Interface(
                self.__bus.get_object(BLUEZ_SERVICE, ADAPTER_PATH),
                'org.freedesktop.DBus.Properties'
            )
            adapter_props.Set(BLUEZ_SERVICE + '.Adapter1', 'Pairable', dbus.Boolean(False))
            
            pairable = adapter_props.Get(BLUEZ_SERVICE + '.Adapter1', 'Pairable')
            if not pairable:
                self.__logger.info("Bluetooth pairing disabled")
                return True
            else:
                self.__log_failure("agent_off", error="Failed to disable pairing")
                return False
                
        except dbus.exceptions.DBusException as e:
            self.__log_failure("agent_off", error=str(e))
            return False
    
    def pair(self, mac: str) -> bool:
        """Pair with a Bluetooth device"""
        try:
            device = self.__get_device(mac)
            device.Pair(timeout=60000)  # 60 second timeout for pairing
            self.__logger.info(f"Successfully paired with {mac}")
            return True
            
        except dbus.exceptions.DBusException as e:
            if "Already paired" in str(e):
                self.__logger.info(f"Device {mac} already paired")
                return True
            self.__log_failure("pair", device=mac, error=str(e))
            return False
    
    def unpair(self, mac: str) -> bool:
        """Unpair from a Bluetooth device"""
        try:
            adapter = self.__get_adapter()
            device_path = DEVICE_PREFIX + mac.replace(':', '_').upper()
            adapter.RemoveDevice(device_path)
            self.__logger.info(f"Successfully unpaired from {mac}")
            return True
            
        except dbus.exceptions.DBusException as e:
            if "Not found" in str(e):
                self.__logger.info(f"Device {mac} not found (not paired)")
                return True
            self.__log_failure("unpair", device=mac, error=str(e))
            return False
    
    def trust(self, mac: str) -> bool:
        """Trust a Bluetooth device"""
        try:
            device_props = dbus.Interface(
                self.__bus.get_object(BLUEZ_SERVICE, DEVICE_PREFIX + mac.replace(':', '_').upper()),
                'org.freedesktop.DBus.Properties'
            )
            device_props.Set(BLUEZ_SERVICE + '.Device1', 'Trusted', dbus.Boolean(True))
            
            trusted = device_props.Get(BLUEZ_SERVICE + '.Device1', 'Trusted')
            if trusted:
                self.__logger.info(f"Device {mac} trusted")
                return True
            else:
                self.__log_failure("trust", device=mac, error="Failed to set trusted property")
                return False
                
        except dbus.exceptions.DBusException as e:
            self.__log_failure("trust", device=mac, error=str(e))
            return False
    
    def untrust(self, mac: str) -> bool:
        """Untrust a Bluetooth device"""
        try:
            device_props = dbus.Interface(
                self.__bus.get_object(BLUEZ_SERVICE, DEVICE_PREFIX + mac.replace(':', '_').upper()),
                'org.freedesktop.DBus.Properties'
            )
            device_props.Set(BLUEZ_SERVICE + '.Device1', 'Trusted', dbus.Boolean(False))
            
            trusted = device_props.Get(BLUEZ_SERVICE + '.Device1', 'Trusted')
            if not trusted:
                self.__logger.info(f"Device {mac} untrusted")
                return True
            else:
                self.__log_failure("untrust", device=mac, error="Failed to unset trusted property")
                return False
                
        except dbus.exceptions.DBusException as e:
            self.__log_failure("untrust", device=mac, error=str(e))
            return False
    
    def connect(self, mac: str) -> bool:
        """Connect to a Bluetooth device"""
        try:
            device = self.__get_device(mac)
            device.Connect(timeout=30000)  # 30 second timeout for connection
            self.__logger.info(f"Connected to {mac}")
            return True
            
        except dbus.exceptions.DBusException as e:
            if "Already connected" in str(e):
                self.__logger.info(f"Already connected to {mac}")
                return True
            self.__log_failure("connect", device=mac, error=str(e))
            return False
    
    def disconnect(self, mac: str) -> bool:
        """Disconnect from a Bluetooth device"""
        try:
            device = self.__get_device(mac)
            device.Disconnect()
            self.__logger.info(f"Disconnected from {mac}")
            return True
            
        except dbus.exceptions.DBusException as e:
            if "Not connected" in str(e):
                self.__logger.info(f"Device {mac} not connected")
                return True
            self.__log_failure("disconnect", device=mac, error=str(e))
            return False
    
    def info(self, mac: str) -> str:
        """Get device information"""
        try:
            device_props = dbus.Interface(
                self.__bus.get_object(BLUEZ_SERVICE, DEVICE_PREFIX + mac.replace(':', '_').upper()),
                'org.freedesktop.DBus.Properties'
            )
            
            # Get all properties
            all_props = device_props.GetAll(BLUEZ_SERVICE + '.Device1')
            
            # Format the output
            info_str = f"Device {mac}\n"
            for key, value in all_props.items():
                info_str += f"\t{key}: {value}\n"
            
            self.__logger.info(f"Retrieved info for {mac}")
            return info_str
            
        except dbus.exceptions.DBusException as e:
            self.__log_failure("info", device=mac, error=str(e))
            return ""
    
    def devices(self, audio_sink: bool = True) -> dict:
        """Get list of paired audio sink devices"""
        try:
            # Get the Managed Objects from ObjectManager
            om = dbus.Interface(
                self.__bus.get_object(BLUEZ_SERVICE, '/'),
                'org.freedesktop.DBus.ObjectManager'
            )
            
            devices_dict = {}
            managed_objs = om.GetManagedObjects()
            
            for path, interfaces in managed_objs.items():
                device_iface = interfaces.get(BLUEZ_SERVICE + '.Device1')
                if device_iface:
                    # Check if device is paired and is an audio sink
                    if device_iface.get('Paired'):
                        if self.__is_audio_sink(device_iface) or not audio_sink:
                            address = device_iface.get('Address')
                            name = device_iface.get('Name', 'Unknown')
                            devices_dict[address] = name

            log_str = f"Found {len(devices_dict)} paired audio sinks:\n"
            for address, name in devices_dict.items():
                log_str += f"\t{str(address)}: {name}\n"
            self.__logger.info(log_str)
            return devices_dict
            
        except dbus.exceptions.DBusException as e:
            self.__log_failure("devices", error=str(e))
            return {}
    
    def __is_audio_sink(self, device_props) -> bool:
        """Check if a device is an audio sink"""
        # Audio Sink UUID: 0000110b-0000-1000-8000-00805f9b34fb
        audio_sink_uuid = '0000110b-0000-1000-8000-00805f9b34fb'

        # Check if device has the Audio Sink UUID
        uuids = device_props.get('UUIDs', [])
        if audio_sink_uuid in uuids:
            return True

        # Check major device class (0x04 = Audio/Video device)
        device_class = device_props.get('Class', 0)
        major_device_class = (device_class >> 8) & 0xFF
        if major_device_class == 0x04:
            return True
        
        # If neither check passed, it's not an audio sink
        return False
    
    def scan(self, duration: int, audio_sink: bool = True) -> dict:
        """Scan for nearby Bluetooth devices"""
        try:
            adapter = self.__get_adapter()
            
            # Start discovery
            adapter.StartDiscovery()
            self.__logger.info(f"Starting discovery for {duration} seconds")
            
            # Wait for the specified duration
            time.sleep(duration)
            
            # Stop discovery
            try:
                adapter.StopDiscovery()
            except dbus.exceptions.DBusException as e:
                if "No discovery started" not in str(e):
                    self.__logger.error(f"Error stopping discovery: {str(e)}")
            
            # Get discovered devices
            om = dbus.Interface(
                self.__bus.get_object(BLUEZ_SERVICE, '/'),
                'org.freedesktop.DBus.ObjectManager'
            )
            
            devices_dict = {}
            managed_objs = om.GetManagedObjects()
            
            for path, interfaces in managed_objs.items():
                device_iface = interfaces.get(BLUEZ_SERVICE + '.Device1')
                if device_iface:
                    # Filter for audio sink devices only
                    if self.__is_audio_sink(device_iface) or not audio_sink:
                        address = device_iface.get('Address')
                        name = device_iface.get('Name', 'Unknown')
                        devices_dict[address] = name

            log_str = f"Discovery found {len(devices_dict)} audio sink devices:\n"
            for address, name in devices_dict.items():
                log_str += f"\t{str(address)}: {name}\n"
            self.__logger.info(log_str)
            return devices_dict
            
        except dbus.exceptions.DBusException as e:
            self.__log_failure("scan", error=str(e))
            return {}
