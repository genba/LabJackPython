"""
Multi-Platform Python wrapper that implements functions from the LabJack 
Windows UD Driver, and the LabJack Linux and Mac drivers.

Author LabJack Corporation

Version 0.7.0

For use with drivers:
    - Windows UD driver: 2.69
    - Linux driver: 1.1
    - Mac driver: 1.0


This python wrapper is intended to be used as an easy way to implement the 
Windows UD driver, the Mac driver or the Linux driver.  It uses the module ctypes 
to interface with the appropriate operating system LabJack driver.  For versions 
of Python older than 2.4 and older, CTypes is available at 
http://sourceforge.net/projects/ctypes/.  Python 2.5 and new comes with the ctypes
module as a standard.

Version History
    - 0.1.0: Converted many UD functions to Python using ctyes package.
    - 0.2.0: Made linux support for Open, Read, Write, and driverVersion.
    - 0.3.0: Made Mac support for Open, Read, Write, and driverVersion.
    - 0.4.0 Wrote initial epydoc documentation.
    - 0.5.0 December 12, 2006
        - Added Get Driver Version for Linux
        - Made windows functions return an error when called by a Linux or Mac OS.
        - Fixed a twos compliment problem with Read and Write functions
    - 0.5.1 January 8, 2007
        - Fixed an error with eGetRaw which disallowed x1 to be a double array.
        - Added a stream example program to the driver package.
    - 0.5.2 January 23, 2007
        - Added a DriverPresent function to test if the necessary drivers are present 
          for the wrapper to run.
    - 0.6.0 Febuary 6, 2007
        - Added the LJHash function which is used for authorizing LabJack devices.
    - 0.6.1 July 19, 2007
        - Updated the documentation concerning the mac support.
    - 0.6.2 October 10, 2007
        - Added Checksum functions to driver
        - Added windows functionality for write and read
        - Added example functions for sht commands and u3 feedback
    - 0.6.3 March 5, 2008
        - Fixed TCP read and write error
    - 0.6.4 July 31, 2008
        - Updated Examples/U3/u3.py
    - 0.7.0 November 18, 2008
        - Modified listAll to display device information in a different, more intuitive way.
        - Added a Device class for simplier usage
        - openLabJack can now search for devices to open via ipAddress, localID, or serialNumber
        - Put most functions into proper camelcase notation
        - Removed large static function encapsulating all functions.  Works as one module now.
        - Changed Read and Write to increase speed
        - Performed many other minor revisions.
"""

import ctypes
import os
import struct
from decimal import Decimal
import socket
import Modbus

from struct import pack, unpack

__version = "0.7.0"

DEBUG = False

#Define constants used as default parameters.
LJ_ctUSB = 1

SOCKET_TIMEOUT = 10
BROADCAST_SOCKET_TIMEOUT = 1

class LabJackException(Exception):
    """Custom Exception meant for dealing specifically with LabJack Exceptions.

    Error codes are either going to be a LabJackUD error code or a -1.  The -1 implies
    a python wrapper specific error.  
    
    WINDOWS ONLY
    If errorString is not specified then errorString is set by errorCode
    
    #TODO Make errorCode to errorString conversion for non windows systems.
    """
    def __init__(self, ec = 0, errorString = ''):
        self.errorCode = ec
        self.errorString = errorString

        if not self.errorString:
            try:
                pString = ctypes.create_string_buffer(256)
                staticLib.ErrorToString(ctypes.c_long(self.errorCode), ctypes.byref(pString))
                self.errorString = pString.value
            except:
                self.errorString = str(self.errorCode)
    
    def __str__(self):
          return self.errorString

def _loadLibrary():
    """_loadLibrary()
    Returns a ctypes dll pointer to the library.
    """
    if(os.name == 'posix'):
            try:
                return ctypes.cdll.LoadLibrary("liblabjackusb.so")
            except:
                try:
                    return ctypes.cdll.LoadLibrary("liblabjackusb.dylib")
                except:
                    raise LabJackException("Could not load labjackusb driver.  " + \
                                           "Ethernet connectivity availability only.")
    if(os.name == 'nt'):
        try:
            return ctypes.windll.LoadLibrary("labjackud")
        except:
            raise LabJackException("Could not load labjackud driver.")

staticLib = _loadLibrary()

class Device(object):
    """Device(handle, localID = None, serialNumber = None, ipAddress = "", type = None)
            
    Creates a simple 0 with the following functions:
    write(writeBuffer) -- Writes a buffer.
    writeRegister(addr, value) -- Writes a value to a modbus register
    read(numBytes) -- Reads until a packet is received.
    readRegister(addr, numReg = None, format = None) -- Reads a modbus register.
    ping() -- Pings the device.  Returns true if communication worked.
    close() -- Closes the device.
    reset() -- Resets the device.
    """
    def __init__(self, handle, localID = None, serialNumber = None, ipAddress = "", devType = None):
        self.handle = handle
        self.localID = localID
        self.serialNumber = serialNumber
        self.ipAddress = ipAddress
        self.devType = devType
        self.debug = False

    def write(self, writeBuffer, modbus = False, checksum = True):
        """write([writeBuffer], modbus = False)
            
        Writes the data contained in writeBuffer to the device.  writeBuffer must be a list of 
        bytes.
        """
        if self.handle is None:
            raise LabJackException("The device handle is None.")

        if checksum:
            setChecksum(writeBuffer)

        handle = self.handle

        if(isinstance(handle, UE9TCPHandle)):
            packFormat = "B" * len(writeBuffer)
            tempString = struct.pack(packFormat, *writeBuffer)
            if modbus is True:
                handle.modbus.send(tempString)
            else:
                handle.data.send(tempString)
        else:
            if os.name == 'posix':
                if modbus is True:
                    writeBuffer = [ 0, 0 ] + writeBuffer
                if self.debug: print "In write: ", writeBuffer
                newA = (ctypes.c_byte*len(writeBuffer))(0) 
                for i in range(len(writeBuffer)):
                    newA[i] = ctypes.c_byte(writeBuffer[i])
                writeBytes = staticLib.LJUSB_BulkWrite(handle, 1, \
                                                       ctypes.byref(newA), len(writeBuffer))
                if(writeBytes != len(writeBuffer)):
                    raise LabJackException("Could only write " + str(writeBytes) + \
                                           " of " + str(len(writeBuffer)) + " bytes")
            elif os.name == 'nt':
                if modbus is True:
                    writeBuffer = [ 0, 0 ] + writeBuffer
                eGetRaw(handle, LJ_ioRAW_OUT, 0, len(writeBuffer), writeBuffer)
        
    def read(self, numBytes, stream = False, modbus = False):
        """read(numBytes, stream = False, modbus = False)
            
        Blocking read until a packet is received.
        """
        readBytes = 0
        
        if self.handle is None:
            raise LabJackException("The device handle is None.")
        handle = self.handle
        
        if(isinstance(handle, UE9TCPHandle)):
            if stream is True:
                rcvString = handle.stream.recv(numBytes)
            else:
                if modbus is True:
                    try:
                        rcvString = handle.modbus.recv(numBytes)
                    except socket.error, e:
                        try:
                            if self.debug: print "Attempting connect in Read"
                            handle.modbus = socket.socket()
                            handle.modbus.connect((self.ipAddress, 502))
                            handle.modbus.settimeout(10)
                            raise LabJackException("Read had a problem, but it's ok now.")
                        except LabJackException, g:
                            raise g
                        except:
                            raise e
                else:
                    rcvString = handle.data.recv(numBytes)
            readBytes = len(rcvString)
            packFormat = "B" * readBytes
            rcvDataBuff = struct.unpack(packFormat, rcvString)
            return rcvDataBuff
        else:
            if(os.name == 'posix'):
                newA = (ctypes.c_byte*numBytes)()
                
                if(stream):
                    readBytes = staticLib.LJUSB_BulkRead(handle, 4, ctypes.byref(newA), numBytes)
                else:
                    readBytes = staticLib.LJUSB_BulkRead(handle, 2, ctypes.byref(newA), numBytes)
                return [(newA[i] & 0xff) for i in range(readBytes)]
            elif os.name == 'nt':
                tempBuff = [0] * numBytes
                return eGetRaw(handle, LJ_ioRAW_IN, 0, numBytes, tempBuff)[1]
    
    def readRegister(self, addr, numReg = None, format = None):
        """ Reads a specific register from the device and returns the value.
        Requires Modbus.py
        
        readHoldingRegister(addr, numReg = None, format = None)
        addr: The address you would like to read
        numReg: Number of consecutive addresses you would like to read
        format: the unpack format of the returned value ( '>f' or '>I')
        
        Modbus is not supported for UE9s over USB. If you try it, a LabJackException is raised.
        """
        
        if numReg == None:
            numReg = Modbus.calcNumberOfRegisters(addr)
        
        pkt = Modbus.readHoldingRegistersRequest(addr, numReg = numReg)
        pkt = [ ord(c) for c in pkt ]
        
        
        if self.debug: print "Sent: ", pkt
        
        numBytes = 9 + (2 * int(numReg))
        
        response = self._modbusWriteRead(pkt, numBytes)
        
        if self.debug: print "Response is: ", response
        
        packFormat = ">" + "B" * numBytes
        from struct import pack
        response = pack(packFormat, *response)
        
        if format == None and numReg == 2:
            format = '>f'
            
        value = Modbus.readHoldingRegistersResponse(response, payloadFormat=format)[0]
        
        return value
        
    def writeRegister(self, addr, value):
        """ 
        Writes a value to a register. Returns the value to be written, if successful.
        Requires Modbus.py
        
        writeRegister(self, addr, value)
        addr: The address you want to write to.
        value: The value, or list of values, you want to write.
        
        if you cannot write to that register, a LabJackException is raised.
        Modbus is not supported for UE9's over USB. If you try it, a LabJackException is raised.
        """
        
        if type(value) is list:
            return self.writeMultipleRegisters(addr, value)
        
        numReg = Modbus.calcNumberOfRegisters(addr)
        if numReg > 1:
            return self.writeFloatToRegister(addr, value)
        
        request = Modbus.writeRegisterRequest(addr, value)
        request = [ ord(c) for c in request ]
        numBytes = 12
        
        if self.debug: print "Sent: ", request
        
        response = self._modbusWriteRead(request, numBytes)
        if self.debug: print "Response is: ", response
            
        response = list(response)
        if self.debug: print "response from write is: ", response
        
        if request != response:
            raise LabJackException(0, "Error writing register. Make sure you're writing to an address that allows writes.")
        
        return str(value)
        
    def writeFloatToRegister(self, addr, value):
        numReg = 2
        # Function, Address, Num Regs, Byte count, Data
        payload = pack('>BHHBf', 0x10, addr, 0x02, 0x04, value)
        request = pack('>HHHB', 0, 0, len(payload)+1, 0xff) + payload
        request = [ ord(c) for c in request ]
        if self.debug: print "Request is: ", request
        numBytes = 14
        
        response = self._modbusWriteRead(request, numBytes)
        if self.debug: print "Response is: ", response
            
        response = list(response)
        if self.debug: print "response from write is: ", response

        return str(value)
        
    def writeMultipleRegisters(self, startAddr, values):
        request = Modbus.writeRegistersRequest(startAddr, values)
        request = [ ord(c) for c in request ]
        if self.debug: "Request is: ", request
        numBytes = 12
        
        response = self._modbusWriteRead(request, numBytes)
        if self.debug: print "Response is: ", response
            
        response = list(response)
        if self.debug: print "response from write is: ", response

        return str(values)
        
    
    def setDIOState(IOnum, state):
        value = (int(state) & 0x01)
        self.writeRegister(6000+IOnum, value)
        return True
    
    def _modbusWriteRead(self, request, numBytes):
        self.write(request, modbus = True, checksum = False)
        try:
            return self.read(numBytes, modbus = True)
        except LabJackException:
            self.write(request, modbus = True, checksum = False)
            return self.read(numBytes, modbus = True)
    
    def _checkCommandBytes(self, results, commandBytes):
        """
        Checks all the stuff from a command
        """
        size = len(commandBytes)
        if results[0] == 0xB8 and results[1] == 0xB8:
            raise LabJackException("Device detected a bad checksum.")
        elif results[1:(size+1)] != commandBytes:
            raise LabJackException("Got incorrect command bytes.")
        elif not verifyChecksum(results):
            raise LabJackException("Checksum was incorrect.")
        elif results[6] != 0:
            raise LabJackException("Command returned with error number %s" % results[6])
            
    def _writeRead(self, command, readLen, commandBytes, checkBytes = True, checksum = True):
        self.write(command, checksum = checksum)
        result = self.read(readLen)
        if self.debug: print "Result: ", result
        if checkBytes:
            self._checkCommandBytes(result, commandBytes)
        return result
    
    
    def ping(self):
        try:
            if self.devType == LJ_dtUE9:
                writeBuffer = [0x70, 0x70]
                self.write(writeBuffer)
                try:
                    self.read(2)
                except LabJackException:
                    self.write(writeBuffer)
                    self.read(2)
                return True
            
            if self.devType == LJ_dtU3:
                writeBuffer = [0, 0xf8, 0x01, 0x2a, 0, 0, 0, 0]
                writeBuffer = setChecksum(writeBuffer)
                self.write(writeBuffer)
                self.read(40)
                return True

            return False
        except Exception, e:
            print e
            return False
        

    def open(self, devType, Ethernet=False, firstFound = True, localId = None, devNumber = None, ipAddress = None):
        """
        Device.open(devType, Ethernet=False, firstFound = True, localId = None, devNumber = None, ipAddress = None)
        
        Open a device of type devType. 
        """
        ct = 1
        if Ethernet:
            ct = 2
        
        d = None
        if firstFound:
            d = openLabJack(devType, ct, firstFound = True)
        elif devNumber != None:
            d = openLabJack(devType, ct, firstFound = False, devNumber = devNumber)
        elif localId != None:
            d = openLabJack(devType, ct, firstFound = False, pAddress = localId)
        elif ipAddress != None:
            d = openLabJack(devType, ct, firstFound = False, pAddress = ipAddress)
        else:
            raise LabJackException("You must use first found, or give a localId, devNumber, or IP Address")
        
        self.handle = d.handle
        self.localId = d.localID
        self.serialNumber  = d.serialNumber
        
        if devType is 9:
            self.ipAddress = d.ipAddress

    def close(self):
        """close()
        
        This function is not specifically supported in the LabJackUD driver
        for Windows and so simply calls the UD function Close.  For Mac and unix
        drivers, this function MUST be performed when finished with a device.
        The reason for this close is because there can not be more than one program
        with a given device open at a time.  If a device is not closed before
        the program is finished it may still be held open and unable to be used
        by other programs until properly closed.
        
        For Windows, Linux, and Mac
        """
        if(os.name == 'posix'):
            if(isinstance(self.handle, UE9TCPHandle)):
                self.handle.close()
            else:    
                staticLib.LJUSB_CloseDevice(self.handle);
            
        self.handle = None

    def __repr__(self):
        return str(self.asDict())

    def asDict(self):
        return dict(devType = self.devType, localID = self.localID, serialNumber = self.serialNumber, ipAddress = self.ipAddress)

    def reset(self):
        """Reset the LabJack device.
    
        For Windows, Linux, and Mac
    
        Sample Usage:
    
        >>> u3 = OpenLabJack(LJ_dtU3, LJ_ctUSB, "0", 1)
        >>> u3.reset()
        
        @type  None
        @param Function takes no arguments
        
        @rtype: None
        @return: Function returns nothing.
            
        @raise LabJackException: 
        """        
        
        if os.name == 'nt':
            staticLib = ctypes.windll.LoadLibrary("labjackud")
            ec = staticLib.ResetLabJack(self.handle)
    
            if ec != 0: raise LabJackException(ec)
        elif os.name == 'posix':
            sndDataBuff = [0] * 4
            
            #Make the reset packet
            sndDataBuff[0] = 0x9B
            sndDataBuff[1] = 0x99
            sndDataBuff[2] = 0x02
            
            try:
                self.write(sndDataBuff)
                rcvDataBuff = self.read(4)
                if(len(rcvDataBuff) != 4):
                    raise LabJackException(0, "Unable to reset labJack 2")
            except Exception, e:
                raise LabJackException(0, "Unable to reset labjack: %s" % str(e))



# --------------------- BEGIN LabJackPython ---------------------------------

def setChecksum(command):
    """Returns a command with checksums places in the proper locations

    For Windows, Mac, and Linux
    
    Sample Usage:
    
    >>> from LabJackPython import *
    >>> command = [0] * 12
    >>> command[1] = 0xf8
    >>> command[2] = 0x03
    >>> command[3] = 0x0b
    >>> command = SetChecksum(command)
    >>> command
    [7, 248, 3, 11, 0, 0, 0, 0, 0, 0, 0, 0]

    @type  command: List
    @param command: The command by which to calculate the checksum

            
    @rtype: List
    @return: A command list with checksums in the proper locations.
    """  
    
    if len(command) < 8:
        raise LabJackException("Command does not contain enough bytes.")
    
    try:        
        a = command[1]
        
        a = (a & 0x78) >> 3
        
        #Check if the command is an extended command
        if a == 15:
            
            command = setChecksum16(command)
            command = setChecksum8(command, 6)
            return command
        else:
            command = setChecksum8(command, len(command))
            return command
    except LabJackException, e:
        raise e
    except Exception, e:
        raise LabJackException("SetChecksum Exception:" + str(e))



def verifyChecksum(buffer):
    """Verifies the checksum of a given buffer using the traditional U3/UE9 Command Structure.
    """
    
    buff0 = buffer[0]
    buff4 = buffer[4]
    buff5 = buffer[5]

    tempBuffer = setChecksum(buffer)
    
    if (buff0 == tempBuffer[0]) and (buff4 == tempBuffer[4]) \
    and (buff5 == tempBuffer[5]):
        return True

    return False


def listAll(deviceType, connectionType = LJ_ctUSB):
    """listAll(deviceType, connectionType) -> [[local ID, Serial Number, IP Address], ...]
    
    Searches for all devices of a given type over a given connection type and returns a list 
    of all devices found.
    
    WORKS on WINDOWS, MAC, UNIX
    """
    if deviceType == 12:
        if U12DriverPresent():
            u12Driver = ctypes.windll.LoadLibrary("ljackuw")
            
            # Setup all the ctype arrays
            pSerialNumbers = (ctypes.c_long * 127)(0)
            pIDs = (ctypes.c_long * 127)(0)
            pProdID = (ctypes.c_long * 127)(0)
            pPowerList = (ctypes.c_long * 127)(0)
            pCalMatrix = (ctypes.c_long * 2540)(0)
            pNumFound = ctypes.c_long()
            pFcdd = ctypes.c_long(0)
            pHvc = ctypes.c_long(0)
            
            #Output dictionary
            deviceList = {}
            
            ec = u12Driver.ListAll(ctypes.cast(pProdID, ctypes.POINTER(ctypes.c_long)),
                               ctypes.cast(pSerialNumbers, ctypes.POINTER(ctypes.c_long)),
                               ctypes.cast(pIDs, ctypes.POINTER(ctypes.c_long)),
                               ctypes.cast(pPowerList, ctypes.POINTER(ctypes.c_long)),
                               ctypes.cast(pCalMatrix, ctypes.POINTER(ctypes.c_long)),
                               ctypes.byref(pNumFound),
                               ctypes.byref(pFcdd),
                               ctypes.byref(pHvc))

            if ec != 0: raise LabJackException(ec)
            for i in range(pNumFound.value):
                deviceList[pSerialNumbers[i]] = { 'SerialNumber' : pSerialNumbers[i], 'Id' : pIDs[i], 'ProdId' : pProdID[i], 'powerList' : pPowerList[i] }
                
            return deviceList
    
            
        else:
            return {}
        
    
    if(os.name == 'nt'):
        pNumFound = ctypes.c_long()
        pSerialNumbers = (ctypes.c_long * 128)()
        pIDs = (ctypes.c_long * 128)()
        pAddresses = (ctypes.c_double * 128)()
        
        #The actual return variables so the user does not have to use ctypes
        serialNumbers = []
        ids = []
        addresses = []
        
        ec = staticLib.ListAll(deviceType, connectionType, 
                              ctypes.byref(pNumFound), 
                              ctypes.cast(pSerialNumbers, ctypes.POINTER(ctypes.c_long)), 
                              ctypes.cast(pIDs, ctypes.POINTER(ctypes.c_long)), 
                              ctypes.cast(pAddresses, ctypes.POINTER(ctypes.c_long)))
        
        if ec != 0: raise LabJackException(ec)
        
        deviceList = dict()
    
        for i in range(pNumFound.value):
            deviceValue = dict(localID = pIDs[i], serialNumber = pSerialNumbers[i], ipAddress = DoubleToStringAddress(pAddresses[i]), devType = deviceType)
            deviceList[pSerialNumbers[i]] = deviceValue
    
        return deviceList

    if(os.name == 'posix'):
        handle = None
    
        if deviceType == LJ_dtUE9:
            return __listAllUE9Unix(connectionType)
    
        if deviceType == LJ_dtU3:
            return __listAllU3Unix()
        
        if deviceType == 6:
            return __listAllU6Unix()

def deviceCount(devType = None):
    """Returns the number of devices connected. """
    if devType == None:
        numu3 = staticLib.LJUSB_GetDevCount(3)
        numue9 = staticLib.LJUSB_GetDevCount(9)
        return numu3 + numue9
    else:
        return staticLib.LJUSB_GetDevCount(devType)

#Windows, Linux, and Mac
def openLabJack(deviceType, connectionType, firstFound = True, pAddress = None, devNumber = None):
    """openLabJack(deviceType, connectionType, firstFound = True, pAddress = 1)
    
        Note: On Windows, Ue9 over Ethernet, pAddress MUST be the IP address. 
    """
    rcvDataBuff = []

    #If windows operating system then use the UD Driver
    if(os.name == 'nt'):
        handle = ctypes.c_long()
        pAddress = str(pAddress)
        ec = staticLib.OpenLabJack(deviceType, connectionType, 
                                    pAddress, firstFound, ctypes.byref(handle))

        if ec != 0: raise LabJackException(ec)
        devHandle = handle.value
        
        
        serial = int(eGet(devHandle, LJ_ioGET_CONFIG, LJ_chSERIAL_NUMBER, 0, 0))
        localId = int(eGet(devHandle, LJ_ioGET_CONFIG, LJ_chLOCALID, 0, 0))
        
        ipAddress = ""
        if(deviceType == LJ_dtUE9):
            ipAddress = DoubleToStringAddress(eGet(devHandle, LJ_ioGET_CONFIG, LJ_chIP_ADDRESS, 0, 0))
        
        return Device(devHandle, localID = localId, ipAddress = ipAddress, serialNumber = serial, devType = deviceType)

    # Linux/Mac need to work in the low level driver.
    if(os.name == 'posix'):
        if(connectionType == LJ_ctUSB):
            devType = ctypes.c_ulong(deviceType)
            openDev = staticLib.LJUSB_OpenDevice
            openDev.restype = ctypes.c_void_p
            
            if(devNumber != None):
                try:
                    handle = openDev(devNumber, 0, devType)
                    if handle <= 0:
                        raise Exception
                    return _makeDeviceFromHandle(handle, deviceType)
                except Exception, e:
                    print type(e), e
                    raise LabJackException(LJE_LABJACK_NOT_FOUND)
            elif(firstFound):
                try:
                    handle = openDev(1, 0, devType)
                    if handle <= 0:
                        raise Exception
                    return _makeDeviceFromHandle(handle, deviceType)
                except:
                    raise LabJackException(LJE_LABJACK_NOT_FOUND)
            else:            
                numDevices = staticLib.LJUSB_GetDevCount(deviceType)
                
                for i in range(numDevices):
              
                    handle = staticLib.LJUSB_OpenDevice(i + 1, 0, deviceType)
                    
                    try:
                        if handle <= 0:
                            raise Exception
                        device = _makeDeviceFromHandle(handle, deviceType)
                    except:
                        continue
                    
                    try:
                        if(device.localID == pAddress or device.serialNumber == pAddress or \
                                                                    device.ipAddress == pAddress):
                            return device
                    except:
                        pass
                    
                    device.close()
                
            raise LabJackException(LJE_LABJACK_NOT_FOUND)

    if(connectionType == LJ_ctETHERNET):
        if deviceType == LJ_dtUE9:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.settimeout(BROADCAST_SOCKET_TIMEOUT)

            sndDataBuff = [0] * 6
            sndDataBuff[0] = 0x22
            sndDataBuff[1] = 0x78
            sndDataBuff[3] = 0xa9

            outBuff = ""
            for item in sndDataBuff:
                outBuff += chr(item)
            s.sendto(outBuff, ("255.255.255.255", 52362))

            try:
                while True:
                    rcvDataBuff = s.recv(128)
                    try:
                        rcvDataBuff = [ord(val) for val in rcvDataBuff]
                        if verifyChecksum(rcvDataBuff):
                            #Parse the packet
                            macAddress = rcvDataBuff[28:34]
                            macAddress.reverse()

                            # The serial number is four bytes:
                            # 0x10 and the last three bytes of the MAC address
                            serialBytes = chr(0x10)
                            for j in macAddress[3:]:
                                serialBytes += chr(j)
                            serialNumber = struct.unpack(">I", serialBytes)[0]

                            #Parse out the IP address
                            ipAddress = ""
                            for j in range(13, 9, -1):
                                ipAddress += str(int(rcvDataBuff[j]))
                                ipAddress += "." 
                            ipAddress = ipAddress[0:-1]

                            #Local ID
                            localID = rcvDataBuff[8] & 0xff

                            try:
                                if(localID == pAddress or serialNumber == pAddress or \
                                                                        ipAddress == pAddress):
                                    handle = UE9TCPHandle(ipAddress)
                                    return Device(handle, localID, serialNumber, \
                                                  ipAddress, deviceType)
                            except Exception, e:
                                print e
                    except Exception, e:
                        pass
            except:
                raise LabJackException(LJE_LABJACK_NOT_FOUND)

def _makeDeviceFromHandle(handle, deviceType):
    """ A helper function to get set all the info about a device from a handle"""
    if(deviceType == LJ_dtUE9):
        device = Device(handle, devType = 9)
        
        sndDataBuff = [0] * 38
        sndDataBuff[0] = 0x89
        sndDataBuff[1] = 0x78
        sndDataBuff[2] = 0x10
        sndDataBuff[3] = 0x01
        
        try:
            device.write(sndDataBuff, checksum = False)
            rcvDataBuff = device.read(38)
        
            
            device.localID = rcvDataBuff[8] & 0xff
        
            macAddress = rcvDataBuff[28:34]
            macAddress.reverse()
        
            serialBytes = chr(0x10)
            for j in macAddress[3:]:
                serialBytes += chr(j)
            device.serialNumber = struct.unpack(">I", serialBytes)[0]
        
            #Parse out the IP address
            ipAddress = ""
            for j in range(13, 9, -1):
                ipAddress += str(int(rcvDataBuff[j]))
                ipAddress += "." 
            device.ipAddress = ipAddress[0:-1]
        except Exception, e:
            device.close()
            raise e
        
        
    if deviceType == LJ_dtU3:
        device = Device(handle, devType = 3)
        sndDataBuff = [0] * 26
        sndDataBuff[0] = 0x0b
        sndDataBuff[1] = 0xf8
        sndDataBuff[2] = 0x0a
        sndDataBuff[3] = 0x08
        
        try:
            device.write(sndDataBuff, checksum = False)
            rcvDataBuff = device.read(38) 
        except LabJackException, e:
            device.close()
            raise e
        
        device.localID = rcvDataBuff[21] & 0xff
        serialNumber = struct.pack("<BBBB", *rcvDataBuff[15:19])
        device.serialNumber = struct.unpack('<I', serialNumber)[0]
        device.ipAddress = ""
        
    if deviceType == 6:
        device = Device(handle, devType = 6)
        command = [ 0 ] * 26
        command[1] = 0xF8
        command[2] = 0x0A
        command[3] = 0x08
        try:
            device.write(command)
            rcvDataBuff = device.read(38)
        except LabJackException, e:
            device.close()
            raise e
        
        device.localID = rcvDataBuff[21] & 0xff
        serialNumber = struct.pack("<BBBB", *rcvDataBuff[15:19])
        device.serialNumber = struct.unpack('<I', serialNumber)[0]
        device.ipAddress = ""
        
    
    return device

def AddRequest(handle, IOType, Channel, Value, x1, UserData):
    """AddRequest(handle, ioType, channel, value, x1, userData)
        
    Windows Only
    """
    if os.name == 'nt':
        staticLib = ctypes.windll.LoadLibrary("labjackud")
        
        v = ctypes.c_double(Value)
        ud = ctypes.c_double(UserData)
        
        ec = staticLib.AddRequest(Handle, IOType, Channel, v, x1, ud)
        if ec != 0: raise LabJackException(ec)
    else:
       raise LabJackException(0, "Function only supported for Windows")


#Windows
def AddRequestS(Handle, pIOType, Channel, Value, x1, UserData):
    """Add a request to the LabJackUD request stack
    
    For Windows
    
    Sample Usage to get the AIN value from channel 0:
    
    >>> u3Handle = OpenLabJack(LJ_dtU3, LJ_ctUSB, "0", 1)
    >>> AddRequestS(u3Handle,"LJ_ioGET_AIN", 0, 0.0, 0, 0.0)
    >>> Go()
    >>> value = GetResult(u3Handle, LJ_ioGET_AIN, 0)
    >>> print "Value:" + str(value)
    Value:0.366420765873
    
    @type  Handle: number
    @param Handle: Handle to the LabJack device.
    @type  IOType: String
    @param IOType: IO Request to the LabJack.
    @type  Channel: number
    @param Channel: Channel for the IO request.
    @type  Value: number
    @param Value: Used for some requests
    @type  x1: number
    @param x1: Used for some requests
    @type  UserData: number
    @param UserData: Used for some requests
    
    @rtype: None
    @return: Function returns nothing.
    
    @raise LabJackException:
    """
    if os.name == 'nt':
        staticLib = ctypes.windll.LoadLibrary("labjackud")
        
        v = ctypes.c_double(Value)
        ud = ctypes.c_double(UserData)
        
        ec = staticLib.AddRequestS(Handle, pIOType, Channel, 
                                    v, x1, ud)

        if ec != 0: raise LabJackException(ec)
    else:
       raise LabJackException(0, "Function only supported for Windows")

#Windows
def AddRequestSS(Handle, pIOType, pChannel, Value, x1, UserData):
    """Add a request to the LabJackUD request stack
    
    For Windows
    
    Sample Usage to get the AIN value from channel 0:
    
    >>> u3Handle = OpenLabJack(LJ_dtU3, LJ_ctUSB, "0", 1)
    >>> AddRequestSS(u3Handle,"LJ_ioGET_CONFIG", "LJ_chFIRMWARE_VERSION", 0.0, 0, 0.0)
    >>> Go()
    >>> value = GetResultS(u3Handle, "LJ_ioGET_CONFIG", LJ_chFIRMWARE_VERSION)
    >>> print "Value:" + str(value)
    Value:1.27
    
    @type  Handle: number
    @param Handle: Handle to the LabJack device.
    @type  IOType: String
    @param IOType: IO Request to the LabJack.
    @type  Channel: String
    @param Channel: Channel for the IO request.
    @type  Value: number
    @param Value: Used for some requests
    @type  x1: number
    @param x1: Used for some requests
    @type  UserData: number
    @param UserData: Used for some requests
    
    @rtype: None
    @return: Function returns nothing.
    
    @raise LabJackException:
    """
    if os.name == 'nt':      
        staticLib = ctypes.windll.LoadLibrary("labjackud")
        
        v = ctypes.c_double(Value)
        ud = ctypes.c_double(UserData)
        
        ec = staticLib.AddRequestSS(Handle, pIOType, pChannel, 
                                     v, x1, ud)

        if ec != 0: raise LabJackException(ec)
    else:
       raise LabJackException(0, "Function only supported for Windows")

#Windows
def Go():
    """Complete all requests currently on the LabJackUD request stack

    For Windows Only
    
    Sample Usage:
    
    >>> u3Handle = OpenLabJack(LJ_dtU3, LJ_ctUSB, "0", 1)
    >>> AddRequestSS(u3Handle,"LJ_ioGET_CONFIG", "LJ_chFIRMWARE_VERSION", 0.0, 0, 0.0)
    >>> Go()
    >>> value = GetResultS(u3Handle, "LJ_ioGET_CONFIG", LJ_chFIRMWARE_VERSION)
    >>> print "Value:" + str(value)
    Value:1.27
    
    @rtype: None
    @return: Function returns nothing.
    
    @raise LabJackException:
    """
    
    if os.name == 'nt':
        staticLib = ctypes.windll.LoadLibrary("labjackud")           
        ec = staticLib.Go()

        if ec != 0: raise LabJackException(ec)
    else:
       raise LabJackException("Function only supported for Windows")

#Windows
def GoOne(Handle):
    """Performs the next request on the LabJackUD request stack
    
    For Windows Only
    
    Sample Usage:
    
    >>> u3Handle = OpenLabJack(LJ_dtU3, LJ_ctUSB, "0", 1)
    >>> AddRequestSS(u3Handle,"LJ_ioGET_CONFIG", "LJ_chFIRMWARE_VERSION", 0.0, 0, 0.0)
    >>> GoOne(u3Handle)
    >>> value = GetResultS(u3Handle, "LJ_ioGET_CONFIG", LJ_chFIRMWARE_VERSION)
    >>> print "Value:" + str(value)
    Value:1.27
    
    @type  Handle: number
    @param Handle: Handle to the LabJack device.
    
    @rtype: None
    @return: Function returns nothing.
    
    @raise LabJackException:
    """
    if os.name == 'nt':
        staticLib = ctypes.windll.LoadLibrary("labjackud")           
        ec = staticLib.GoOne(Handle)

        if ec != 0: raise LabJackException(ec)
    else:
       raise LabJackException(0, "Function only supported for Windows")

#Windows
def eGet(Handle, IOType, Channel, pValue, x1):
    """Perform one call to the LabJack Device
    
    eGet is equivilent to an AddRequest followed by a GoOne.
    
    For Windows Only
    
    Sample Usage:
    
    >>> eGet(u3Handle, LJ_ioGET_AIN, 0, 0, 0)
    0.39392614550888538
    
    @type  Handle: number
    @param Handle: Handle to the LabJack device.
    @type  IOType: number
    @param IOType: IO Request to the LabJack.
    @type  Channel: number
    @param Channel: Channel for the IO request.
    @type  Value: number
    @param Value: Used for some requests
    @type  x1: number
    @param x1: Used for some requests
    
    @rtype: number
    @return: Returns the value requested.
        - value
        
    @raise LabJackException:
    """
    if os.name == 'nt':
        staticLib = ctypes.windll.LoadLibrary("labjackud")
        pv = ctypes.c_double(pValue)
        #ppv = ctypes.pointer(pv)
        ec = staticLib.eGet(Handle, IOType, Channel, ctypes.byref(pv), x1)
        #staticLib.eGet.argtypes = [ctypes.c_long, ctypes.c_long, ctypes.c_long, ctypes.c_double, ctypes.c_long]
        #ec = staticLib.eGet(Handle, IOType, Channel, pValue, x1)
        
        if ec != 0: raise LabJackException(ec)
        #print "EGet:" + str(ppv)
        #print "Other:" + str(ppv.contents)
        return pv.value
    else:
       raise LabJackException(0, "Function only supported for Windows")


#Windows
#Raw method -- Used because x1 is an output
def eGetRaw(Handle, IOType, Channel, pValue, x1):
    """Perform one call to the LabJack Device as a raw command
    
    eGetRaw is equivilent to an AddRequest followed by a GoOne.
    
    For Windows Only
    
    Sample Usage (Calling a echo command):
    
    >>> sendBuff = [0] * 2
    >>> sendBuff[0] = 0x70
    >>> sendBuff[1] = 0x70
    >>> eGetRaw(ue9Handle, LJ_ioRAW_OUT, 0, len(sendBuff), sendBuff)
    (2.0, [112, 112])
    
    @type  Handle: number
    @param Handle: Handle to the LabJack device.
    @type  IOType: number
    @param IOType: IO Request to the LabJack.
    @type  Channel: number
    @param Channel: Channel for the IO request.
    @type  pValue: number
    @param Value: Length of the buffer.
    @type  x1: number
    @param x1: Buffer to send.
    
    @rtype: Tuple
    @return: The tuple (numBytes, returnBuffer)
        - numBytes (number)
        - returnBuffer (List)
        
    @raise LabJackException:
    """
    ec = 0
    x1Type = "int"
    if os.name == 'nt':
        staticLib = ctypes.windll.LoadLibrary("labjackud")

        digitalConst = [35, 36, 37, 45]
        pv = ctypes.c_double(pValue)

        #If IOType is digital then call eget with x1 as a long
        if IOType in digitalConst:
            ec = staticLib.eGet(Handle, IOType, Channel, ctypes.byref(pv), x1)
        else: #Otherwise as an array
            
            try:
                #Verify x1 is an array
                if len(x1) < 1:
                    raise LabJackException(0, "x1 is not a valid variable for the given IOType") 
            except Exception:
                raise LabJackException(0, "x1 is not a valid variable for the given IOType")  
            
            #Initialize newA
            newA = None
            if type(x1[0]) == int:
                newA = (ctypes.c_byte*len(x1))()
                for i in range(0, len(x1), 1):
                    newA[i] = ctypes.c_byte(x1[i])
            else:
                x1Type = "float"
                newA = (ctypes.c_double*len(x1))()
                for i in range(0, len(x1), 1):
                    newA[i] = ctypes.c_double(x1[i])

            ec = staticLib.eGet(Handle, IOType, Channel, ctypes.byref(pv), ctypes.byref(newA))
            x1 = [0] * len(x1)
            for i in range(len(x1)):
                x1[i] = newA[i]
                if(x1Type == "int"):
                    x1[i] = x1[i] & 0xff
            
        if ec != 0: raise LabJackException(ec)
        return pv.value, x1
    else:
       raise LabJackException(0, "Function only supported for Windows")

#Windows
def eGetS(Handle, pIOType, Channel, pValue, x1):
    """Perform one call to the LabJack Device
    
    eGet is equivilent to an AddRequest followed by a GoOne.
    
    For Windows Only
    
    Sample Usage:
    
    >>> eGet(u3Handle, "LJ_ioGET_AIN", 0, 0, 0)
    0.39392614550888538
    
    @type  Handle: number
    @param Handle: Handle to the LabJack device.
    @type  pIOType: String
    @param pIOType: IO Request to the LabJack.
    @type  Channel: number
    @param Channel: Channel for the IO request.
    @type  Value: number
    @param Value: Used for some requests
    @type  x1: number
    @param x1: Used for some requests
    
    @rtype: number
    @return: Returns the value requested.
        - value
        
    @raise LabJackException:
    """
    if os.name == 'nt':
        staticLib = ctypes.windll.LoadLibrary("labjackud")
        pv = ctypes.c_double(pValue)
        ec = staticLib.eGetS(Handle, pIOType, Channel, ctypes.byref(pv), x1)

        if ec != 0: raise LabJackException(ec)
        return pv.value
    else:
       raise LabJackException(0, "Function only supported for Windows")

#Windows
def eGetSS(Handle, pIOType, pChannel, pValue, x1):
    """Perform one call to the LabJack Device
    
    eGet is equivilent to an AddRequest followed by a GoOne.
    
    For Windows Only
    
    Sample Usage:
    
    >>> eGetSS(u3Handle,"LJ_ioGET_CONFIG", "LJ_chFIRMWARE_VERSION", 0, 0)
    1.27
    
    @type  Handle: number
    @param Handle: Handle to the LabJack device.
    @type  pIOType: String
    @param pIOType: IO Request to the LabJack.
    @type  Channel: String
    @param Channel: Channel for the IO request.
    @type  Value: number
    @param Value: Used for some requests
    @type  x1: number
    @param x1: Used for some requests
    
    @rtype: number
    @return: Returns the value requested.
        - value
        
    @raise LabJackException:
    """
    if os.name == 'nt':
        staticLib = ctypes.windll.LoadLibrary("labjackud")
        pv = ctypes.c_double(pValue)
        ec = staticLib.eGetSS(Handle, pIOType, pChannel, ctypes.byref(pv), x1)

        if ec != 0: raise LabJackException(ec)
        return pv.value
    else:
       raise LabJackException(0, "Function only supported for Windows")


#Windows
#Not currently implemented
def eGetRawS(Handle, pIOType, Channel, pValue, x1):
    """Function not yet implemented.
    
    For Windows only.
    """
    pass

#Windows
def ePut(Handle, IOType, Channel, Value, x1):
    """Put one value to the LabJack device
    
    ePut is equivilent to an AddRequest followed by a GoOne.
    
    For Windows Only
    
    Sample Usage:
    
    >>> u3Handle = OpenLabJack(LJ_dtU3, LJ_ctUSB, "0", 1)
    >>> eGet(u3Handle, LJ_ioGET_CONFIG, LJ_chLOCALID, 0, 0)
    0.0
    >>> ePut(u3Handle, LJ_ioPUT_CONFIG, LJ_chLOCALID, 8, 0)
    >>> eGet(u3Handle, LJ_ioGET_CONFIG, LJ_chLOCALID, 0, 0)
    8.0
    
    @type  Handle: number
    @param Handle: Handle to the LabJack device.
    @type  IOType: number
    @param IOType: IO Request to the LabJack.
    @type  Channel: number
    @param Channel: Channel for the IO request.
    @type  Value: number
    @param Value: Used for some requests
    @type  x1: number
    @param x1: Used for some requests
    
    @rtype: None
    @return: Function returns nothing.
    
    @raise LabJackException:
    """
    if os.name == 'nt':
        staticLib = ctypes.windll.LoadLibrary("labjackud")
        pv = ctypes.c_double(Value)
        ec = staticLib.ePut(Handle, IOType, Channel, pv, x1)

        if ec != 0: raise LabJackException(ec)
    else:
       raise LabJackException(0, "Function only supported for Windows")

#Windows
def ePutS(Handle, pIOType, Channel, Value, x1):
    """Put one value to the LabJack device
    
    ePut is equivilent to an AddRequest followed by a GoOne.
    
    For Windows Only
    
    Sample Usage:
    
    >>> u3Handle = OpenLabJack(LJ_dtU3, LJ_ctUSB, "0", 1)
    >>> eGet(u3Handle, LJ_ioGET_CONFIG, LJ_chLOCALID, 0, 0)
    0.0
    >>> ePutS(u3Handle, "LJ_ioPUT_CONFIG", LJ_chLOCALID, 8, 0)
    >>> eGet(u3Handle, LJ_ioGET_CONFIG, LJ_chLOCALID, 0, 0)
    8.0
    
    @type  Handle: number
    @param Handle: Handle to the LabJack device.
    @type  IOType: String
    @param IOType: IO Request to the LabJack.
    @type  Channel: number
    @param Channel: Channel for the IO request.
    @type  Value: number
    @param Value: Used for some requests
    @type  x1: number
    @param x1: Used for some requests
    
    @rtype: None
    @return: Function returns nothing.
    
    @raise LabJackException:
    """
    if os.name == 'nt':
        staticLib = ctypes.windll.LoadLibrary("labjackud")
        
        pv = ctypes.c_double(Value)
        ec = staticLib.ePutS(Handle, pIOType, Channel, pv, x1)

        if ec != 0: raise LabJackException(ec)
    else:
       raise LabJackException(0, "Function only supported for Windows")

#Windows
def ePutSS(Handle, pIOType, pChannel, Value, x1):
    """Put one value to the LabJack device
    
    ePut is equivilent to an AddRequest followed by a GoOne.
    
    For Windows Only
    
    Sample Usage:
    
    >>> u3Handle = OpenLabJack(LJ_dtU3, LJ_ctUSB, "0", 1)
    >>> eGet(u3Handle, LJ_ioGET_CONFIG, LJ_chLOCALID, 0, 0)
    0.0
    >>> ePutSS(u3Handle, "LJ_ioPUT_CONFIG", "LJ_chLOCALID", 8, 0)
    >>> eGet(u3Handle, LJ_ioGET_CONFIG, LJ_chLOCALID, 0, 0)
    8.0
    
    @type  Handle: number
    @param Handle: Handle to the LabJack device.
    @type  IOType: String
    @param IOType: IO Request to the LabJack.
    @type  Channel: String
    @param Channel: Channel for the IO request.
    @type  Value: number
    @param Value: Used for some requests
    @type  x1: number
    @param x1: Used for some requests
    
    @rtype: None
    @return: Function returns nothing.
    
    @raise LabJackException:
    """
    if os.name == 'nt':
        staticLib = ctypes.windll.LoadLibrary("labjackud")

        pv = ctypes.c_double(Value)
        ec = staticLib.ePutSS(Handle, pIOType, pChannel, pv, x1)

        if ec != 0: raise LabJackException(ec)
    else:
       raise LabJackException(0, "Function only supported for Windows")

#Windows
def GetResult(Handle, IOType, Channel):
    """Put one value to the LabJack device
    
    ePut is equivilent to an AddRequest followed by a GoOne.
    
    For Windows Only
    
    Sample Usage:
    
    >>> u3Handle = OpenLabJack(LJ_dtU3, LJ_ctUSB, "0", 1)
    >>> AddRequestSS(u3Handle,"LJ_ioGET_CONFIG", "LJ_chFIRMWARE_VERSION", 0.0, 0, 0.0)
    >>> GoOne(u3Handle)
    >>> value = GetResult(u3Handle, LJ_ioGET_CONFIG, LJ_chFIRMWARE_VERSION)
    >>> print "Value:" + str(value)
    Value:1.27
    
    @type  Handle: number
    @param Handle: Handle to the LabJack device.
    @type  IOType: number
    @param IOType: IO Request to the LabJack.
    @type  Channel: number
    @param Channel: Channel for the IO request.
    
    @rtype: number
    @return: The value requested.
        - value
        
    @raise LabJackException:
    """
    if os.name == 'nt':
        staticLib = ctypes.windll.LoadLibrary("labjackud")
        pv = ctypes.c_double()
        ec = staticLib.GetResult(Handle, IOType, Channel, ctypes.byref(pv))

        if ec != 0: raise LabJackException(ec)          
        return pv.value
    else:
       raise LabJackException(0, "Function only supported for Windows")

#Windows
def GetResultS(Handle, pIOType, Channel):
    """Put one value to the LabJack device
    
    ePut is equivilent to an AddRequest followed by a GoOne.
    
    For Windows Only
    
    Sample Usage:
    
    >>> u3Handle = OpenLabJack(LJ_dtU3, LJ_ctUSB, "0", 1)
    >>> AddRequestSS(u3Handle,"LJ_ioGET_CONFIG", "LJ_chFIRMWARE_VERSION", 0.0, 0, 0.0)
    >>> GoOne(u3Handle)
    >>> value = GetResultS(u3Handle, "LJ_ioGET_CONFIG", LJ_chFIRMWARE_VERSION)
    >>> print "Value:" + str(value)
    Value:1.27
    
    @type  Handle: number
    @param Handle: Handle to the LabJack device.
    @type  pIOType: String
    @param pIOType: IO Request to the LabJack.
    @type  Channel: number
    @param Channel: Channel for the IO request.
    
    @rtype: number
    @return: The value requested.
        - value
        
    @raise LabJackException:
    """
    if os.name == 'nt':
        staticLib = ctypes.windll.LoadLibrary("labjackud")
        pv = ctypes.c_double()
        ec = staticLib.GetResultS(Handle, pIOType, Channel, ctypes.byref(pv))

        if ec != 0: raise LabJackException(ec)          
        return pv.value
    else:
       raise LabJackException(0, "Function only supported for Windows")

#Windows
def GetResultSS(Handle, pIOType, pChannel):
    """Put one value to the LabJack device
    
    ePut is equivilent to an AddRequest followed by a GoOne.
    
    For Windows Only
    
    Sample Usage:
    
    >>> u3Handle = OpenLabJack(LJ_dtU3, LJ_ctUSB, "0", 1)
    >>> AddRequestSS(u3Handle,"LJ_ioGET_CONFIG", "LJ_chFIRMWARE_VERSION", 0.0, 0, 0.0)
    >>> GoOne(u3Handle)
    >>> value = GetResultSS(u3Handle, "LJ_ioGET_CONFIG", "LJ_chFIRMWARE_VERSION")
    >>> print "Value:" + str(value)
    Value:1.27
    
    @type  Handle: number
    @param Handle: Handle to the LabJack device.
    @type  pIOType: String
    @param pIOType: IO Request to the LabJack.
    @type  Channel: String
    @param Channel: Channel for the IO request.
    
    @rtype: number
    @return: The value requested.
        - value
        
    @raise LabJackException:
    """
    if os.name == 'nt':
        staticLib = ctypes.windll.LoadLibrary("labjackud")
        pv = ctypes.c_double()
        ec = staticLib.GetResultS(Handle, pIOType, pChannel, ctypes.byref(pv))

        if ec != 0: raise LabJackException(ec)          
        return pv.value
    else:
       raise LabJackException(0, "Function only supported for Windows")

#Windows
def GetFirstResult(Handle):
    """List All LabJack devices of a specific type over a specific connection type.

    For Windows only.

    Sample Usage (Shows getting the localID (8) and firmware version (1.27) of a U3 device):

    >>> u3Handle = OpenLabJack(LJ_dtU3, LJ_ctUSB, "0", 1)
    >>> AddRequest(u3Handle, LJ_ioGET_CONFIG, LJ_chLOCALID, 0, 0, 0)
    >>> AddRequest(u3Handle, LJ_ioGET_CONFIG, LJ_chFIRMWARE_VERSION, 0, 0, 0)
    >>> Go()
    >>> GetFirstResult(u3Handle)
    (1001, 0, 8.0, 0, 0.0)
    >>> GetNextResult(u3Handle)
    (1001, 11, 1.27, 0, 0.0)

    @type  DeviceType: number
    @param DeviceType: The LabJack device.
    @type  ConnectionType: number
    @param ConnectionType: The connection method (Ethernet/USB).
    
    @rtype: Tuple
    @return: The tuple (ioType, channel, value, x1, userData)
        - ioType (number): The io of the result.
        - serialNumber (number): The channel of the result.
        - value (number): The requested result.
        - x1 (number):  Used only in certain requests.
        - userData (number): Used only in certain requests.
        
    @raise LabJackException: 
    """   
    if os.name == 'nt':     
        staticLib = ctypes.windll.LoadLibrary("labjackud")
        pio = ctypes.c_long()
        pchan = ctypes.c_long()
        pv = ctypes.c_double()
        px = ctypes.c_long()
        pud = ctypes.c_double()
        ec = staticLib.GetFirstResult(Handle, ctypes.byref(pio), 
                                       ctypes.byref(pchan), ctypes.byref(pv), 
                                       ctypes.byref(px), ctypes.byref(pud))

        if ec != 0: raise LabJackException(ec)          
        return pio.value, pchan.value, pv.value, px.value, pud.value
    else:
       raise LabJackException(0, "Function only supported for Windows")

#Windows
def GetNextResult(Handle):
    """List All LabJack devices of a specific type over a specific connection type.

    For Windows only.

    Sample Usage (Shows getting the localID (8) and firmware version (1.27) of a U3 device):

    >>> u3Handle = OpenLabJack(LJ_dtU3, LJ_ctUSB, "0", 1)
    >>> AddRequest(u3Handle, LJ_ioGET_CONFIG, LJ_chLOCALID, 0, 0, 0)
    >>> AddRequest(u3Handle, LJ_ioGET_CONFIG, LJ_chFIRMWARE_VERSION, 0, 0, 0)
    >>> Go()
    >>> GetFirstResult(u3Handle)
    (1001, 0, 8.0, 0, 0.0)
    >>> GetNextResult(u3Handle)
    (1001, 11, 1.27, 0, 0.0)

    @type  DeviceType: number
    @param DeviceType: The LabJack device.
    @type  ConnectionType: number
    @param ConnectionType: The connection method (Ethernet/USB).
    
    @rtype: Tuple
    @return: The tuple (ioType, channel, value, x1, userData)
        - ioType (number): The io of the result.
        - serialNumber (number): The channel of the result.
        - value (number): The requested result.
        - x1 (number):  Used only in certain requests.
        - userData (number): Used only in certain requests.
        
    @raise LabJackException: 
    """ 
    if os.name == 'nt':
        staticLib = ctypes.windll.LoadLibrary("labjackud")
        pio = ctypes.c_long()
        pchan = ctypes.c_long()
        pv = ctypes.c_double()
        px = ctypes.c_long()
        pud = ctypes.c_double()
        ec = staticLib.GetNextResult(Handle, ctypes.byref(pio), 
                                       ctypes.byref(pchan), ctypes.byref(pv), 
                                       ctypes.byref(px), ctypes.byref(pud))

        if ec != 0: raise LabJackException(ec)          
        return pio.value, pchan.value, pv.value, px.value, pud.value
    else:
       raise LabJackException(0, "Function only supported for Windows")

#Windows
def DoubleToStringAddress(number):
    """Converts a number (base 10) to an IP string.
    
    For Windows

    Sample Usage:

    >>> DoubleToStringAddress(3232235985)
    '192.168.1.209'
    
    @type  number: number
    @param number: Number to be converted.
    
    @rtype: String
    @return: The IP string converted from the number (base 10).
        
    @raise LabJackException: 
    """ 
    number = int(number)
    address = "%i.%i.%i.%i" % ((number >> 8*3 & 0xFF), (number >> 8*2 & 0xFF), (number >> 8 & 0xFF), (number & 0xFF))
    return address

def StringToDoubleAddress(pString):
    """Converts an IP string to a number (base 10).

    Sample Usage:

    >>> StringToDoubleAddress("192.168.1.209")
    3232235985L
    
    @type  pString: String
    @param pString: String to be converted.
    
    @rtype: number
    @return: The number (base 10) that represents the IP string.
        
    @raise LabJackException: 
    """  
    parts = pString.split('.')
    
    if len(parts) is not 4:
        raise LabJackException(0, "IP address not correctly formatted")
    
    try:
        value = (int(parts[0]) << 8*3) + (int(parts[1]) << 8*2) + (int(parts[2]) << 8) + int(parts[3])
    except ValueError:
        raise LabJackException(0, "IP address not correctly formatted")
    
    return value

#Windows
def StringToConstant(pString):
    """Converts an LabJackUD valid string to its constant value.

    For Windows

    Sample Usage:

    >>> StringToConstant("LJ_dtU3")
    3
    
    @type  pString: String
    @param pString: String to be converted.
    
    @rtype: number
    @return: The number (base 10) that represents the LabJackUD string.
    """
    if os.name == 'nt':
        staticLib = ctypes.windll.LoadLibrary("labjackud")
        a = ctypes.create_string_buffer(pString, 256)
        return staticLib.StringToConstant(a)
    else:
       raise LabJackException(0, "Function only supported for Windows")

#Windows
def ErrorToString(ErrorCode):
    """Converts an LabJackUD valid error code to a String.

    For Windows

    Sample Usage:

    >>> ErrorToString(1007)
    'LabJack not found'
    
    @type  ErrorCode: number
    @param ErrorCode: Valid LabJackUD error code.
    
    @rtype: String
    @return: The string that represents the valid LabJackUD error code
    """
    if os.name == 'nt':
        staticLib = ctypes.windll.LoadLibrary("labjackud")
        pString = ctypes.create_string_buffer(256)
        staticLib.ErrorToString(ctypes.c_long(ErrorCode), ctypes.byref(pString))
        return pString.value
    else:
       raise LabJackException(0, "Function only supported for Windows")

#Windows, Linux, and Mac
def GetDriverVersion():
    """Converts an LabJackUD valid error code to a String.

    For Windows, Linux, and Mac

    Sample Usage:

    >>> GetDriverVersion()
    2.64
    
    >>> GetDriverVersion()
    Mac
    
    @rtype: number/String
    @return: Value of the driver version as a String
        - For Mac machines the return type is "Mac"
        - For Windows and Linux systems the return type is a number that represents the driver version
    """
    
    if os.name == 'nt':        
        staticLib = ctypes.windll.LoadLibrary("labjackud")
        staticLib.GetDriverVersion.restype = ctypes.c_float
        return str(staticLib.GetDriverVersion())
        
    elif os.name == 'posix':
        staticLib = None
        mac = 0
        try:
            staticLib = ctypes.cdll.LoadLibrary("liblabjackusb.so")
        except:
            try:
                staticLib = ctypes.cdll.LoadLibrary("liblabjackusb.dylib")
                mac = 1
            except:
                raise LabJackException("Get Driver Version function could not load library")

        #If not windows then return the operating system.
        if mac:
            return "Mac"
        staticLib.LJUSB_GetLibraryVersion.restype = ctypes.c_float
        #Return only two decimal places
        twoplaces = Decimal(10) ** -2
        return str(Decimal(str(staticLib.LJUSB_GetLibraryVersion())).quantize(twoplaces))
        
#Windows
def TCVoltsToTemp(TCType, TCVolts, CJTempK):
    """Converts a thermo couple voltage reading to an appropriate temperature reading.

    For Windows

    Sample Usage:

    >>> TCVoltsToTemp(LJ_ttK, 0.003141592, 297.038889)
    373.13353222244825
            
    @type  TCType: number
    @param TCType: The type of thermo couple used.
    @type  TCVolts: number
    @param TCVolts: The voltage reading from the thermo couple
    @type  CJTempK: number
    @param CJTempK: The cold junction temperature reading in Kelvin
    
    @rtype: number
    @return: The thermo couples temperature reading
        - pTCTempK
        
    @raise LabJackException:
    """
    if os.name == 'nt':
        staticLib = ctypes.windll.LoadLibrary("labjackud")
        pTCTempK = ctypes.c_double()
        ec = staticLib.TCVoltsToTemp(ctypes.c_long(TCType), ctypes.c_double(TCVolts), 
                                     ctypes.c_double(CJTempK), ctypes.byref(pTCTempK))

        if ec != 0: raise LabJackException(ec)          
        return pTCTempK.value
    else:
       raise LabJackException(0, "Function only supported for Windows")


#Windows 
def Close():
    """Resets the driver and closes all open handles.

    For Windows

    Sample Usage:

    >>> Close()
            
    @rtype: None
    @return: The function returns nothing.
    """    

    opSys = os.name
    
    if(opSys == 'nt'):
        staticLib = ctypes.windll.LoadLibrary("labjackud")
        staticLib.Close()
    else:
       raise LabJackException(0, "Function only supported for Windows")

#Windows, Linux and Mac
def DriverPresent():
    try:
        ctypes.windll.LoadLibrary("labjackud")
        return True
    except:
        try:
            ctypes.cdll.LoadLibrary("liblabjackusb.so")
            return True
        except:
            try:
                ctypes.cdll.LoadLibrary("liblabjackusb.dylib")
                return True
            except:
                return False
            return False
        return False
        
def U12DriverPresent():
    try:
        ctypes.windll.LoadLibrary("ljackuw")
        return True
    except:
        return False


#Windows only
def LJHash(hashStr, size):
    """An approximation of the md5 hashing algorithms.  

    For Windows
    
    An approximation of the md5 hashing algorithm.  Used 
    for authorizations on UE9 version 1.73 and higher and u3 
    version 1.35 and higher.

    @type  hashStr: String
    @param hashStr: String to be hashed.
    @type  size: number
    @param size: Amount of bytes to hash from the hashStr
            
    @rtype: String
    @return: The hashed string.
    """  
    
    print "Hash String:" + str(hashStr)
    
    outBuff = (ctypes.c_char * 16)()
    retBuff = ''
    
    staticLib = ctypes.windll.LoadLibrary("labjackud")
    
    ec = staticLib.LJHash(ctypes.cast(hashStr, ctypes.POINTER(ctypes.c_char)),
                          size, 
                          ctypes.cast(outBuff, ctypes.POINTER(ctypes.c_char)), 
                          0)
    if ec != 0: raise LabJackException(ec)

    for i in range(16):
        retBuff += outBuff[i]
        
    return retBuff
    
    
    
    
    
    
def __listAllUE9Unix(connectionType):
    """Private listAll function for use on unix and mac machines to find UE9s.
    """

    deviceList = {}
    rcvDataBuff = []

    if connectionType == LJ_ctUSB:
        numDevices = staticLib.LJUSB_GetDevCount(LJ_dtUE9)

        for i in range(numDevices):
            handle = staticLib.LJUSB_OpenDevice(i + 1, 0, LJ_dtUE9)
            device = Device(handle, devType = 9)
            #Construct a comm config packet
            sndDataBuff = [0] * 38
            sndDataBuff[1] = 0x78
            sndDataBuff[2] = 0x10
            sndDataBuff[3] = 0x01
            sndDataBuff = setChecksum(sndDataBuff)

            try:
                device.write(sndDataBuff)
                rcvDataBuff = device.read(38)

                #Parse the packet
                macAddress = rcvDataBuff[28:34]
                macAddress.reverse()

                # The serial number is four bytes:
                # 0x10 and the last three bytes of the MAC address
                serialBytes = chr(0x10)
                for j in macAddress[3:]:
                    serialBytes += chr(j)
                serial = struct.unpack(">I", serialBytes)[0]

                #Parse out the IP address
                ipAddress = ""
                for j in range(13, 9, -1):
                    ipAddress += str(int(rcvDataBuff[j]))
                    ipAddress += "." 
                ipAddress = ipAddress[0:-1]

                #Local ID
                localID = rcvDataBuff[8] & 0xff
                deviceList[serial] = dict(devType = LJ_dtUE9, localID = localID, \
                                                serialNumber = serial, ipAddress = ipAddress)
                device.close()
            except Exception, e:
                print e
                device.close()
                continue

    elif connectionType == LJ_ctETHERNET:
        #Create a socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.settimeout(BROADCAST_SOCKET_TIMEOUT)

        sndDataBuff = [0] * 6
        sndDataBuff[0] = 0x22
        sndDataBuff[1] = 0x78
        sndDataBuff[3] = 0xa9

        outBuff = ""
        for item in sndDataBuff:
            outBuff += chr(item)
        s.sendto(outBuff, ("255.255.255.255", 52362))

        try:
            while True:
                rcvDataBuff = s.recv(128)
                try:
                    rcvDataBuff = [ord(val) for val in rcvDataBuff]
                    if verifyChecksum(rcvDataBuff):
                        #Parse the packet
                        macAddress = rcvDataBuff[28:34]
                        macAddress.reverse()

                        # The serial number is four bytes:
                        # 0x10 and the last three bytes of the MAC address
                        serialBytes = chr(0x10)
                        for j in macAddress[3:]:
                            serialBytes += chr(j)
                        serial = struct.unpack(">I", serialBytes)[0]

                        #Parse out the IP address
                        ipAddress = ""
                        for j in range(13, 9, -1):
                            ipAddress += str(int(rcvDataBuff[j]))
                            ipAddress += "." 
                        ipAddress = ipAddress[0:-1]

                        #Local ID
                        localID = rcvDataBuff[8] & 0xff

                        deviceList[serial] = dict(devType = LJ_dtUE9, localID = localID, \
                                                    serialNumber = serial, ipAddress = ipAddress)
                except Exception, e:
                    pass
        except:
            pass

    return deviceList



def __listAllU3Unix():
    """Private listAll function for unix and mac machines.  Works on the U3 only.
    """
    deviceList = {}
    numDevices = staticLib.LJUSB_GetDevCount(LJ_dtU3)

    for i in range(numDevices):
        handle = staticLib.LJUSB_OpenDevice(i + 1, 0, LJ_dtU3)
        
        if handle == 0:
            continue
        
        device = Device(handle, devType = 3)
        sndDataBuff = [0] * 26
        sndDataBuff[1] = 0xf8
        sndDataBuff[2] = 0x0a
        sndDataBuff[3] = 0x08

        sndDataBuff = setChecksum(sndDataBuff)

        try:
            device.write(sndDataBuff)
            rcvDataBuff = device.read(38)
        except LabJackException, e:
            device.close()
            raise LabJackException("Error in listAllU3")

        serialNumber = struct.pack("<BBBB", *rcvDataBuff[15:19])
        serialNumber = struct.unpack('<I', serialNumber)[0]
        localID = rcvDataBuff[21] & 0xff
        deviceList[serialNumber] = dict(devType = LJ_dtU3, localID = localID, \
                                        serialNumber = serialNumber, ipAddress = None)
        device.close()

    return deviceList


def __listAllU6Unix():
    """ List all for U6's """
    deviceList = {}
    numDevices = staticLib.LJUSB_GetDevCount(6)

    for i in range(numDevices):
        handle = staticLib.LJUSB_OpenDevice(i + 1, 0, 6)
        
        if handle == 0:
            continue
        
        device = Device(handle, devType = 6)
        sndDataBuff = [0] * 26
        sndDataBuff[1] = 0xf8
        sndDataBuff[2] = 0x0a
        sndDataBuff[3] = 0x08

        try:
            device.write(sndDataBuff)
            rcvDataBuff = device.read(38)
        except LabJackException, e:
            device.close()
            raise LabJackException("Error in listAllU6")

        serialNumber = struct.pack("<BBBB", *rcvDataBuff[15:19])
        serialNumber = struct.unpack('<I', serialNumber)[0]
        localID = rcvDataBuff[21] & 0xff
        pro = False
        if rcvDataBuff[37] == 12:
            pro = True
        
        deviceList[serialNumber] = dict(devType = 6, localID = localID, \
                                        serialNumber = serialNumber, ipAddress = None, Pro=pro)
        device.close()

    return deviceList

def setChecksum16(buffer):
    total = 0;

    for i in range(6, len(buffer)):
        total += (buffer[i] & 0xff)

    buffer[4] = (total & 0xff)
    buffer[5] = ((total >> 8) & 0xff)

    return buffer


def setChecksum8(buffer, numBytes):
    total = 0

    for i in range(1, numBytes):
        total += (buffer[i] & 0xff)

    buffer[0] = (total & 0xff) + ((total >> 8) & 0xff)
    buffer[0] = (buffer[0] & 0xff) + ((buffer[0] >> 8) & 0xff)

    return buffer


#Class for handling UE9 TCP Connections
class UE9TCPHandle(object):
    """__UE9TCPHandle(ipAddress)

    Creates two sockets for the streaming and non streaming port on the UE9.  
    Only works on default ports (Data 52360, Stream 52361).
    """

    def __init__(self, ipAddress, timeout = SOCKET_TIMEOUT):
        try:
            print "Attempting connect in TCP Handle"
            self.data = socket.socket()
            self.data.connect((ipAddress, 52360))
            self.data.settimeout(timeout)

            self.stream = socket.socket()
            self.stream.connect((ipAddress, 52361))
            self.stream.settimeout(timeout)
            
            self.modbus = socket.socket()
            self.modbus.connect((ipAddress, 502))
            self.modbus.settimeout(timeout)
        except Exception, e:
            print e
            raise LabJackException("Could not connect to labjack at address: " + str(ipAddress))

    def close(self):
        try:
            self.data.close()
            self.stream.close()
            self.modbus.close()
        except Exception, e:
            print "UE9 Handle close exception: ", e
            pass


    
    
    
#device types
LJ_dtUE9 = 9
"""Device type for the UE9"""

LJ_dtU3 = 3
"""Device type for the U3"""

# connection types:
LJ_ctUSB = 1 # UE9 + U3
"""Connection type for the UE9 and U3"""
LJ_ctETHERNET = 2 # UE9 only
"""Connection type for the UE9"""

LJ_ctUSB_RAW = 101 # UE9 + U3
"""Connection type for the UE9 and U3

Raw connection types are used to open a device but not communicate with it
should only be used if the normal connection types fail and for testing.
If a device is opened with the raw connection types, only LJ_ioRAW_OUT
and LJ_ioRAW_IN io types should be used
"""

LJ_ctETHERNET_RAW = 102 # UE9 only
"""Connection type for the UE9

Raw connection types are used to open a device but not communicate with it
should only be used if the normal connection types fail and for testing.
If a device is opened with the raw connection types, only LJ_ioRAW_OUT
and LJ_ioRAW_IN io types should be used
"""


# io types:
LJ_ioGET_AIN = 10 # UE9 + U3.  This is single ended version.
"""IO type for the UE9 and U3

This is the single ended version
"""  

LJ_ioGET_AIN_DIFF = 15 # U3 only.  Put second channel in x1.  If 32 is passed as x1, Vref will be added to the result. 
"""IO type for the U3

Put second channel in x1.  If 32 is passed as x1, Vref will be added to the result. 
"""

LJ_ioPUT_AIN_RANGE = 2000 # UE9
"""IO type for the UE9"""

LJ_ioGET_AIN_RANGE = 2001 # UE9
"""IO type for the UE9"""

# sets or reads the analog or digital mode of the FIO and EIO pins.     FIO is Channel 0-7, EIO 8-15
LJ_ioPUT_ANALOG_ENABLE_BIT = 2013 # U3 
"""IO type for the U3

Sets or reads the analog or digital mode of the FIO and EIO pins.     FIO is Channel 0-7, EIO 8-15
"""

LJ_ioGET_ANALOG_ENABLE_BIT = 2014 # U3 
"""IO type for the U3

Sets or reads the analog or digital mode of the FIO and EIO pins.     FIO is Channel 0-7, EIO 8-15
"""


# sets or reads the analog or digital mode of the FIO and EIO pins. Channel is starting 
# bit #, x1 is number of bits to read. The pins are set by passing a bitmask as a double
# for the value.  The first bit of the int that the double represents will be the setting 
# for the pin number sent into the channel variable. 
LJ_ioPUT_ANALOG_ENABLE_PORT = 2015 # U3 
""" IO type for the U3

sets or reads the analog or digital mode of the FIO and EIO pins. Channel is starting 
bit #, x1 is number of bits to read. The pins are set by passing a bitmask as a double
for the value.  The first bit of the int that the double represents will be the setting 
for the pin number sent into the channel variable.
"""

LJ_ioGET_ANALOG_ENABLE_PORT = 2016 # U3
""" IO type for the U3

sets or reads the analog or digital mode of the FIO and EIO pins. Channel is starting 
bit #, x1 is number of bits to read. The pins are set by passing a bitmask as a double
for the value.  The first bit of the int that the double represents will be the setting 
for the pin number sent into the channel variable.
"""


LJ_ioPUT_DAC = 20 # UE9 + U3
"""IO type for the U3 and UE9"""
LJ_ioPUT_DAC_ENABLE = 2002 # UE9 + U3 (U3 on Channel 1 only)
"""IO type for the U3 and UE9

U3 on channel 1 only.
"""
LJ_ioGET_DAC_ENABLE = 2003 # UE9 + U3 (U3 on Channel 1 only)
"""IO type for the U3 and UE9

U3 on channel 1 only.
"""

LJ_ioGET_DIGITAL_BIT = 30 # UE9 + U3  # changes direction of bit to input as well
LJ_ioGET_DIGITAL_BIT_DIR = 31 # U3
LJ_ioGET_DIGITAL_BIT_STATE = 32 # does not change direction of bit, allowing readback of output

# channel is starting bit #, x1 is number of bits to read 
LJ_ioGET_DIGITAL_PORT = 35 # UE9 + U3  # changes direction of bits to input as well
LJ_ioGET_DIGITAL_PORT_DIR = 36 # U3
LJ_ioGET_DIGITAL_PORT_STATE = 37 # U3 does not change direction of bits, allowing readback of output

# digital put commands will set the specified digital line(s) to output
LJ_ioPUT_DIGITAL_BIT = 40 # UE9 + U3
# channel is starting bit #, value is output value, x1 is bits to write
LJ_ioPUT_DIGITAL_PORT = 45 # UE9 + U3

# Used to create a pause between two events in a U3 low-level feedback
# command.    For example, to create a 100 ms positive pulse on FIO0, add a
# request to set FIO0 high, add a request for a wait of 100000, add a
# request to set FIO0 low, then Go.     Channel is ignored.  Value is
# microseconds to wait and should range from 0 to 8388480.    The actual
# resolution of the wait is 128 microseconds.
LJ_ioPUT_WAIT = 70 # U3

# counter.    Input only.
LJ_ioGET_COUNTER = 50 # UE9 + U3

LJ_ioPUT_COUNTER_ENABLE = 2008 # UE9 + U3
LJ_ioGET_COUNTER_ENABLE = 2009 # UE9 + U3


# this will cause the designated counter to reset.    If you want to reset the counter with
# every read, you have to use this command every time.
LJ_ioPUT_COUNTER_RESET = 2012  # UE9 + U3 


# on UE9: timer only used for input. Output Timers don't use these.     Only Channel used.
# on U3: Channel used (0 or 1).     
LJ_ioGET_TIMER = 60 # UE9 + U3

LJ_ioPUT_TIMER_VALUE = 2006 # UE9 + U3.     Value gets new value
LJ_ioPUT_TIMER_MODE = 2004 # UE9 + U3.    On both Value gets new mode.  
LJ_ioGET_TIMER_MODE = 2005 # UE9

# IOTypes for use with SHT sensor.    For LJ_ioSHT_GET_READING, a channel of LJ_chSHT_TEMP (5000) will 
# read temperature, and LJ_chSHT_RH (5001) will read humidity.    
# The LJ_ioSHT_DATA_CHANNEL and LJ_ioSHT_SCK_CHANNEL iotypes use the passed channel 
# to set the appropriate channel for the data and SCK lines for the SHT sensor. 
# Default digital channels are FIO0 for the data channel and FIO1 for the clock channel. 
LJ_ioSHT_GET_READING = 500 # UE9 + U3.
LJ_ioSHT_DATA_CHANNEL = 501 # UE9 + U3. Default is FIO0
LJ_ioSHT_CLOCK_CHANNEL = 502 # UE9 + U3. Default is FIO1

# Uses settings from LJ_chSPI special channels (set with LJ_ioPUT_CONFIG) to communcaite with
# something using an SPI interface.     The value parameter is the number of bytes to transfer
# and x1 is the address of the buffer.    The data from the buffer will be sent, then overwritten
# with the data read.  The channel parameter is ignored. 
LJ_ioSPI_COMMUNICATION = 503 # UE9
LJ_ioI2C_COMMUNICATION = 504 # UE9 + U3
LJ_ioASYNCH_COMMUNICATION = 505 # UE9 + U3
LJ_ioTDAC_COMMUNICATION = 506 # UE9 + U3

# Set's the U3 to it's original configuration.    This means sending the following
# to the ConfigIO and TimerClockConfig low level functions
#
# ConfigIO
# Byte #
# 6          WriteMask          15      Write all parameters.
# 8          TimerCounterConfig      0          No timers/counters.  Offset=0.
# 9          DAC1Enable      0          DAC1 disabled.
# 10      FIOAnalog          0          FIO all digital.
# 11      EIOAnalog          0          EIO all digital.
# 
# 
# TimerClockConfig
# Byte #
# 8          TimerClockConfig          130      Set clock to 24 MHz.
# 9          TimerClockDivisor          0          Divisor = 0.

# 
LJ_ioPIN_CONFIGURATION_RESET = 2017 # U3

# the raw in/out are unusual, channel # corresponds to the particular comm port, which 
# depends on the device.  For example, on the UE9, 0 is main comm port, and 1 is the streaming comm.
# Make sure and pass a porter to a char buffer in x1, and the number of bytes desired in value.     A call 
# to GetResult will return the number of bytes actually read/written.  The max you can send out in one call
# is 512 bytes to the UE9 and 16384 bytes to the U3.
LJ_ioRAW_OUT = 100 # UE9 + U3
LJ_ioRAW_IN = 101 # UE9 + U3
# sets the default power up settings based on the current settings of the device AS THIS DLL KNOWS.     This last part
# basically means that you should set all parameters directly through this driver before calling this.    This writes 
# to flash which has a limited lifetime, so do not do this too often.  Rated endurance is 20,000 writes.
LJ_ioSET_DEFAULTS = 103 # U3

# requests to create the list of channels to stream.  Usually you will use the CLEAR_STREAM_CHANNELS request first, which
# will clear any existing channels, then use ADD_STREAM_CHANNEL multiple times to add your desired channels.  Some devices will 
# use value, x1 for other parameters such as gain.    Note that you can do CLEAR, and then all your ADDs in a single Go() as long
# as you add the requests in order.
LJ_ioADD_STREAM_CHANNEL = 200
LJ_ioCLEAR_STREAM_CHANNELS = 201
LJ_ioSTART_STREAM = 202
LJ_ioSTOP_STREAM = 203
 
LJ_ioADD_STREAM_CHANNEL_DIFF = 206

# Get stream data has several options.    If you just want to get a single channel's data (if streaming multiple channels), you 
# can pass in the desired channel #, then the number of data points desired in Value, and a pointer to an array to put the 
# data into as X1.    This array needs to be an array of doubles. Therefore, the array needs to be 8 * number of 
# requested data points in byte length. What is returned depends on the StreamWaitMode.     If None, this function will only return 
# data available at the time of the call.  You therefore must call GetResult() for this function to retrieve the actually number 
# of points retreived.    If Pump or Sleep, it will return only when the appropriate number of points have been read or no 
# new points arrive within 100ms.  Since there is this timeout, you still need to use GetResult() to determine if the timeout 
# occured.    If AllOrNone, you again need to check GetResult.  

# You can also retreive the entire scan by passing LJ_chALL_CHANNELS.  In this case, the Value determines the number of SCANS 
# returned, and therefore, the array must be 8 * number of scans requested * number of channels in each scan.  Likewise
# GetResult() will return the number of scans, not the number of data points returned.

# Note: data is stored interleaved across all streaming channels.  In other words, if you are streaming two channels, 0 and 1, 
# and you request LJ_chALL_CHANNELS, you will get, Channel0, Channel1, Channel0, Channel1, etc.     Once you have requested the 
# data, any data returned is removed from the internal buffer, and the next request will give new data.

# Note: if reading the data channel by channel and not using LJ_chALL_CHANNELS, the data is not removed from the internal buffer
# until the data from the last channel in the scan is requested.  This means that if you are streaming three channels, 0, 1 and 2,
# and you request data from channel 0, then channel 1, then channel 0 again, the request for channel 0 the second time will 
# return the exact same amount of data.     Also note, that the amount of data that will be returned for each channel request will be
# the same until you've read the last channel in the scan, at which point your next block may be a different size.

# Note: although more convenient, requesting individual channels is slightly slower then using LJ_chALL_CHANNELS.  Since you 
# are probably going to have to split the data out anyway, we have saved you the trouble with this option.    

# Note: if you are only scanning one channel, the Channel parameter is ignored.

LJ_ioGET_STREAM_DATA = 204
        
# U3 only:

# Channel = 0 buzz for a count, Channel = 1 buzz continuous
# Value is the Period
# X1 is the toggle count when channel = 0
LJ_ioBUZZER = 300 # U3 

# config iotypes:
LJ_ioPUT_CONFIG = 1000 # UE9 + U3
LJ_ioGET_CONFIG = 1001 # UE9 + U3


# channel numbers used for CONFIG types:
# UE9 + U3
LJ_chLOCALID = 0 # UE9 + U3
LJ_chHARDWARE_VERSION = 10 # UE9 + U3 (Read Only)
LJ_chSERIAL_NUMBER = 12 # UE9 + U3 (Read Only)
LJ_chFIRMWARE_VERSION = 11 # UE9 + U3 (Read Only)
LJ_chBOOTLOADER_VERSION = 15 # UE9 + U3 (Read Only)

# UE9 specific:
LJ_chCOMM_POWER_LEVEL = 1 #UE9
LJ_chIP_ADDRESS = 2 #UE9
LJ_chGATEWAY = 3 #UE9
LJ_chSUBNET = 4 #UE9
LJ_chPORTA = 5 #UE9
LJ_chPORTB = 6 #UE9
LJ_chDHCP = 7 #UE9
LJ_chPRODUCTID = 8 #UE9
LJ_chMACADDRESS = 9 #UE9
LJ_chCOMM_FIRMWARE_VERSION = 11     
LJ_chCONTROL_POWER_LEVEL = 13 #UE9 
LJ_chCONTROL_FIRMWARE_VERSION = 14 #UE9 (Read Only)
LJ_chCONTROL_BOOTLOADER_VERSION = 15 #UE9 (Read Only)
LJ_chCONTROL_RESET_SOURCE = 16 #UE9 (Read Only)
LJ_chUE9_PRO = 19 # UE9 (Read Only)

# U3 only:
# sets the state of the LED 
LJ_chLED_STATE = 17 # U3   value = LED state
LJ_chSDA_SCL = 18 # U3     enable / disable SDA/SCL as digital I/O


# Used to access calibration and user data.     The address of an array is passed in as x1.
# For the UE9, a 1024-element buffer of bytes is passed for user data and a 128-element
# buffer of doubles is passed for cal constants.
# For the U3, a 256-element buffer of bytes is passed for user data and a 12-element
# buffer of doubles is passed for cal constants.
# The layout of cal ants are defined in the users guide for each device.
# When the LJ_chCAL_CONSTANTS special channel is used with PUT_CONFIG, a
# special value (0x4C6C) must be passed in to the Value parameter. This makes it
# more difficult to accidently erase the cal constants.     In all other cases the Value
# parameter is ignored.
LJ_chCAL_CONSTANTS = 400 # UE9 + U3
LJ_chUSER_MEM = 402 # UE9 + U3

# Used to write and read the USB descriptor strings.  This is generally for OEMs
# who wish to change the strings.
# Pass the address of an array in x1.  Value parameter is ignored.
# The array should be 128 elements of bytes.  The first 64 bytes are for the
# iManufacturer string, and the 2nd 64 bytes are for the iProduct string.
# The first byte of each 64 byte block (bytes 0 and 64) contains the number
# of bytes in the string.  The second byte (bytes 1 and 65) is the USB spec
# value for a string descriptor (0x03).     Bytes 2-63 and 66-127 contain unicode
# encoded strings (up to 31 characters each).
LJ_chUSB_STRINGS = 404 # U3


# timer/counter related
LJ_chNUMBER_TIMERS_ENABLED = 1000 # UE9 + U3
LJ_chTIMER_CLOCK_BASE = 1001 # UE9 + U3
LJ_chTIMER_CLOCK_DIVISOR = 1002 # UE9 + U3
LJ_chTIMER_COUNTER_PIN_OFFSET = 1003 # U3

# AIn related
LJ_chAIN_RESOLUTION = 2000 # ue9 + u3
LJ_chAIN_SETTLING_TIME = 2001 # ue9 + u3
LJ_chAIN_BINARY = 2002 # ue9 + u3

# DAC related
LJ_chDAC_BINARY = 3000 # ue9 + u3

# SHT related
LJ_chSHT_TEMP = 5000 # ue9 + u3
LJ_chSHT_RH = 5001 # ue9 + u3

# SPI related
LJ_chSPI_AUTO_CS = 5100 # UE9
LJ_chSPI_DISABLE_DIR_CONFIG = 5101 # UE9
LJ_chSPI_MODE = 5102 # UE9
LJ_chSPI_CLOCK_FACTOR = 5103 # UE9
LJ_chSPI_MOSI_PINNUM = 5104 # UE9
LJ_chSPI_MISO_PINNUM = 5105 # UE9
LJ_chSPI_CLK_PINNUM = 5106 # UE9
LJ_chSPI_CS_PINNUM = 5107 # UE9

# I2C related :
# used with LJ_ioPUT_CONFIG
LJ_chI2C_ADDRESS_BYTE = 5108 # UE9 + U3
LJ_chI2C_SCL_PIN_NUM = 5109 # UE9 + U3
LJ_chI2C_SDA_PIN_NUM = 5110 # UE9 + U3
LJ_chI2C_OPTIONS = 5111 # UE9 + U3
LJ_chI2C_SPEED_ADJUST = 5112 # UE9 + U3

# used with LJ_ioI2C_COMMUNICATION :
LJ_chI2C_READ = 5113 # UE9 + U3
LJ_chI2C_WRITE = 5114 # UE9 + U3
LJ_chI2C_GET_ACKS = 5115 # UE9 + U3
LJ_chI2C_WRITE_READ = 5130 # UE9 + U3

# ASYNCH related :
# Used with LJ_ioASYNCH_COMMUNICATION
LJ_chASYNCH_RX = 5117 # UE9 + U3
LJ_chASYNCH_TX = 5118 # UE9 + U3
LJ_chASYNCH_FLUSH = 5128 # UE9 + U3
LJ_chASYNCH_ENABLE = 5129 # UE9 + U3

# Used with LJ_ioPUT_CONFIG and LJ_ioGET_CONFIG
LJ_chASYNCH_BAUDFACTOR = 5127 # UE9 + U3

# stream related.  Note, Putting to any of these values will stop any running streams.
LJ_chSTREAM_SCAN_FREQUENCY = 4000
LJ_chSTREAM_BUFFER_SIZE = 4001
LJ_chSTREAM_CLOCK_OUTPUT = 4002
LJ_chSTREAM_EXTERNAL_TRIGGER = 4003
LJ_chSTREAM_WAIT_MODE = 4004
# readonly stream related
LJ_chSTREAM_BACKLOG_COMM = 4105
LJ_chSTREAM_BACKLOG_CONTROL = 4106
LJ_chSTREAM_BACKLOG_UD = 4107
LJ_chSTREAM_SAMPLES_PER_PACKET = 4108


# special channel #'s
LJ_chALL_CHANNELS = -1
LJ_INVALID_CONSTANT = -999


#Thermocouple Type constants.
LJ_ttB = 6001
"""Type B thermocouple constant"""
LJ_ttE = 6002
"""Type E thermocouple constant"""
LJ_ttJ = 6003
"""Type J thermocouple constant"""
LJ_ttK = 6004
"""Type K thermocouple constant"""
LJ_ttN = 6005
"""Type N thermocouple constant"""
LJ_ttR = 6006
"""Type R thermocouple constant"""
LJ_ttS = 6007
"""Type S thermocouple constant"""
LJ_ttT = 6008
"""Type T thermocouple constant"""


# other constants:
# ranges (not all are supported by all devices):
LJ_rgBIP20V = 1     # -20V to +20V
LJ_rgBIP10V = 2     # -10V to +10V
LJ_rgBIP5V = 3     # -5V to +5V
LJ_rgBIP4V = 4     # -4V to +4V
LJ_rgBIP2P5V = 5 # -2.5V to +2.5V
LJ_rgBIP2V = 6     # -2V to +2V
LJ_rgBIP1P25V = 7# -1.25V to +1.25V
LJ_rgBIP1V = 8     # -1V to +1V
LJ_rgBIPP625V = 9# -0.625V to +0.625V

LJ_rgUNI20V = 101  # 0V to +20V
LJ_rgUNI10V = 102  # 0V to +10V
LJ_rgUNI5V = 103   # 0V to +5V
LJ_rgUNI4V = 104   # 0V to +4V
LJ_rgUNI2P5V = 105 # 0V to +2.5V
LJ_rgUNI2V = 106   # 0V to +2V
LJ_rgUNI1P25V = 107# 0V to +1.25V
LJ_rgUNI1V = 108   # 0V to +1V
LJ_rgUNIP625V = 109# 0V to +0.625V
LJ_rgUNIP500V = 110 # 0V to +0.500V
LJ_rgUNIP3125V = 111 # 0V to +0.3125V

# timer modes (UE9 only):
LJ_tmPWM16 = 0 # 16 bit PWM
LJ_tmPWM8 = 1 # 8 bit PWM
LJ_tmRISINGEDGES32 = 2 # 32-bit rising to rising edge measurement
LJ_tmFALLINGEDGES32 = 3 # 32-bit falling to falling edge measurement
LJ_tmDUTYCYCLE = 4 # duty cycle measurement
LJ_tmFIRMCOUNTER = 5 # firmware based rising edge counter
LJ_tmFIRMCOUNTERDEBOUNCE = 6 # firmware counter with debounce
LJ_tmFREQOUT = 7 # frequency output
LJ_tmQUAD = 8 # Quadrature
LJ_tmTIMERSTOP = 9 # stops another timer after n pulses
LJ_tmSYSTIMERLOW = 10 # read lower 32-bits of system timer
LJ_tmSYSTIMERHIGH = 11 # read upper 32-bits of system timer
LJ_tmRISINGEDGES16 = 12 # 16-bit rising to rising edge measurement
LJ_tmFALLINGEDGES16 = 13 # 16-bit falling to falling edge measurement

# timer clocks:
LJ_tc750KHZ = 0      # UE9: 750 khz 
LJ_tcSYS = 1      # UE9: system clock

LJ_tc2MHZ = 10       # U3: Hardware Version 1.20 or lower
LJ_tc6MHZ = 11       # U3: Hardware Version 1.20 or lower
LJ_tc24MHZ = 12        # U3: Hardware Version 1.20 or lower
LJ_tc500KHZ_DIV = 13# U3: Hardware Version 1.20 or lower
LJ_tc2MHZ_DIV = 14    # U3: Hardware Version 1.20 or lower
LJ_tc6MHZ_DIV = 15    # U3: Hardware Version 1.20 or lower
LJ_tc24MHZ_DIV = 16 # U3: Hardware Version 1.20 or lower

# stream wait modes
LJ_swNONE = 1  # no wait, return whatever is available
LJ_swALL_OR_NONE = 2 # no wait, but if all points requested aren't available, return none.
LJ_swPUMP = 11    # wait and pump the message pump.  Prefered when called from primary thread (if you don't know
                           # if you are in the primary thread of your app then you probably are.  Do not use in worker
                           # secondary threads (i.e. ones without a message pump).
LJ_swSLEEP = 12 # wait by sleeping (don't do this in the primary thread of your app, or it will temporarily 
                           # hang)    This is usually used in worker secondary threads.


# BETA CONSTANTS
# Please note that specific usage of these constants and their values might change

# SWDT related 
LJ_chSWDT_RESET_COMM = 5200 # UE9 - Reset Comm on watchdog reset
LJ_chSWDT_RESET_CONTROL = 5201 # UE9 - Reset Control on watchdog trigger
LJ_chSWDT_UDPATE_DIO0 = 5202 # UE9 - Update DIO0 settings after reset
LJ_chSWDT_UPDATE_DIO1 = 5203 # UE9 - Update DIO1 settings after reset
LJ_chSWDT_DIO0 = 5204 # UE9 - DIO0 channel and state (value) to be set after reset
LJ_chSWDT_DIO1 = 5205 # UE9 - DIO1 channel and state (value) to be set after reset
LJ_chSWDT_UPDATE_DAC0 = 5206 # UE9 - Update DAC1 settings after reset
LJ_chSWDT_UPDATE_DAC1 = 5207 # UE9 - Update DAC1 settings after reset
LJ_chSWDT_DAC0 = 5208 # UE9 - voltage to set DAC0 at on watchdog reset
LJ_chSWDT_DAC1 = 5209 # UE9 - voltage to set DAC1 at on watchdog reset
LJ_chSWDT_DACS_ENABLE = 5210 # UE9 - Enable DACs on watchdog reset
LJ_chSWDT_ENABLE = 5211 # UE9 - used with LJ_ioSWDT_CONFIG to enable watchdog.    Value paramter is number of seconds to trigger
LJ_chSWDT_DISABLE = 5212 # UE9 - used with LJ_ioSWDT_CONFIG to enable watchdog.

LJ_ioSWDT_CONFIG = 504 # UE9 - Use LJ_chSWDT_ENABLE or LJ_chSWDT_DISABLE

LJ_tc4MHZ = 20       # U3: Hardware Version 1.21 or higher
LJ_tc12MHZ = 21        # U3: Hardware Version 1.21 or higher
LJ_tc48MHZ = 22        # U3: Hardware Version 1.21 or higher
LJ_tc1000KHZ_DIV = 23# U3: Hardware Version 1.21 or higher
LJ_tc4MHZ_DIV = 24    # U3: Hardware Version 1.21 or higher
LJ_tc12MHZ_DIV = 25     # U3: Hardware Version 1.21 or higher
LJ_tc48MHZ_DIV = 26 # U3: Hardware Version 1.21 or higher

# END BETA CONSTANTS


# error codes:    These will always be in the range of -1000 to 3999 for labView compatibility (+6000)
LJE_NOERROR = 0
 
LJE_INVALID_CHANNEL_NUMBER = 2 # occurs when a channel that doesn't exist is specified (i.e. DAC #2 on a UE9), or data from streaming is requested on a channel that isn't streaming
LJE_INVALID_RAW_INOUT_PARAMETER = 3
LJE_UNABLE_TO_START_STREAM = 4
LJE_UNABLE_TO_STOP_STREAM = 5
LJE_NOTHING_TO_STREAM = 6
LJE_UNABLE_TO_CONFIG_STREAM = 7
LJE_BUFFER_OVERRUN = 8 # occurs when stream buffer overruns (this is the driver buffer not the hardware buffer).  Stream is stopped.
LJE_STREAM_NOT_RUNNING = 9
LJE_INVALID_PARAMETER = 10
LJE_INVALID_STREAM_FREQUENCY = 11 
LJE_INVALID_AIN_RANGE = 12
LJE_STREAM_CHECKSUM_ERROR = 13 # occurs when a stream packet fails checksum.  Stream is stopped
LJE_STREAM_COMMAND_ERROR = 14 # occurs when a stream packet has invalid command values.     Stream is stopped.
LJE_STREAM_ORDER_ERROR = 15 # occurs when a stream packet is received out of order (typically one is missing).    Stream is stopped.
LJE_AD_PIN_CONFIGURATION_ERROR = 16 # occurs when an analog or digital request was made on a pin that isn't configured for that type of request
LJE_REQUEST_NOT_PROCESSED = 17 # When a LJE_AD_PIN_CONFIGURATION_ERROR occurs, all other IO requests after the request that caused the error won't be processed. Those requests will return this error.


# U3 Specific Errors
LJE_SCRATCH_ERROR = 19
"""U3 error"""
LJE_DATA_BUFFER_OVERFLOW = 20
"""U3 error"""
LJE_ADC0_BUFFER_OVERFLOW = 21 
"""U3 error"""
LJE_FUNCTION_INVALID = 22
"""U3 error"""
LJE_SWDT_TIME_INVALID = 23
"""U3 error"""
LJE_FLASH_ERROR = 24
"""U3 error"""
LJE_STREAM_IS_ACTIVE = 25
"""U3 error"""
LJE_STREAM_TABLE_INVALID = 26
"""U3 error"""
LJE_STREAM_CONFIG_INVALID = 27
"""U3 error"""
LJE_STREAM_BAD_TRIGGER_SOURCE = 28
"""U3 error"""
LJE_STREAM_INVALID_TRIGGER = 30
"""U3 error"""
LJE_STREAM_ADC0_BUFFER_OVERFLOW = 31
"""U3 error"""
LJE_STREAM_SAMPLE_NUM_INVALID = 33
"""U3 error"""
LJE_STREAM_BIPOLAR_GAIN_INVALID = 34
"""U3 error"""
LJE_STREAM_SCAN_RATE_INVALID = 35
"""U3 error"""
LJE_TIMER_INVALID_MODE = 36
"""U3 error"""
LJE_TIMER_QUADRATURE_AB_ERROR = 37
"""U3 error"""
LJE_TIMER_QUAD_PULSE_SEQUENCE = 38
"""U3 error"""
LJE_TIMER_BAD_CLOCK_SOURCE = 39
"""U3 error"""
LJE_TIMER_STREAM_ACTIVE = 40
"""U3 error"""
LJE_TIMER_PWMSTOP_MODULE_ERROR = 41
"""U3 error"""
LJE_TIMER_SEQUENCE_ERROR = 42
"""U3 error"""
LJE_TIMER_SHARING_ERROR = 43
"""U3 error"""
LJE_TIMER_LINE_SEQUENCE_ERROR = 44
"""U3 error"""
LJE_EXT_OSC_NOT_STABLE = 45
"""U3 error"""
LJE_INVALID_POWER_SETTING = 46
"""U3 error"""
LJE_PLL_NOT_LOCKED = 47
"""U3 error"""
LJE_INVALID_PIN = 48
"""U3 error"""
LJE_IOTYPE_SYNCH_ERROR = 49
"""U3 error"""
LJE_INVALID_OFFSET = 50
"""U3 error"""
LJE_FEEDBACK_IOTYPE_NOT_VALID = 51
"""U3 error

Has been described as mearly a flesh wound.
"""

LJE_SHT_CRC = 52
LJE_SHT_MEASREADY = 53
LJE_SHT_ACK = 54
LJE_SHT_SERIAL_RESET = 55
LJE_SHT_COMMUNICATION = 56

LJE_AIN_WHILE_STREAMING = 57

LJE_STREAM_TIMEOUT = 58
LJE_STREAM_CONTROL_BUFFER_OVERFLOW = 59
LJE_STREAM_SCAN_OVERLAP = 60
LJE_FIRMWARE_DOESNT_SUPPORT_IOTYPE = 61
LJE_FIRMWARE_DOESNT_SUPPORT_CHANNEL = 62
LJE_FIRMWARE_DOESNT_SUPPORT_VALUE = 63


LJE_MIN_GROUP_ERROR = 1000 # all errors above this number will stop all requests, below this number are request level errors.

LJE_UNKNOWN_ERROR = 1001 # occurs when an unknown error occurs that is caught, but still unknown.
LJE_INVALID_DEVICE_TYPE = 1002 # occurs when devicetype is not a valid device type
LJE_INVALID_HANDLE = 1003 # occurs when invalid handle used
LJE_DEVICE_NOT_OPEN = 1004    # occurs when Open() fails and AppendRead called despite.
LJE_NO_DATA_AVAILABLE = 1005 # this is cause when GetData() called without calling DoRead(), or when GetData() passed channel that wasn't read
LJE_NO_MORE_DATA_AVAILABLE = 1006
LJE_LABJACK_NOT_FOUND = 1007 # occurs when the labjack is not found at the given id or address.
LJE_COMM_FAILURE = 1008 # occurs when unable to send or receive the correct # of bytes
LJE_CHECKSUM_ERROR = 1009
LJE_DEVICE_ALREADY_OPEN = 1010 
LJE_COMM_TIMEOUT = 1011
LJE_USB_DRIVER_NOT_FOUND = 1012
LJE_INVALID_CONNECTION_TYPE = 1013
LJE_INVALID_MODE = 1014


# warning are negative
LJE_DEVICE_NOT_CALIBRATED = -1 # defaults used instead
LJE_UNABLE_TO_READ_CALDATA = -2 # defaults used instead


# depreciated constants:
LJ_ioANALOG_INPUT = 10  
"""Deprecated constant"""  
LJ_ioANALOG_OUTPUT = 20 # UE9 + U3
"""Deprecated constant"""  
LJ_ioDIGITAL_BIT_IN = 30 # UE9 + U3
"""Deprecated constant"""  
LJ_ioDIGITAL_PORT_IN = 35 # UE9 + U3 
"""Deprecated constant"""  
LJ_ioDIGITAL_BIT_OUT = 40 # UE9 + U3
"""Deprecated constant"""  
LJ_ioDIGITAL_PORT_OUT = 45 # UE9 + U3
"""Deprecated constant"""  
LJ_ioCOUNTER = 50 # UE9 + U3
"""Deprecated constant"""  
LJ_ioTIMER = 60 # UE9 + U3
"""Deprecated constant"""  
LJ_ioPUT_COUNTER_MODE = 2010 # UE9
"""Deprecated constant"""  
LJ_ioGET_COUNTER_MODE = 2011 # UE9
"""Deprecated constant"""  
LJ_ioGET_TIMER_VALUE = 2007 # UE9
"""Deprecated constant"""  
LJ_ioCYCLE_PORT = 102  # UE9 
"""Deprecated constant"""  
LJ_chTIMER_CLOCK_CONFIG = 1001 # UE9 + U3 
"""Deprecated constant"""  
LJ_ioPUT_CAL_CONSTANTS = 400
"""Deprecated constant"""  
LJ_ioGET_CAL_CONSTANTS = 401
"""Deprecated constant"""  
LJ_ioPUT_USER_MEM = 402
"""Deprecated constant"""  
LJ_ioGET_USER_MEM = 403
"""Deprecated constant"""  
LJ_ioPUT_USB_STRINGS = 404
"""Deprecated constant"""  
LJ_ioGET_USB_STRINGS = 405
"""Deprecated constant"""  
