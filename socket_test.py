ss = 'test from server'
sc = 'test from client'

OLPC_OFFSET = 5.5

def server(soc):
    soc.sendall(ss)
    x = soc.recv(len(sc))
    return float(hash(x))

def client(soc):
    x = soc.recv(len(ss))
    soc.sendall(sc)
    return float(hash(x))

def speed_of_sound():
    return 345.67

def measure_dt_seq(soc, is_server):
    if is_server:
        return server(soc)
    else:
        return client(soc)
