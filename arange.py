# Copyright 2007 Benjamin M. Schwartz
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

try:
    import numpy as num
    fft = num.fft.fft
    ifft = num.fft.ifft
except ImportError:
    import Numeric as num
    import FFT
    fft = FFT.fft
    ifft = FFT.inverse_fft

import wave
import pygst
pygst.require('0.10')
import gst
import struct
import tempfile
#import pylab
import time
import socket
import types
import math

REC_HZ = 48000
MLS_INDEX = 14

OLPC_OFFSET = 0.096 #Measured constant offset due to speaker placement
    
def compute_mls(R):
    """
    Computes a Maximum-Length-Sequence using a naive LFSR approach
    for n=3...32. R is the register initializer (cannot be all-zero) which 
    determines the phase of the MLS.  
    """

    # 1-indexed collection of MLS taps from http://homepage.mac.com/afj/taplist.html
    taps = ( (), (), (), #ignore n=0,1,2
             (3, 2),
             (4, 3),
             (5, 3),
             (6, 5),
             (7, 6),
             (8, 7, 6, 1),
             (9, 5),
             (10, 7),
             (11, 9),
             (12, 11, 10, 4),
             (13, 12, 11, 8),
             (14, 13, 12, 2),
             (15, 14),
             (16, 15, 13, 4),
             (17, 14),
             (18, 11),
             (19, 18, 17, 14),
             (20, 17),
             (21, 19),
             (22, 21),
             (23, 18),
             (24, 23, 22, 17),
             (25, 22),
             (26, 25, 24, 20),
             (27, 26, 25, 22),
             (28, 25),
             (29, 27),
             (30, 29, 28, 7),
             (31, 28),
             (32, 31, 30, 10))

    n = len(R)
    return LFSR(R, [i - 1 for i in taps[n]], 2**n-1)

def LFSR(R, taps, m):
    """
    Computes the output of the LFSR specified by "taps" on initial registers
    R for m steps.
    R = an indexable object
    taps = zero-indexed collection of taps
    
    returns a num.array of length m
    """
    o = num.resize(num.array([], num.bool), (m)) #numpy-only
    #o = num.resize(num.array([], num.UInt8), (m))
    if len(taps) == 2:
        a = taps[0]
        b = taps[1]   
        for i in xrange(m):
             next = R[a] ^ R[b] 
             o[i] = R[-1]
             R[1:] = R[:-1]
             R[0] = next
    elif len(taps) == 4:
        a = taps[0]
        b = taps[1]
        c = taps[2]
        d = taps[3]
        for i in xrange(m):
             next = R[a] ^ R[b] ^ R[c] ^ R[d]
             o[i] = R[-1]
             R[1:] = R[:-1]
             R[0] = next
    else:
        for i in xrange(m):
            next = False
            for i in taps:
                next = next ^ R[i]
            o[i] = R[-1]
            R[1:] = R[:-1]
            R[0] = next
    return o

def write_wav(o):
    """
    Writes a [0,1]-scaled array o into the left channel of a 8-bit stereo
    wav-file at 48KHz
    """
    f = tempfile.NamedTemporaryFile(mode='wb')
    w = wave.open(f)
    w.setparams((2,1,REC_HZ,0, 'NONE', 'NONE'))
    n = num.size(o)
    #q = num.zeros((2*n), num.UInt8) #Numeric or old numpy
    q = num.zeros((2*n), num.uint8) #new numpy
    q[::2] = o*255 #numpy-only
    #q[::2] = (o*255).tolist()
    q[1::2] = 128
    w.writeframes(q.tostring())
    return f

def play_wav(fname):
    """
    This void function plays the file named fname and does not return until
    after playback has completed.
    """
    print "about to get player"
    player = gst.element_factory_make("playbin", 'player')
    print "about to get bus"
    bus = player.get_bus()
    
    print "about to start playing"
    player.set_property('uri','file://'+fname)
    player.set_state(gst.STATE_PLAYING)

    print "about to wait for EOS"
    bus.poll(gst.MESSAGE_EOS,-1)
    print "cleaning up"
    player.set_state(gst.STATE_NULL)

def record_while_playing(play_name, t):
    """
    This function starts recording, plays the file named 'play_name',
    waits a time t (s) after playback has finished, then stops recording.
    It returns a filehandle to a WAV file containing the recording.
    """
    (pipeline, f) = start_recording()
    if play_name:
        play_wav(play_name)
    time.sleep(t)
    stop_recording(pipeline)
    return f

def start_recording():
    """
    Initiates recording of a mono 48 KHz wav file via gstreamer from the default
    capture device.
    returns (pipeline, f)
    pipeline is the gstreamer pipeline corresponding to the recording process
    f is a file object for the wav file
    """
    f = tempfile.NamedTemporaryFile('rb')
    fname = tempfile.mktemp()

    pipeline = gst.element_factory_make('pipeline', 'recorder')
    microphone = gst.element_factory_make('alsasrc', 'microphone')
    converter = gst.element_factory_make('audioconvert', 'converter')
    wave_encoder = gst.element_factory_make('wavenc', 'wave_encoder')
    file_writer = gst.element_factory_make('filesink', 'file writer')
    file_writer.set_property('location', f.name)
    
    pipeline.add(microphone)
    pipeline.add(converter)
    pipeline.add(wave_encoder)
    pipeline.add(file_writer)

    microphone.link(converter, gst.caps_from_string('audio/x-raw-int, endianness=1234, signed=(boolean)true, width=16, depth=16, rate=' + str(REC_HZ) +', channels=1'))
    converter.link(wave_encoder)
    wave_encoder.link(file_writer)
    
    pipeline.set_state(gst.STATE_PLAYING)
    return (pipeline, f)

def stop_recording(pipeline):
    """
    This function safely shuts down a recording pipeline.
    """
    mic = pipeline.iterate_sources().next()
    bus = pipeline.get_bus()
    
    mic.set_state(gst.STATE_NULL)
    mic.set_locked_state(True)
    
    bus.poll(gst.MESSAGE_EOS,-1)
    pipeline.set_state(gst.STATE_NULL)
    mic.set_locked_state(False)

def read_wav(f):
    """
    Reads one channel of a .wav file object (f) into a float array, unscaled
    """
    w = wave.open(f)
    n = w.getnframes()
    nc = w.getnchannels()
    b = w.getsampwidth()
    if b==2:
        typecode = 'h'
    elif b==1:
        typecode = 'b'
    s = w.readframes(n)
    n = len(s)/(nc*b)
    a = struct.unpack(str(n*nc)+typecode, s)
    return num.array(a[::nc], num.float)

def cross_cov(a, b):
    """computes the cross-covariance of signals in a and b"""
    #assert a.ndim == b.ndim == 1 #numpy-only
    assert len(num.shape(a)) == len(num.shape(b)) == 1
    #n = max(a.size, b.size) #numpy-only
    n = max(num.size(a), num.size(b))
    n2 = 2**int(math.ceil(math.log(n,2))) #power of 2 >=n
    fa = fft(a,n2)
    fb = fft(b,n2)
    fprod = num.conjugate(fa)*fb
    xc = ifft(fprod)
    return xc[:n].real

def get_room_echo(t):
    """A test function that can be used to determine the impulse response
    of a microphone-speaker system, up to a time-delay"""
    R = (num.zeros((MLS_INDEX)) == 0)
    mls = compute_mls(R)
    mls_wav_file = write_wav(mls)
    record_wav_file = record_while_playing(mls_wav_file.name, t)
    mls_wav_file.close()
    rec_array = read_wav(record_wav_file)
    record_wav_file.close()
    return cross_cov(mls - 0.5, rec_array)

def get_noise_echo(t):
    """The same as get_echo, but with no signal."""
    R = (num.zeros((MLS_INDEX)) == 0)
    mls = compute_mls(R)

    record_wav_file = record_while_playing(False, t)

    rec_array = read_wav(record_wav_file)
    record_wav_file.close()
    return cross_cov(mls - 0.5, rec_array)


def do_server_simul(server_address, port):
    """
    Make this computer the server for a distance measurement using
    measure_dt_simul.
    """
    listener_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener_socket.setsockopt(socket.SO_REUSEADDR)
    listener_socket.bind((server_address, port))
    listener_socket.listen(1)
    (server_socket, client_address) = listener_socket.accept()
    listener_socket.close()
    dt = measure_dt_simul(server_socket, True)
    server_socket.close()
    return dt

def do_client_simul(server_address, port):
    """
    Make this computer the client for a distance measurement 
    using measure_dt_simul
    """
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect((server_address, port))
    dt = measure_dt_simul(client_socket, False)
    client_socket.close()
    return dt
    
def do_server_seq(server_address, port):
    """
    Make this computer the server for a distance measurement
    using measure_dt_seq.
    """
    listener_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener_socket.bind((server_address, port))
    listener_socket.listen(1)
    (server_socket, client_address) = listener_socket.accept()
    listener_socket.close()
    dt = measure_dt_seq(server_socket, True)
    server_socket.close()
    return dt

def do_client_seq(server_address, port):
    """
    Make this computer the client for a distance measurement
    using measure_dt_seq.
    """
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect((server_address, port))
    dt = measure_dt_seq(client_socket, False)
    client_socket.close()
    return dt

def recvall(s, n):
    """
    Attempt to receive n bytes from socket s.  Return received message.
    Fails with "Assertion failed" if a message of incorrect length is received.
    """
    #assert type(s) == socket._socketobject
    received = ''
    while len(received) < n:
        q = s.recv(n - len(received))
        assert len(q) > 0
        received = received + q
    return received

def recvmsg(s, message):
    """
    Attempt to receive a specific message from a socket.  Returns
    a boolean indicating whether or not that message was received.
    """
    #assert type(s) == socket._socketobject
    return (message == recvall(s, len(message)))

def measure_dt_simul(s, am_server):
    """
    Performs all the actual communication between client and server for
    distance measurement using simultaneous playback on both computers.
    The method relies on the very low cross-covariance of certain pairs of
    m-sequences (MLS), including the pair generated by time-reversal. In
    practice, due to nonlinearities in the speakers and microphones, it
    is not usable.
    """
    #assert type(s) == socket._socketobject
    R = (num.zeros((MLS_INDEX)) == 0)
    mls = compute_mls(R)
    if am_server:
        mls = mls[::-1]
    mls_wav_file = write_wav(mls)

    ready_command = 'ready'
    if am_server:
        assert recvmsg(s, ready_command)
    else:
        s.sendall(ready_command)

    start_and_play_command = 'start'
    if am_server:
        (pipeline, rec_wav_file) = start_recording()
        s.sendall(start_and_play_command)
    else:
        assert recvmsg(s, start_and_play_command)
        (pipeline, rec_wav_file) = start_recording()

    playing_command = 'playing'
    rectime = 5 #seconds
    if am_server:
        assert recvmsg(s, playing_command)
        play_wav(mls_wav_file.name)
        time.sleep(rectime)
    else:
        play_wav(mls_wav_file.name)
        s.sendall(playing_command)
    
    stop_command = 'stop'
    if am_server:
        s.sendall(stop_command)
    else:
        assert recvmsg(s, stop_command)

    stop_recording(pipeline)
    mls_wav_file.close()
    rec_array = read_wav(rec_wav_file)
    rec_wav_file.close()
    mls_float = mls - 0.5
    xc_self = cross_cov(mls_float, rec_array)
    xc_other = cross_cov(mls_float[::-1], rec_array)
    dn = getpeak(xc_other) - getpeak(xc_self)
    dt = float(dn)/REC_HZ
    format_string = '!d'
    n = struct.calcsize(format_string)
    s.sendall(struct.pack(format_string, dt))
    other_dt = struct.unpack(format_string, recvall(s, n))[0]

    roundtrip = dt + other_dt

    return roundtrip/2

def measure_dt_seq(s, am_server, send_signal=False):
    """
    This function performs distance measurement using sequential playback.
    In this method, the server plays its sound first, and the client plays
    only after the server has finished.  The first and second halves of the
    recording are analyzed separately.  This method is much more tolerant
    of low-quality speaker systems and is known to work.
    """
    #assert type(s) == socket._socketobject

    if send_signal:
        send_signal('preparing')

    R = (num.zeros((MLS_INDEX)) == 0)
    mls = compute_mls(R)
    mls_rev = mls[::-1]
    
    if am_server:
    	mls_wav_file = write_wav(mls)
    else:
    	mls_wav_file = write_wav(mls_rev)

    if send_signal:
        send_signal('waiting')
    ready_command = 'ready'
    if am_server:
        assert recvmsg(s, ready_command)
    else:
        s.sendall(ready_command)

    start_and_play_command = 'start recording'
    if am_server:
        s.sendall(start_and_play_command)
    else:
        assert recvmsg(s, start_and_play_command)

    if send_signal:
        send_signal('playing')

    t1=time.time()
    (pipeline, rec_wav_file) = start_recording()
    t2=time.time()

    start_confirmation_command = 'started'
    if am_server:
        assert recvmsg(s, start_confirmation_command)
    else:
        s.sendall(start_confirmation_command)
	
    handoff_command = 'your turn'
    playtime = float(2**MLS_INDEX)/REC_HZ #seconds
    ringdown = 0.5 #seconds
    if am_server:
        print "about to play_wav"
        play_wav(mls_wav_file.name)
        print "played wav"
        time.sleep(ringdown)
        t3 = time.time()
        time.sleep(t2-t1)
        s.sendall(handoff_command)
    else:
        assert recvmsg(s, handoff_command)
        t3 = time.time()
        time.sleep(t2-t1)
        play_wav(mls_wav_file.name)
        time.sleep(ringdown)
    
    stop_command = 'stop'
    if am_server:
        assert recvmsg(s, stop_command)
    else:
        s.sendall(stop_command)

    stop_recording(pipeline)
    mls_wav_file.close()
    rec_array = read_wav(rec_wav_file)
    rec_wav_file.close()

    if send_signal:
        send_signal('processing')
    
    breaktime = t3-t1
    print breaktime
    breaknum = int(math.ceil(breaktime*REC_HZ))
    rec1 = rec_array[:breaknum]
    rec2 = rec_array[breaknum:]
    print num.size(rec1)
    print num.size(rec2)
    
    mls_float = mls - 0.5
    mls_rev_float = mls_rev - 0.5
    xc_server = cross_cov(mls_float, rec1)
    xc_client = cross_cov(mls_rev_float, rec2)
    s_peak = getpeak(xc_server)
    c_peak = getpeak(xc_client)
    print xc_server[s_peak]
    print xc_client[c_peak]
    dn = (c_peak + breaknum) - s_peak
    dt = float(dn)/REC_HZ
    format_string = '!d'
    n = struct.calcsize(format_string)
    s.sendall(struct.pack(format_string, dt))
    other_dt = struct.unpack(format_string, recvall(s, n))[0]

    roundtrip = abs(dt - other_dt)

    #pylab.plot(xc_server)
    #pylab.show()

    if send_signal:
        send_signal('done')

    return roundtrip/2
    
def getpeak(a):
    return num.argmax(abs(a))
    
def speed_of_sound(t=25.0, h=0.6, p=101325.0, x_c=0.0004): 
    """
    t= temperature in Celsius
    h = relative humidity as a fraction
    p = pressure in Pa
    x_c = mole fraction of CO2
    returns an estimate of the speed of sound in (m/s)
    from Cramer, O. "The variation of the specific heat ratio and the speed of sound in air with temperature, pressure, humidity, and CO2 concentration". Journal of the Acoustical Society of America, 1993, Vol. 93, Issue 5, p. 2510, eq. 15 and A1-A3."""

    a0 = 331.5024
    a1 = 0.603055
    a2 = -0.000528
    a3 = 51.471935
    a4 = 0.1495874
    a5 = -0.000782
    a6 = -1.82e-7
    a7 = 3.73e-8
    a8 = -2.93e-10
    a9 = -85.20931
    a10 = -0.228525
    a11 = 5.91e-5
    a12 = -2.835149
    a13 = -2.15e-13
    a14 = 29.179762
    a15 = 0.000486

    t2 = t**2
    T = t + 273.15

    f = 1.00062 + 3.14e-8*p + 5.6e-7*t2
    psv = math.exp(1.2811805e-5*(T**2) - 1.9509874e-2*T \
                       + 34.04926034 - 6.3536311e3/T) #Pa
    x_w = h*f*psv/p

    return a0 + a1*t + a2*t2 + (a3 + a4*t +a5*t2)*x_w \
+ (a6 + a7*t + a8*t2)*p + (a9 + a10*t + a11*t2)*x_c \
+ a12*(x_w**2) + a13*(p**2) + a14*(x_c**2) + a15*x_w*p*x_c


def interactive_mode():
     n = input('Type 1 to be the server, 2 to be the client:')
     assert (n == 1) or (n == 2)
     if n==1:
         server_address = raw_input('Enter the address on which to listen:')
         port = input('Enter the port on which to listen:')
         dt = do_server_seq(server_address, port)
     elif n==2:
         server_address = raw_input('Enter the IP address or hostname of the server:')
         port = input('Enter the port on which the server is listening:')
         dt = do_client_seq(server_address, port)
     print "The time delay in seconds is ", dt
     print "The speed of sound in m/s is ", speed_of_sound()
     print "The distance in meters is therefore ", dt*speed_of_sound()-OLPC_OFFSET

#pylab.plot(get_room_echo(1))
#pylab.show()
#e=get_room_echo(4)
#n=get_noise_echo(4)
#print e[getpeak(e)]
#print n[getpeak(n)]
#interactive_mode()
