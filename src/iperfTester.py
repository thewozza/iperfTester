#!/usr/bin/python

import subprocess, platform
import sys
from datetime import datetime, timedelta
import csv
import socket
import time

def check_ping(hostname):

    # just do a quick ping test to the remote server
    # there's no point going further if we can't ping it
    try:
        response  = subprocess.check_output("ping -{} 1 {}".format('n' if platform.system().lower()=="windows" else 'c', hostname), shell=True)
    
    except Exception:
        return False
    return True

def iPerfTestActual(hostname,direction,port):
    
    # set the iperf variables
    if direction == "reverse":
        direction = "-R"
    else:
        direction = ""
    try:
        iperfOutput = subprocess.check_output("iperf3 -P 5 -c " + remote + " " + direction + " -i 0 -t " + str(testTime) + " -p " + str(port), shell=True).split("\n")
        
        # this lets things settle a bit
        # sometimes clients would barf if we went too fast
        time.sleep(1)
    except subprocess.CalledProcessError as e:
        # if the iperf server isn't running we should at least TRY
        # to send a human readable error message
        raise RuntimeError("command '{}' return with error (code {}): {}".format(e.cmd, e.returncode, e.output))
    
    # first draft of parsing the results
    # we only send back the summary lines
    for line in iperfOutput:
            results = line.split()
            if results[0] == "[SUM]":
                return results[5], results[6]
                break   

def get_ip():
    # I blindly copied this from the internet
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # doesn't even have to be reachable
        s.connect(('10.255.255.255', 0))
        IP = s.getsockname()[0]
    except:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

# die with instructions if someone calls this with no arguments
if len(sys.argv) == 1:
    print "Usage: " + sys.argv[0] + " [host] [duration(mins)] [port]"
    print "port parameter is optional, default is 5201"
    exit()

# get the remote iperf endpoint as an argument
remote = sys.argv[1]

# we do 10s tests
testTime = 10

# get the total test duration as an argument
totalDuration = int(sys.argv[2])

#default port is 5201
testPort = 5201

# if the port is not passed as a parameter, don't completely die
# just use the default port
try:
    # get the test port
    if sys.argv[3]:
        testPort = int(sys.argv[3])
    else:
        testPort = 5201

except IndexError:
    pass

# we sanitize the tcp port used
# we don't allow ports less than 1024 or greater than 65335
# because that would be dumb
if (testPort <=1024) or (testPort >=65535):
    print "Port must be between 1024 and 65535"
    exit()

# we use this to figure out if we're at the end of our test duration
period = timedelta(minutes=totalDuration)
next_time = datetime.now() + period

# we want to know the IP of THIS endpoint
local = get_ip()

if check_ping(remote):
    # we use this as the CSV filename for output
    currentDateTime = str((datetime.date(datetime.now()))) + "." + str(datetime.time(datetime.now())).split(".")[0]
    
    # we use this as row data in the output
    currentDate = str((datetime.date(datetime.now())))

    # initialize the dictionary
    database = {}
    
    # we stay in this loop unless the time exceeds 10m
    while next_time >= datetime.now():
        currentTime = str(datetime.time(datetime.now())).split(".")[0]
        database[currentTime] = {}
        
        (database[currentTime]["forwardSpeed"],database[currentTime]["forwardRate"]) = iPerfTestActual(remote, "forward",testPort)
        # print a dot so the user knows it is working
        sys.stdout.write('.')
        sys.stdout.flush()
        (database[currentTime]["reverseSpeed"],database[currentTime]["reverseRate"]) = iPerfTestActual(remote, "reverse",testPort)
        # print a dot so the user knows it is working
        sys.stdout.write('.')
        sys.stdout.flush()
        
    # print a newline so it looks nice
    print ""
    
    # output to CSV
    with open(currentDateTime + ".csv", "wb") as csvfile:
        csvoutput = csv.writer(csvfile, delimiter=',')
        for timeLoop, dictLoop in database.items():
            csvoutput.writerow([local,remote,currentDate,timeLoop,dictLoop["forwardSpeed"],dictLoop["forwardRate"],dictLoop["reverseSpeed"],dictLoop["reverseRate"]])
    csvfile.close()
    
    # append to master CSV
    with open(local + ".csv", "a") as csvfile:
        csvoutput = csv.writer(csvfile, delimiter=',')
        for timeLoop, dictLoop in database.items():
            csvoutput.writerow([local,remote,currentDate,timeLoop,dictLoop["forwardSpeed"],dictLoop["forwardRate"],dictLoop["reverseSpeed"],dictLoop["reverseRate"]])
    csvfile.close()
    
else:
    print "Not pingable, exiting"