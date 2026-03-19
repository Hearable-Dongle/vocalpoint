# Standard imports
from typing import Optional
import logging
import threading

# Local imports
from .bt import BT_Interface
from .usb import USB_Interface


class Audio_Interface():
    """
    Interface managing the audio streaming from USB input to Bluetooth output.
    """

    def __init__(
        self,
        bt_interface: BT_Interface,
        usb_interface: USB_Interface,
        logger: logging.Logger,
        channels: int
    ) -> None:
        """
        Initialize audio interface.
        
        Parameters
        ----------
        bt_interface : BT_Interface
            Bluetooth interface for writing audio frames to the sink device
        usb_interface : USB_Interface
            USB interface for capturing audio frames from the configured source
        logger : logging.Logger
            Logger instance for recording audio events and errors
        channels : int
            Number of audio channels to process (e.g. 1 for mono, 2 for stereo)

        Returns
        -------
        None
        """

        # Initialize instance variables
        self.__bt = bt_interface
        self.__usb = usb_interface
        self.__logger = logger
        self.__channels = channels
        self.__running: bool = False
        self.__thread: Optional[threading.Thread] = None

        # Define hardfault flag
        self.__hardfault: bool = False

    def __stream_audio(self):
        """
        Background audio streaming loop
        
        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        try:
            # Loop while running flag is set
            while self.__running:
                # Read audio frame from USB interface
                audio_frame = self.__usb.read_audio()

                # Check if USB read returned a frame of audio data
                if audio_frame is None:
                    # Log warning if read fails
                    self.__logger.warning("Failed to read audio frame")

                else:
                    # Process audio frame with callback function
                    processed_frame = callback(audio_frame, self.__channels)

                    # Write processed audio frame to Bluetooth interface
                    if not self.__bt.write_audio(processed_frame):
                        # Log warning if write fails
                        self.__logger.warning("Failed to write audio frame")

                # Update hardfault status based on USB and Bluetooth interfaces
                self.__hardfault = self.__usb.hardfault or self.__bt.hardfault

        # Catch any exceptions that occur during streaming to prevent thread from crashing
        except Exception as e:
            # Log the failure in the streaming process
            self.__logger.error(f"Error in audio streaming thread: {e}")

        finally:
            # Ensure running flag is cleared if thread exits due to exception
            self.__running = False
    
    def start(self) -> bool:
        """
        Start audio streaming in background thread
        
        Parameters
        ----------
        None

        Returns
        -------
        bool
            True if streaming started successfully, False otherwise
        """

        # Set return code to False by default
        ret_code = False

        # Check if already running to prevent multiple threads
        if not self.__running:
            # Set running flag
            self.__running = True

            # Start background thread for audio streaming
            self.__thread = threading.Thread(target = self.__stream_audio, daemon = False)

            # Start the thread before logging to ensure accurate timing of streaming start event
            self.__thread.start()

            # Log start of streaming after thread has been initiated to ensure accurate timing
            self.__logger.info("Audio streaming started")

            # Set return code to True if streaming started successfully
            ret_code = True

        else:
            # Log warning if start is called while already running, but do not raise exception
            self.__logger.warning("Audio streaming is already running")

        # Return the status of the start operation
        return ret_code
    
    def stop(self) -> bool:
        """
        Stop audio streaming thread
        
        Parameters
        ----------
        None

        Returns
        -------
        bool
            True if streaming stopped successfully, False otherwise
        """

        # Set return code to False by default
        ret_code = False

        # Check if running before attempting to stop to prevent unnecessary operations
        if self.__running:
            # Clear running flag to signal thread to stop
            self.__running = False

            # Check if thread was started before attempting to join
            if self.__thread:
                # Wait for thread to finish with timeout to prevent hanging indefinitely
                self.__thread.join(timeout=1.0)

                # Log stop of streaming after thread has been signaled to stop 
                self.__logger.info("Audio streaming stopped")

                # Set return code to True if streaming stopped successfully
                ret_code = True
            
            else:
                # Log warning if thread was not started, but do not raise exception
                self.__logger.warning("Audio streaming thread was not started")

        else:
            # Log warning if stop is called while not running, but do not raise exception
            self.__logger.warning("Audio streaming is not running")

        # Return the status of the stop operation
        return ret_code

    @property
    def running(self) -> bool:
        """
        Return running status of audio streaming thread
        
        Parameters
        ----------
        None

        Returns
        -------
        bool
            True if streaming thread is currently running, False otherwise
        """

        # Return the current running status
        return self.__running

    @property
    def hardfault(self) -> bool:
        """
        Return hardfault status of audio interface
        
        Parameters
        ----------
        None

        Returns
        -------
        bool
            True if either USB or Bluetooth interface is in hardfault state, False otherwise
        """

        # Return the current hardfault status
        return self.__hardfault
    