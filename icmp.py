import argparse
import asyncio
import imageio
import numpy as np
from queue import Queue
import socket
import struct
import threading
import time
import websockets

parser = argparse.ArgumentParser()
parser.add_argument("image", help="Image file to draw, must be 512x512")
args = parser.parse_args()
image = imageio.imread(args.image, pilmode="RGBA")
w, h, _ = image.shape
if w != 512 or h != 512:
    raise Exception("Image is not 512x512")
img_r, img_g, img_b = image[:, :, 0], image[:, :, 1], image[:, :, 2]

sock = socket.socket(socket.AF_INET6, socket.SOCK_RAW, socket.IPPROTO_ICMPV6)
data = b"\x08" + b"\x00" * 7

_ip_buf = bytearray(socket.inet_pton(socket.AF_INET6, "2a06:a003:d040::"))
def make_ip(x, y, r, g, b, size=1):
    _ip_buf[6] = (size << 4) | (x >> 8)
    _ip_buf[7] = x & 0xFF
    _ip_buf[8] = y >> 8
    _ip_buf[9] = y & 0xFF
    _ip_buf[11] = r
    _ip_buf[13] = g
    _ip_buf[15] = b
    return _ip_buf

class CanvasHolder:
    def __init__(self):
        self.canvas = None
        self.q = Queue()

    def update(self, img):
        self.q.put(img)
    
    def _merge(self, img):
        nz = np.nonzero(img[:, :, 3])
        self.canvas[nz] = img[nz]

    def get_canvas(self):
        if self.q.empty() and self.canvas is not None:
            return self.canvas
        if self.canvas is None:
            self.canvas = imageio.imread(self.q.get(), pilmode='RGBA')
        while not self.q.empty():
            self._merge(imageio.imread(self.q.get(), pilmode='RGBA'))
        return self.canvas

ch = CanvasHolder()


async def process_ws():
    async with websockets.connect("wss://v6.sys42.net/ws") as websocket:
        while True:
            msg = await websocket.recv()
            if isinstance(msg, bytes):
                ch.update(msg)
            else:
                print("Got websocket message:", msg)

def asyncio_thread(loop):
    asyncio.set_event_loop(loop)
    loop.run_until_complete(process_ws())
threading.Thread(target=asyncio_thread, args=(asyncio.get_event_loop(),)).start()

def paint():
    canvas = ch.get_canvas()
    canvas_r, canvas_g, canvas_b = canvas[:, :, 0], canvas[:, :, 1], canvas[:, :, 2]
    painted = 0
    for y in range(512):
        if y % 64 == 0:
            print("Y =", y)
        row_r, row_g, row_b = img_r[y], img_g[y], img_b[y]
        c_row_r, c_row_g, c_row_b = canvas_r[y], canvas_g[y], canvas_b[y]
        for x in range(512):
            r, g, b = row_r[x], row_g[x], row_b[x]
            if r == c_row_r[x] and g == c_row_g[x] and b == c_row_b[x]:
                continue
            painted += 1
            ip = socket.inet_ntop(socket.AF_INET6, make_ip(
                x,
                y,
                r,
                g,
                b,
            ))
            sock.sendto(data, (ip, 0, 0, 0))
            sock.sendto(data, (ip, 0, 0, 0))
    print("Painted", painted, "pixels")

while True:
    paint()
