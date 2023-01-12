import argparse
import asyncio
import imageio
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
r, g, b = image[:, :, 0], image[:, :, 1], image[:, :, 2]


sock = socket.socket(socket.AF_INET6, socket.SOCK_RAW, socket.IPPROTO_ICMPV6)
data = b"\x08" + b"\x00" * 7
base_ip = b"\x2a\x06\xa0\x03\xd0\x40"
def make_ip(x, y, r, g, b):
    return base_ip + struct.pack("BBBBxBxBxB", 
        0x10 | (x >> 8),
        x & 0xFF,
        y >> 8,
        y & 0xFF,
        r,
        g,
        b,
    )

class CanvasHolder:
    def __init__(self):
        self.canvas = None
        self.q = Queue()

    def update(self, img):
        self.q.put(img)
    
    def _merge(self, img):
        for y in range(512):
            row = img[y]
            if not row.any():
                continue
            for x in range(512):
                if row[x, 3] != 0:
                    self.canvas[y, x] = row[x]

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
    painted = 0
    for y in range(512):
        if y % 64 == 0:
            print("Y =", y)
        for x in range(512):
            if r[y, x] == canvas[y, x, 0] and g[y, x] == canvas[y, x, 1] and b[y, x] == canvas[y, x, 2]:
                continue
            painted += 1
            ip = socket.inet_ntop(socket.AF_INET6, make_ip(
                x,
                y,
                r[y, x],
                g[y, x],
                b[y, x]
            ))
            sock.sendto(data, (ip, 0, 0, 0))
            sock.sendto(data, (ip, 0, 0, 0))
    print("Painted", painted, "pixels")

while True:
    paint()
    time.sleep(1)
