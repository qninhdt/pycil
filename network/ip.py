from socket import *

PORTS = range(2404, 2424) # :>>

def get_host_name():
    return gethostbyname(gethostname())

def check_port(ip, port):
    sock = socket(AF_INET, SOCK_STREAM)
    result = sock.connect_ex((ip, port))
    sock.close()

    return result == 0

def get_port():
    ip = get_host_name()

    for port in PORTS:
        if not check_port(ip, port):
            return port