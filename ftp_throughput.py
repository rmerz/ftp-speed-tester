#!/usr/bin/env python

import argparse, sys, os
import ftplib as fl
import netrc
import datetime as dt
import time
import serial
from multiprocessing import Process, Value, Queue

class Ftp:
    def __init__(self,size,intervalDuration,timeout,host,netrcFile,data,upload):
        self.size = size
        self.host = host
        self.port = 21
        self.timeout = timeout
        try:
            cred = netrc.netrc(netrcFile)
            (self.user, account, self.password) = cred.authenticators(self.host)
        except FileNotFoundError as e:
            sys.stderr.write('netrc file not found\n')
            sys.exit(-1)
        except netrc.NetrcParseError as e:
            sys.stderr.write('netrc badly formatted\n')
            sys.exit(-1)
        self.data = data
        self.upload = upload
        if self.upload and not os.path.exists(self.data):
            sys.stderr.write('Upload file %s not found\n' % self.data)
            sys.exit(-1)
        self.ftp = fl.FTP()
        self.k = 0
        self.lastChunkSum = 0
        self.startChunk = dt.datetime.now()
        self.stopChunk = 0
        self.intervalDuration = intervalDuration

    def processChunk(self,chunk):
        self.size.value += len(chunk)

    def Run(self,q,filename):
        sys.stderr.write("Connect\n")
        try:
            self.ftp.connect(self.host,self.port,self.timeout)
        except Exception as e:
            sys.stderr.write("Connection establishment failed. Quit.\n")
            sys.exit(-1)
        try:
            sys.stderr.write("Trying to login\n")
            self.ftp.login(self.user,self.password)
        except Exception as e:
            sys.stderr.write("Connection timed out. Quit.\n")
            sys.exit(-1)
        # sys.stderr.write(str(self.ftp.dir())+'\n') # dir() writes to stdout
        #sys.stderr.write(str(self.ftp.size(self.data))+'\n')
        sys.stderr.flush()
        if self.upload:
            sys.stderr.write("Upload: chdir to %s\n" % self.upload)
            self.ftp.cwd(self.upload)
        start = dt.datetime.now()
        self.ftp.set_pasv(True)
        try:
            if self.upload:
                self.ftp.storbinary('STOR '+self.data,open(self.data,'rb'),blocksize=1024,callback=self.processChunk)
            else:
                self.ftp.retrbinary('RETR '+self.data,callback=self.processChunk) # blocksize=1024*16
        except KeyboardInterrupt as e:
            # sys.stderr.write('Let\'s stop FTP\n')
            pass
        stop = dt.datetime.now()
        diff = stop-start
        self.ftp.quit
        # # Get stats
        # if self.upload:
        #     mode = "uploaded"
        # else:
        #     mode = "downloaded"
        # print("Total bytes %s: %d" % (mode,self.size.value))
        # print("Total duration: %.2f [s]" % (diff.total_seconds()))
        # throughput_Bs = self.size.value / diff.total_seconds()
        # print("Throughput: %.2f Mbit/s" % ((throughput_Bs/1e6) * 8))
        # # Save to file
        # f = open(filename,'w')
        # f.write(str(dt.datetime.now())+'\n')
        # f.write("Total bytes downloaded: %d" % (self.size.value)+'\n')
        # f.write("Total duration: %.2f [s]" % (diff.total_seconds())+'\n')
        # f.write("Throughput: %.2f Mbit/s" % ((throughput_Bs/1e6) * 8)+'\n')
        # f.write("Interval duration: %.2f [s]" % (self.intervalDuration) + '\n')
        # while q.empty() is not True:
        #     res = q.get()
        #     f.write('%d %d %s %.2f Mbit/s' % (res[0],res[1],res[2],res[3],)+'\n')
        # f.close()

    def printSize(self,q,size,triggerCounter,filename,upload,processes):
        self.k = 0
        start = dt.datetime.now() # Default
        try:
            self.startChunk = dt.datetime.now()
            time.sleep(self.intervalDuration)
            while True:
                self.stopChunk = dt.datetime.now()
                currentValue = self.size.value
                # Does not make sense to start before we do get
                # something
                if currentValue <= 0:
                    # print(currentValue) # Debug
                    start = dt.datetime.now() # Keep on updating as long as we don't have data
                timeDiff = self.stopChunk - self.startChunk
                self.startChunk = dt.datetime.now()
                sizeDiff = currentValue - self.lastChunkSum
                # Can also print timeDiff.total_seconds() or
                # timeDiff.total_seconds()-self.intervalDuration
                trigger = triggerCounter.value
                print(self.k,trigger,self.startChunk,timeDiff.total_seconds(),self.lastChunkSum, currentValue, end=" ")
                self.lastChunkSum = currentValue
                throughput = (sizeDiff/1e6/timeDiff.total_seconds())*8
                print("%.2f Mbit/s" % throughput)
                # Store for later use
                q.put((self.k,trigger,self.startChunk,throughput))
                self.k += 1
                time.sleep(self.intervalDuration)

        except KeyboardInterrupt as e:
            stop = dt.datetime.now()
            diff = stop-start
            # Get stats
            if upload:
                mode = "uploaded"
            else:
                mode = "downloaded"
            print("Processes: %d" % (processes))
            print("Total bytes %s: %d" % (mode,size.value))
            print("Total duration: %.2f [s]" % (diff.total_seconds()))
            throughput_Bs = size.value / diff.total_seconds()
            print("Throughput: %.2f Mbit/s" % ((throughput_Bs/1e6) * 8))
            # Save to file
            f = open(filename,'w')
            f.write(str(dt.datetime.now())+'\n')
            f.write("Processes: %d\n" % (processes))
            f.write("Total bytes downloaded: %d" % (size.value)+'\n')
            f.write("Total effective duration: %.2f [s]" % (diff.total_seconds())+'\n')
            f.write("Throughput: %.2f Mbit/s" % ((throughput_Bs/1e6) * 8)+'\n')
            f.write("Interval duration: %.2f [s]" % (self.intervalDuration) + '\n')
            while q.empty() is not True:
                res = q.get()
                f.write('%d %d %s %.2f Mbit/s' % (res[0],res[1],res[2],res[3],)+'\n')
            f.close()


def sayHello():
    while True:
        print("Hello")
        time.sleep(1)

def triggerCount(triggerCounter,serialPort):
    try:
        ser = serial.Serial(port=serialPort, baudrate=19200, \
                            bytesize=8, parity='N', stopbits=1, \
                            timeout=20, xonxoff=False, rtscts=False)
    except serial.SerialException as e:
        sys.stderr.write('Can not connect to serial port %s. Disable trigger count.\n' % serialPort)
        sys.exit(-1)
    count = False
    impulse = 0
    try:
        while True:
            ding = ser.read(1)
            # Leave the mirror (start counting, only if we haven't so far)
            if impulse == 0 and ding == b'{':
                count = True
                continue
            # Enters the mirror (again, we can stop counting)
            elif count == True and ding == b'}':
                count = False
                # sys.exit(0)
            if count == True:
                impulse += 1
                triggerCounter.value = impulse
    except KeyboardInterrupt as e:
        pass

def main():
    parser = argparse.ArgumentParser(description='FTP throughput measurements.')
    # parser.add_argument('-l','--log', type=str, default='DEBUG', help='Set logging level (DEBUG|INFO|WARN|CRIT)')
    parser.add_argument('-u','--upload', type=str, help='Activate uplink and specific directory to copy things')
    parser.add_argument('-i','--interval', type=float, default=1.0, help='Measurement interval duration')
    parser.add_argument('-t','--timeout', type=int, default=10, help='FTP timeout in seconds')
    parser.add_argument('-f','--filename', type=str, default='ftp_data.txt', help='File to write output')
    parser.add_argument('-d','--data', type=str, default='/mirror/ubuntu-cdimage/13.10/ubuntu-13.10-server-amd64+mac.iso', help='Data to download/upload to create traffic')
    parser.add_argument('--host',type=str, default='mirror.switch.ch',  help='Ftp host')
    parser.add_argument('-n','--netrc', type=str, default='sample.netrc', help='Location of netrc file to use')
    parser.add_argument('-s','--serial', type=str, help='Serial port to use')
    parser.add_argument('-p','--processes', type=int, default=1, help='Number of processes to start')
    args = parser.parse_args()


    # if not isinstance(getattr(logging,args.log.upper()), int):
    #     raise ValueError('Invalid log level: %s' % args.log)

    # # Setup logging: see http://docs.python.org/dev/howto/logging.html#logging-basic-tutorial
    # logging.basicConfig(level=args.log.upper())

    # Shared counter for the size calculation
    size = Value('i', 0)
    triggerCounter = Value('i', 0)
    # Shared queue for throughput measurements
    q = Queue()
    # Run stuff
    p = []
    for k in range(0,args.processes):
        print('Setup FTP download %d' % k)
        ftp = Ftp(size,args.interval,args.timeout,args.host,args.netrc,args.data,args.upload)
        p.append(Process(target=ftp.Run, args=(q,args.filename)))
        p[k].start()
        # p1 = Process(target=ftp.Run, args=(q,args.filename))
        # p1.start()
    if args.serial:
        p2 = Process(target=triggerCount, args=(triggerCounter,args.serial))
        p2.start()

    try:
        ftp.printSize(q,size,triggerCounter,args.filename,args.upload,args.processes)
    except KeyboardInterrupt as e:
        pass

    #p2 = Process(target=ftp.printSize, args=(q,))
    #p2.start()

    #try:
        #p1.join()
        #p2.join()
    #except KeyboardInterrupt as e:
        # sys.stderr.write('Let\'s stop\n')
    #    pass

if __name__ == "__main__":
    main()
