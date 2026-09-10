"""Windows handle-relative evidence creation; never follow a reparse point.

NtCreateFile RootDirectory and FILE_OPEN_REPARSE_POINT:
https://learn.microsoft.com/windows/win32/api/winternl/nf-winternl-ntcreatefile
"""

import ctypes as c
from ctypes import wintypes as w
import msvcrt
import os
from pathlib import PureWindowsPath
import stat


class UnicodeString(c.Structure):
    _fields_ = [('length', w.USHORT), ('maximum_length', w.USHORT), ('buffer', w.LPWSTR)]


class ObjectAttributes(c.Structure):
    _fields_ = [('length', w.ULONG), ('root', w.HANDLE),
                ('name', c.POINTER(UnicodeString)), ('attributes', w.ULONG),
                ('security', w.LPVOID), ('quality_of_service', w.LPVOID)]


class IoStatus(c.Structure):
    _fields_ = [('status', c.c_void_p), ('information', c.c_size_t)]


class AttributeTag(c.Structure):
    _fields_ = [('attributes', w.DWORD), ('tag', w.DWORD)]


class FileIdentity(c.Structure):
    _fields_ = [('volume', c.c_ulonglong), ('file_id', c.c_ubyte * 16)]


kernel = c.WinDLL('kernel32', use_last_error=True)
advapi = c.WinDLL('advapi32', use_last_error=True)
ntdll = c.WinDLL('ntdll')
kernel.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, w.LPVOID, w.DWORD, w.DWORD, w.HANDLE]
kernel.CreateFileW.restype = w.HANDLE
kernel.CloseHandle.argtypes = [w.HANDLE]
kernel.CloseHandle.restype = w.BOOL
kernel.GetCurrentProcess.restype = w.HANDLE
kernel.GetFileInformationByHandleEx.argtypes = [w.HANDLE, c.c_int, w.LPVOID, w.DWORD]
kernel.GetFileInformationByHandleEx.restype = w.BOOL
kernel.LocalFree.argtypes = [w.LPVOID]
kernel.LocalFree.restype = w.LPVOID
advapi.OpenProcessToken.argtypes = [w.HANDLE, w.DWORD, c.POINTER(w.HANDLE)]
advapi.OpenProcessToken.restype = w.BOOL
advapi.GetTokenInformation.argtypes = [w.HANDLE, c.c_int, w.LPVOID, w.DWORD, c.POINTER(w.DWORD)]
advapi.GetTokenInformation.restype = w.BOOL
advapi.ConvertSidToStringSidW.argtypes = [w.LPVOID, c.POINTER(w.LPWSTR)]
advapi.ConvertSidToStringSidW.restype = w.BOOL
advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [w.LPCWSTR, w.DWORD, c.POINTER(w.LPVOID), c.POINTER(w.DWORD)]
advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = w.BOOL
ntdll.NtCreateFile.argtypes = [c.POINTER(w.HANDLE), w.DWORD, c.POINTER(ObjectAttributes),
                             c.POINTER(IoStatus), w.LPVOID, w.ULONG, w.ULONG,
                             w.ULONG, w.ULONG, w.LPVOID, w.ULONG]
ntdll.NtCreateFile.restype = w.LONG
ntdll.RtlNtStatusToDosError.argtypes = [w.LONG]
ntdll.RtlNtStatusToDosError.restype = w.ULONG


def checked(value):
    if not value:
        raise c.WinError(c.get_last_error())
    return value


def private_descriptor():
    token = w.HANDLE()
    checked(advapi.OpenProcessToken(kernel.GetCurrentProcess(), 0x0008, c.byref(token)))
    sid_text = w.LPWSTR()
    try:
        needed = w.DWORD()
        advapi.GetTokenInformation(token, 1, None, 0, c.byref(needed))
        if not needed.value:
            raise c.WinError(c.get_last_error())
        user = c.create_string_buffer(needed.value)
        checked(advapi.GetTokenInformation(token, 1, user, needed, c.byref(needed)))
        sid = c.cast(user, c.POINTER(w.LPVOID))[0]
        checked(advapi.ConvertSidToStringSidW(sid, c.byref(sid_text)))
        owner = sid_text.value
        descriptor = w.LPVOID()
        # Establish the protected DACL at creation, without a permissive interval.
        sddl = f'O:{owner}D:P(A;;FA;;;{owner})(A;;FA;;;SY)(A;;FA;;;BA)'
        checked(advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            sddl, 1, c.byref(descriptor), None))
        return descriptor
    finally:
        if sid_text:
            kernel.LocalFree(c.cast(sid_text, w.LPVOID))
        kernel.CloseHandle(token)


def reject_reparse(handle, *, directory):
    info = AttributeTag()
    checked(kernel.GetFileInformationByHandleEx(handle, 9, c.byref(info), c.sizeof(info)))
    if info.attributes & 0x400 or bool(info.attributes & 0x10) != directory:
        raise OSError('reparse point or unexpected file type in evidence walk')


def identity(handle):
    info = FileIdentity()
    checked(kernel.GetFileInformationByHandleEx(handle, 18, c.byref(info), c.sizeof(info)))
    return info.volume, bytes(info.file_id)


def open_relative(parent, component, *, directory=False, create=False, security=None):
    if (not component or component in {'.', '..'} or component.endswith(('.', ' '))
            or any(char in '<>:"/\\|?*' or ord(char) < 32 for char in component)
            or PureWindowsPath(component).is_reserved()):
        raise OSError('ambiguous Windows evidence component')
    buffer = c.create_unicode_buffer(component)
    length = len(component.encode('utf-16-le'))
    if length > 65532:
        raise OSError('Windows evidence component too long')
    name = UnicodeString(length, length + 2, c.cast(buffer, w.LPWSTR))
    attributes = ObjectAttributes(c.sizeof(ObjectAttributes), parent, c.pointer(name),
                                  0x40, security, None)
    handle = w.HANDLE()
    io_status = IoStatus()
    access = 0x00100080 | (0x1 if directory else (0x40000000 if create else 0))
    options = 0x00200000 | 0x20 | (0x1 if directory else 0x40)
    status = ntdll.NtCreateFile(c.byref(handle), access, c.byref(attributes),
                              c.byref(io_status), None, 0x80, 7,
                              2 if create else 1, options, None, 0)
    if status < 0:
        raise c.WinError(ntdll.RtlNtStatusToDosError(status))
    try:
        reject_reparse(handle, directory=directory)
        return handle.value
    except BaseException:
        kernel.CloseHandle(handle)
        raise


def open_private_output(path):
    root = kernel.CreateFileW(str(path.parent.resolve(strict=True)), 0x00100081,
                              7, None, 3, 0x02200000, None)
    if root == w.HANDLE(-1).value:
        raise c.WinError(c.get_last_error())
    descriptor = None
    try:
        reject_reparse(root, directory=True)
        descriptor = private_descriptor()
        handle = open_relative(root, path.name, create=True, security=descriptor)
        try:
            return msvcrt.open_osfhandle(handle, os.O_WRONLY | os.O_BINARY)
        except BaseException:
            kernel.CloseHandle(handle)
            raise
    finally:
        if descriptor:
            kernel.LocalFree(descriptor)
        kernel.CloseHandle(root)


def run_bound_windows_evidence(root, output, expensive_runner):
    directories = []
    descriptor = None
    output_fd = -1
    terminal_fd = -1
    try:
        root_handle = kernel.CreateFileW(str(root), 0x00100081, 7, None, 3, 0x02200000, None)
        if root_handle == w.HANDLE(-1).value:
            raise c.WinError(c.get_last_error())
        directories.append(root_handle)
        reject_reparse(root_handle, directory=True)
        for component in output.parts[:-1]:
            directories.append(open_relative(directories[-1], component, directory=True))
        descriptor = private_descriptor()
        handle = open_relative(directories[-1], output.parts[-1], create=True, security=descriptor)
        try:
            output_fd = msvcrt.open_osfhandle(handle, os.O_WRONLY | os.O_BINARY)
        except BaseException:
            kernel.CloseHandle(handle)
            raise
        initial = os.fstat(output_fd)
        if not stat.S_ISREG(initial.st_mode):
            raise OSError('evidence output terminal is not a regular file')
        expensive_runner(output_fd)
        os.fsync(output_fd)
        opened = os.fstat(output_fd)
        # Reprove the named directory chain too: a still-open directory handle
        # must not hide its replacement by a junction or another directory.
        reopened_root = kernel.CreateFileW(str(root), 0x00100081, 7, None, 3, 0x02200000, None)
        if reopened_root == w.HANDLE(-1).value:
            raise c.WinError(c.get_last_error())
        try:
            reject_reparse(reopened_root, directory=True)
            if identity(reopened_root) != identity(directories[0]):
                raise OSError('evidence root identity changed')
        finally:
            kernel.CloseHandle(reopened_root)
        for index, component in enumerate(output.parts[:-1]):
            named_directory = open_relative(directories[index], component, directory=True)
            try:
                if identity(named_directory) != identity(directories[index + 1]):
                    raise OSError('evidence directory identity changed')
            finally:
                kernel.CloseHandle(named_directory)
        named_handle = open_relative(directories[-1], output.parts[-1])
        try:
            terminal_fd = msvcrt.open_osfhandle(named_handle, os.O_RDONLY | os.O_BINARY)
        except BaseException:
            kernel.CloseHandle(named_handle)
            raise
        named = os.fstat(terminal_fd)
        if (not stat.S_ISREG(named.st_mode)
                or (opened.st_dev, opened.st_ino) != (initial.st_dev, initial.st_ino)
                or (named.st_dev, named.st_ino) != (initial.st_dev, initial.st_ino)):
            raise OSError('evidence output terminal identity changed')
    finally:
        if terminal_fd >= 0:
            os.close(terminal_fd)
        if output_fd >= 0:
            os.close(output_fd)
        if descriptor:
            kernel.LocalFree(descriptor)
        for handle in reversed(directories):
            kernel.CloseHandle(handle)
