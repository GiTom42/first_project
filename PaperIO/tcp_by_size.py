import struct
from encryption import aes_encrypt, aes_decrypt

SIZE_HEADER_FORMAT = ">I"
SIZE_HEADER_SIZE = 4


class TcpBySize:
    def __init__(self, sock, key=None):
        self.sock = sock
        self.key = key

    def send(self, data):
        if isinstance(data, str):
            data = data.encode()
        if self.key:
            data = aes_encrypt(data, self.key)
        header = struct.pack(SIZE_HEADER_FORMAT, len(data))
        self.sock.sendall(header + data)

    def recv(self):
        header = self._recv_exact(SIZE_HEADER_SIZE)
        if not header:
            return ""
        data_len = struct.unpack(SIZE_HEADER_FORMAT, header)[0]
        if data_len == 0:
            return ""
        data = self._recv_exact(data_len)
        if not data:
            return ""
        if self.key:
            data = aes_decrypt(data, self.key)
        return data.decode()

    def _recv_exact(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                return b""
            buf += chunk
        return buf
