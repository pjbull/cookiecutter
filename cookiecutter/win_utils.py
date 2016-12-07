# Functions for identifying and following symlinks in Windows
# from user `eryksun` http://stackoverflow.com/a/27979160
# 16 Jan 2015
# See http://stackoverflow.com/a/15259028 for more information

import os
from shutil import copystat, copy2, Error

from ctypes import c_ubyte, c_buffer, c_wchar_p, c_uint32
from ctypes.wintypes import (
    POINTER, DWORD, LPCWSTR, HANDLE,
    LPVOID, BOOL, USHORT, WCHAR, ULONG,
    WinDLL, Structure, addressof, WinError,
    Union, byref
)

kernel32 = WinDLL('kernel32')
LPDWORD = POINTER(DWORD)
UCHAR = c_ubyte

GetFileAttributesW = kernel32.GetFileAttributesW
GetFileAttributesW.restype = DWORD
GetFileAttributesW.argtypes = (LPCWSTR,)  # lpFileName In

INVALID_FILE_ATTRIBUTES = 0xFFFFFFFF
FILE_ATTRIBUTE_REPARSE_POINT = 0x00400

CreateFileW = kernel32.CreateFileW
CreateFileW.restype = HANDLE
CreateFileW.argtypes = (LPCWSTR,  # lpFileName In
                        DWORD,    # dwDesiredAccess In
                        DWORD,    # dwShareMode In
                        LPVOID,   # lpSecurityAttributes In_opt
                        DWORD,    # dwCreationDisposition In
                        DWORD,    # dwFlagsAndAttributes In
                        HANDLE)   # hTemplateFile In_opt

CloseHandle = kernel32.CloseHandle
CloseHandle.restype = BOOL
CloseHandle.argtypes = (HANDLE,)  # hObject In

INVALID_HANDLE_VALUE = HANDLE(-1).value
OPEN_EXISTING = 3
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000

DeviceIoControl = kernel32.DeviceIoControl
DeviceIoControl.restype = BOOL
DeviceIoControl.argtypes = (HANDLE,   # hDevice In
                            DWORD,    # dwIoControlCode In
                            LPVOID,   # lpInBuffer In_opt
                            DWORD,    # nInBufferSize In
                            LPVOID,   # lpOutBuffer Out_opt
                            DWORD,    # nOutBufferSize In
                            LPDWORD,  # lpBytesReturned Out_opt
                            LPVOID)   # lpOverlapped Inout_opt

FSCTL_GET_REPARSE_POINT = 0x000900A8
IO_REPARSE_TAG_MOUNT_POINT = 0xA0000003
IO_REPARSE_TAG_SYMLINK = 0xA000000C
MAXIMUM_REPARSE_DATA_BUFFER_SIZE = 0x4000


class GENERIC_REPARSE_BUFFER(Structure):
    _fields_ = (('DataBuffer', UCHAR * 1),)


class SYMBOLIC_LINK_REPARSE_BUFFER(Structure):
    _fields_ = (('SubstituteNameOffset', USHORT),
                ('SubstituteNameLength', USHORT),
                ('PrintNameOffset', USHORT),
                ('PrintNameLength', USHORT),
                ('Flags', ULONG),
                ('PathBuffer', WCHAR * 1))

    @property
    def PrintName(self):
        arrayt = WCHAR * (self.PrintNameLength // 2)
        offset = type(self).PathBuffer.offset + self.PrintNameOffset
        return arrayt.from_address(addressof(self) + offset).value


class MOUNT_POINT_REPARSE_BUFFER(Structure):
    _fields_ = (('SubstituteNameOffset', USHORT),
                ('SubstituteNameLength', USHORT),
                ('PrintNameOffset', USHORT),
                ('PrintNameLength', USHORT),
                ('PathBuffer', WCHAR * 1))

    @property
    def PrintName(self):
        arrayt = WCHAR * (self.PrintNameLength // 2)
        offset = type(self).PathBuffer.offset + self.PrintNameOffset
        return arrayt.from_address(addressof(self) + offset).value


class REPARSE_DATA_BUFFER(Structure):
    class REPARSE_BUFFER(Union):
        _fields_ = (('SymbolicLinkReparseBuffer',
                     SYMBOLIC_LINK_REPARSE_BUFFER),
                    ('MountPointReparseBuffer',
                     MOUNT_POINT_REPARSE_BUFFER),
                    ('GenericReparseBuffer',
                     GENERIC_REPARSE_BUFFER))
    _fields_ = (('ReparseTag', ULONG),
                ('ReparseDataLength', USHORT),
                ('Reserved', USHORT),
                ('ReparseBuffer', REPARSE_BUFFER))
    _anonymous_ = ('ReparseBuffer',)


def islink(path):
    result = GetFileAttributesW(path)
    if result == INVALID_FILE_ATTRIBUTES:
        raise WinError()
    return bool(result & FILE_ATTRIBUTE_REPARSE_POINT)


def readlink(path):
    reparse_point_handle = CreateFileW(path,
                                       0,
                                       0,
                                       None,
                                       OPEN_EXISTING,
                                       FILE_FLAG_OPEN_REPARSE_POINT |
                                       FILE_FLAG_BACKUP_SEMANTICS,
                                       None)
    if reparse_point_handle == INVALID_HANDLE_VALUE:
        raise WinError()
    target_buffer = c_buffer(MAXIMUM_REPARSE_DATA_BUFFER_SIZE)
    n_bytes_returned = DWORD()
    io_result = DeviceIoControl(reparse_point_handle,
                                FSCTL_GET_REPARSE_POINT,
                                None, 0,
                                target_buffer, len(target_buffer),
                                byref(n_bytes_returned),
                                None)
    CloseHandle(reparse_point_handle)
    if not io_result:
        raise WinError()
    rdb = REPARSE_DATA_BUFFER.from_buffer(target_buffer)
    if rdb.ReparseTag == IO_REPARSE_TAG_SYMLINK:
        return rdb.SymbolicLinkReparseBuffer.PrintName
    elif rdb.ReparseTag == IO_REPARSE_TAG_MOUNT_POINT:
        return rdb.MountPointReparseBuffer.PrintName
    raise ValueError("not a link")


# symlink function from Stackoverflow user Gian Marco Gherardi, 23 Feb 2013
# http://stackoverflow.com/a/15043806
def symlink(source, link_name):
    csl = kernel32.CreateSymbolicLinkW
    csl.argtypes = (c_wchar_p, c_wchar_p, c_uint32)
    csl.restype = c_ubyte

    flags = 1 if os.path.isdir(source) else 0

    if csl(link_name, source, flags) == 0:
        raise WinError()


# reimplement copytree, but using the windows-specfic symlink functions
def copytree(src, dst, symlinks=False):
    names = os.listdir(src)
    os.makedirs(dst)
    errors = []
    for name in names:
        srcname = os.path.join(src, name)
        dstname = os.path.join(dst, name)
        try:
            if symlinks and islink(srcname):
                linkto = readlink(srcname)
                symlink(linkto, dstname)
            elif os.path.isdir(srcname):
                copytree(srcname, dstname, symlinks)
            else:
                copy2(srcname, dstname)
        except OSError as why:
            errors.append((srcname, dstname, str(why)))
        # catch the Error from the recursive copytree so that we can
        # continue with other files
        except Error as err:
            errors.extend(err.args[0])
    try:
        copystat(src, dst)
    except OSError as why:
        # can't copy file access times on Windows
        if why.winerror is None:
            errors.extend((src, dst, str(why)))
    if errors:
        raise Error(errors)
