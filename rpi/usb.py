"""USB Audio Interface using PyAudio for real-time audio capture."""

import pyaudio
import logging
import subprocess
from typing import Optional


class USB_Interface:
    """Capture audio from USB device using PyAudio."""

    def __init__(self, logger: logging.Logger, source: str, sample_rate: int, frame_size: int) -> None:
        """
        Initialize USB audio interface.
        
        Args:
            logger: Logger instance
            source: ALSA device name or PulseAudio source name
            sample_rate: Sample rate in Hz (typically 16000)
            frame_size: Number of samples per frame (typically 160)
        """
        self.__logger = logger
        self.__source = source
        self.__sample_rate = sample_rate
        self.__frame_size = frame_size
        self.__stream: Optional[pyaudio.Stream] = None
        self.__audio: Optional[pyaudio.PyAudio] = None
        self.__device_index: Optional[int] = None
        self.__channels: int = 0

    def __get_device_index(self) -> int:
        """Get PyAudio device index for the USB source."""
        if self.__audio is None:
            raise RuntimeError("PyAudio not initialized. Call connect() first.")

        # Try to find device by name
        for i in range(self.__audio.get_device_count()):
            info = self.__audio.get_device_info_by_index(i)
            device_name = info['name']
            
            # Match against source name (handle both ALSA and PulseAudio names)
            if self.__source in device_name.upper() or device_name.upper() in self.__source:
                self.__logger.info(f"Found USB device at index {i}: {device_name}")
                return i
        
        # If not found, log available devices and raise error
        self.__logger.error(f"USB device '{self.__source}' not found. Available devices:")
        for i in range(self.__audio.get_device_count()):
            info = self.__audio.get_device_info_by_index(i)
            self.__logger.error(f"  [{i}] {info['name']} (channels: {info['maxInputChannels']})")
        
        raise RuntimeError(f"USB device '{self.__source}' not found")

    def connect(self) -> bool:
        """
        Initialize PyAudio and open audio stream from USB device.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Initialize PyAudio
            self.__audio = pyaudio.PyAudio()
            self.__logger.info("PyAudio initialized")
            
            # Get device index
            self.__device_index = self.__get_device_index()
            device_info = self.__audio.get_device_info_by_index(self.__device_index)
            self.__channels = int(device_info['maxInputChannels'])
            
            # Open audio stream
            self.__stream = self.__audio.open(
                format=pyaudio.paInt16,
                channels=self.__channels,
                rate=self.__sample_rate,
                input=True,
                input_device_index=self.__device_index,
                frames_per_buffer=self.__frame_size
            )
            
            self.__logger.info(
                f"USB_Interface connected: {device_info['name']} "
                f"({self.__channels} channels, {self.__sample_rate}Hz, {self.__frame_size} frame size)"
            )
            return True
            
        except Exception as e:
            self.__logger.error(f"Failed to connect USB interface: {str(e)}")
            self.disconnect()
            return False

    def get_audio(self) -> Optional[bytes]:
        """
        Read one frame of audio from USB device.
        
        Returns:
            Audio frame as bytes (int16 samples), or None if error occurs
            
        Raises:
            RuntimeError: If stream is not connected
        """
        if self.__stream is None:
            self.__logger.error("USB interface not connected. Call connect() first.")
            return None

        try:
            # Read one frame from stream
            # Note: exception_on_overflow parameter is not supported in all PyAudio versions
            try:
                data = self.__stream.read(self.__frame_size, exception_on_overflow=False)
            except TypeError:
                # Fallback if exception_on_overflow is not supported
                data = self.__stream.read(self.__frame_size)
            return data
        except OSError as e:
            # Handle stream errors gracefully
            if "Input overflowed" in str(e) or "Stream closed" in str(e):
                self.__logger.debug(f"USB stream warning: {str(e)}")
                # Return None to skip this frame but keep stream open
                return None
            else:
                self.__logger.error(f"Error reading audio from USB: {str(e)}")
                return None
        except Exception as e:
            self.__logger.error(f"Error reading audio from USB: {str(e)}")
            return None

    def read_frame(self) -> Optional[bytes]:
        """
        Read one frame of audio from USB device (alias for get_audio).
        
        Returns:
            Audio frame as bytes (int16 samples), or None if error occurs
        """
        try:
            return self.get_audio()
        except Exception:
            return None

    @property
    def channels(self) -> int:
        """Get number of channels in the USB device."""
        return self.__channels

    def disconnect(self) -> bool:
        """Close audio stream and cleanup resources."""
        try:
            if self.__stream is not None:
                try:
                    self.__stream.stop_stream()
                    self.__stream.close()
                    self.__logger.info("Audio stream closed")
                except Exception as e:
                    self.__logger.error(f"Error closing stream: {str(e)}")
                finally:
                    self.__stream = None
            
            if self.__audio is not None:
                try:
                    self.__audio.terminate()
                    self.__logger.info("PyAudio terminated")
                except Exception as e:
                    self.__logger.error(f"Error terminating PyAudio: {str(e)}")
                finally:
                    self.__audio = None
            
            return True
        except Exception as e:
            self.__logger.error(f"Error during disconnect: {str(e)}")
            return False

    def __del__(self):
        """Ensure cleanup on object destruction."""
        self.disconnect()
