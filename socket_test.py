import time
import random

ss = 'test from the server'
sc = 'test from ze client'

OLPC_OFFSET = 5.5

def server(soc, send_signal):
    send_signal('preparing')
    time.sleep(1)
    send_signal('waiting')
    soc.sendall(ss)
    send_signal('playing')
    time.sleep(1)
    x = soc.recv(len(sc))
    send_signal('processing')
    time.sleep(1)
    send_signal('done')
    return random.random()

def client(soc, send_signal):
    send_signal('preparing')
    time.sleep(1)
    send_signal('waiting')
    x = soc.recv(len(ss))
    send_signal('playing')
    time.sleep(1)
    soc.sendall(sc)
    send_signal('processing')
    time.sleep(1)
    send_signal('done')
    return random.random()

def speed_of_sound():
    return 345.6789

def measure_dt_seq(soc, is_server, send_signal):
    if is_server:
        return server(soc, send_signal)
    else:
        return client(soc, send_signal)
