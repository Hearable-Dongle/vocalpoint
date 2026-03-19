# Standard imports
from typing import Optional
import logging
import subprocess

# Third-party imports
import pyaudio


class USB_Interface:
    """
    Interface for capturing audio from USB device using PyAudio.
    """

    def __init__(
        self,
        logger: logging.Logger,
        source: str,
        sample_rate: int,
        frame_size: int
    ) -> None:
        """
        Initialize USB audio interface.
        
        Parameters
        ----------
        logger : logging.Logger
            Logger instance for recording audio events and errors
        source : str
            Device name to match for audio source (ALSA or PulseAudio format)
        sample_rate : int
            Sample rate in Hz (typically 16000)
        frame_size : int
            Number of samples per frame (typically 160)

        Returns
        -------
        None
        """

        # Initialize parameters
        self.__logger = logger
        self.__source = source
        self.__sample_rate = sample_rate
        self.__frame_size = frame_size
        self.__stream: Optional[pyaudio.Stream] = None
        self.__audio: Optional[pyaudio.PyAudio] = None
        self.__device_index: Optional[int] = None
        self.__channels: int = 0

    def __get_device_index(self) -> Optional[int]:
        """
        Get PyAudio device index for the USB source.
        
        Parameters
        ----------
        None
        
        Returns
        -------
        int
            PyAudio device index for the USB source
        """

        # Set device index to none by default
        device_idx = None

        # Check if PyAudio is initialized
        if self.__audio is None:
            # Log error when PyAudio is not initialized
            self.__logger.error("PyAudio not initialized: connect() must be called first.")

        else:
            # Iterate through available PyAudio devices
            for idx in range(self.__audio.get_device_count()):
                # Get device info and parse name
                info = self.__audio.get_device_info_by_index(idx)
                device_name = info['name']
                
                # Check if name matches the configured source
                if self.__source in device_name or device_name in self.__source:
                    # Log found device
                    self.__logger.info(f"Found USB device at index {idx}: {device_name}")

                    # Set device index and break loop
                    device_idx = idx
                    break
            else:
                # Log error when no matching device found
                log_str = f"USB device '{self.__source}' not found:"
                for i in range(self.__audio.get_device_count()):
                    info = self.__audio.get_device_info_by_index(i)
                    log_str += f"\n\t[{i}] {info['name']} (channels: {info['maxInputChannels']})"
                self.__logger.error(log_str)

            # Return the found device index or None if not found
            return device_idx

    def connect(self) -> bool:
        """
        Initialize PyAudio and open audio stream from USB device.

        Parameters
        ----------
        None
        
        Returns
        -------
        bool
            True if connection successful, False otherwise
        """

        # Set return code to True by default
        ret_code = True

        # Try to initialize PyAudio and open stream
        try:
            # Initialize PyAudio instance
            self.__audio = pyaudio.PyAudio()

            # Log successful initialization
            self.__logger.info("PyAudio initialized")
            
            # Get device index for the configured source
            self.__device_index = self.__get_device_index()

            # Parse device info
            device_info = self.__audio.get_device_info_by_index(self.__device_index)

            # Get number of channels
            self.__channels = int(device_info['maxInputChannels'])
            
            # Open audio stream with the detected device index and parameters
            self.__stream = self.__audio.open(
                format = pyaudio.paInt16,
                channels = self.__channels,
                rate = self.__sample_rate,
                input = True,
                input_device_index = self.__device_index,
                frames_per_buffer = self.__frame_size
            )
            
            # Log successful connection
            self.__logger.info(f"USB interface connected: {device_info['name']}")
        
        # Catch exceptions during connection attempt
        except Exception as e:
            # Log unsuccessful connection
            self.__logger.error(f"Failed to connect USB interface: {str(e)}")

            # Attempt to cleanup resources if connection fails
            self.disconnect()

            # Set return code to false when exceptions occur
            ret_code = False
        
        # Return the result of the connection attempt
        return ret_code

    def disconnect(self) -> bool:
        """
        Close audio stream and cleanup resources.

        Parameters
        ----------
        None
        
        Returns
        -------
        bool
            True if cleanup was successful, False otherwise
        """

        # Set return code to True by default
        ret_code = True

        # Try to deinitialize PyAudio and close stream
        try:
            # Check if stream is open
            if self.__stream is not None:
                # Attempt to close the stream
                try:
                    # Stop stream
                    self.__stream.stop_stream()

                    # Close stream
                    self.__stream.close()

                    # Log successful stream closure
                    self.__logger.info("USB stream closed")

                # Catch exceptions during closure attempt
                except Exception as e:
                    # Log errors during stream closure
                    self.__logger.error(f"Error closing stream: {str(e)}")

                    # Set return code to false when exceptions occur
                    ret_code = False

                # Set stream to None regardless of closure success
                finally:
                    # Ensure stream is set to None to prevent further use
                    self.__stream = None
            
            # Check if PyAudio instance exists
            if self.__audio is not None:
                # Attempt to terminate PyAudio
                try:
                    # Terminate PyAudio instance
                    self.__audio.terminate()

                    # Log successful termination
                    self.__logger.info("PyAudio terminated")

                # Catch exceptions during termination attempt
                except Exception as e:
                    # Log errors during PyAudio termination
                    self.__logger.error(f"Error terminating PyAudio: {str(e)}")

                    # Set return code to false when exceptions occur
                    ret_code = False

                # Set PyAudio instance to None regardless of termination success
                finally:
                    # Ensure PyAudio instance is set to None to prevent further use
                    self.__audio = None
            
            # Log successful disconnection
            self.__logger.info("USB interface disconnected")
            
            # Return the result of the disconnection attempt
            return ret_code

    def get_audio(self) -> Optional[bytes]:
        """
        Read one frame of audio from USB device.

        Parameters
        ----------
        None
        
        Returns
        -------
        Optional[bytes]
            Audio frame as bytes (int16 format), or None if error occurs
            
        Notes
        -----
        Handles PyAudio version compatibility and stream errors gracefully.
        Input overflows and closed streams return None without raising exceptions,
        allowing the stream to recover on subsequent calls.
        """

        # Set return value to None by default
        data = None

        # Check if stream is open before attempting to read
        if self.__stream is None:
            # Log error when stream is not open
            self.__logger.error("USB interface not connected. Call connect() first.")

        else:
            # Attempt to read audio data from the stream with error handling
            try:
                # Read a frame of audio data from the stream
                data = self.__stream.read(self.__frame_size, exception_on_overflow=False)
            
            # Catch OSError which may occur during stream read attempts
            except OSError as e:
                # Check for common stream errors like input overflow or stream closure
                if "Input overflowed" in str(e) or "Stream closed" in str(e):
                    # Log warning for recoverable stream errors without flooding logs
                    self.__logger.debug(f"USB stream read warning: {str(e)}")

                    # Return empty data to allow stream to recover on next read attempt
                    data = {}

                else:
                    # Log other types of OSError that may indicate more serious issues
                    self.__logger.error(f"Error reading audio from USB: {str(e)}")

            # Catch any other exceptions that may occur during the read attempt
            except Exception as e:
                # Log unexpected errors during audio read attempts
                self.__logger.error(f"Error reading audio from USB: {str(e)}")

        # Return the audio data or None when errors occur
        return data

    @property
    def channels(self) -> int:
        """
        Get number of channels in the USB device.

        Parameters
        ----------
        None
        
        Returns
        -------
        int
            Number of input channels detected on the USB device
        """

        # Return the number of channels detected on the USB device
        return self.__channels
