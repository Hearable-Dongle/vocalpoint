# Standard imports
import re
import shutil
import logging
from pathlib import Path


class Session_Config():

    # Private configuration variables
    # __sink: str = "9C:FC:28:30:11:9F"
    __sink: str = "BC:87:FA:57:47:0E" # Bose QC Headphones
    __source: str = "respeaker"
    __frame: int = 160
    __fs: int = 16000
    __deps: list[str] = [
        "pactl",
        "pw-loopback",
        "bluetoothd",
        "pkill",
        "sudo",
    ]
    __python_deps: list[str] = [
        "dbus",
        "pyaudio",
        "numpy",
    ]

    def __init__(self) -> None:
        # Setup logging to file in script directory
        log_file = Path(__file__).parent / "session.log"
        
        # Clear the log file at the start of new session
        log_file.open('w').close()
        
        # Configure logger
        logging.basicConfig(
            filename=log_file,
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        self.__logger = logging.getLogger(__name__)
        
        # Verify required dependencies are available
        self.__verify_deps()

    def __verify_deps(self) -> None:
        # Check system dependencies
        for dep in self.__deps:
            if not shutil.which(dep):
                raise RuntimeError(f"Missing required dependency: {dep}")
        
        # Check Python dependencies
        import importlib
        for py_dep in self.__python_deps:
            try:
                importlib.import_module(py_dep)
            except ImportError:
                raise RuntimeError(f"Missing required Python package: {py_dep}")

    @property
    def sink(self):
        # Return private Bluetooth sink address
        return self.__sink
    
    @sink.setter
    def sink(self, value: str) -> None:
        # Validate Bluetooth address format
        mac_re = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")
        if not mac_re.match(value):
            raise ValueError("Invalid Bluetooth MAC address format")

        # Set private Bluetooth sink address
        self.__sink = value

    @property
    def source(self):
        # Return private microphone source name
        return self.__source

    @property
    def frame(self):
        # Return private audio frame size
        return self.__frame
    
    @property
    def fs(self):
        # Return private sampling frequency
        return self.__fs
    
    @property
    def logger(self):
        # Return logger instance
        return self.__logger

