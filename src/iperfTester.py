#!/usr/bin/python

import subprocess, platform
import sys
from datetime import datetime, timedelta
import socket, struct
import csv
import time
from netmiko import ConnectHandler
from netmiko.ssh_exception import NetMikoTimeoutException,NetMikoAuthenticationException

def getHostname():
    try:
        hostname = net_connect.find_prompt()
    except (NetMikoTimeoutException,NetMikoAuthenticationException,ValueError):
        return
    return hostname[:-1]

def getConfiguration():
    try:
        config = net_connect.send_command("show run")
    except (NetMikoTimeoutException,NetMikoAuthenticationException,ValueError):
        return
    return config

def getRawCDP():
    try:
        cdp = net_connect.send_command("show cdp neighbor")
    except (NetMikoTimeoutException,NetMikoAuthenticationException,ValueError):
        return
    return cdp

def getNeighbors(interface):
    
    # we expect the interface names to be passed to us
    # in our case it is going to always be Gi1/19 and Gi1/20
    # but who knows what the future will bring
    
    neighbor_name = 0
    neighbor_ip = 0
    
    try:
        command = 'show cdp neighbor ' + interface + ' detail | i Device'
        neighbor_name = net_connect.send_command(command)
        
        # I got fancy here, and we only keep looking for the IP if we've already
        # got the name
        if neighbor_name:
            neighbor_name = neighbor_name.split(":")[1].lstrip().split(".")[0]
            command = 'show cdp neighbor ' + interface + ' detail | i IP address'
            neighbor_ip = net_connect.send_command(command)
            neighbor_ip = neighbor_ip.split(":")[1].lstrip().rstrip()
    except (NetMikoTimeoutException,NetMikoAuthenticationException,ValueError):
        return
    # we just return the names of the AP peers
    return neighbor_name,neighbor_ip

def getNeighborWithRoute(testIP):
    
    # we look at the asset switch routing table
    # and figure out what interface the route for the test server is on
    # then we grab the cdp name and IP of the AP on that link
    
    # if we can get the info we need, then we just make sure that the
    # results are zeroed out
    car0_facing_ap_name = 0
    car0_facing_ap_ip = 0
    
    try:
        # first get the RIB entry for the test server IP
        command = 'show ip route ' + testIP + ' | i via Gig'
        interface = 0
        

        
        # we break that output by spaces, and interate through the list
        # we do this because we can't guarantee that the interface name will
        # always be in the same spot
        for interface in net_connect.send_command(command).split(" "):
            if "Gigabit" in interface:
                break
        
        # this will only be true if we've got a matching route and we've
        # pulled out the interface name
        if interface:
            
            # now we can get the CDP info for this device
            # we hope it is an AP
            command = 'show cdp neighbor ' + interface + ' detail | i Device'
            car0_facing_ap_name = net_connect.send_command(command)
            
            # I got fancy here, and we only keep looking for the IP if we've already
            # got the name
            if car0_facing_ap_name:
                car0_facing_ap_name = car0_facing_ap_name.split(":")[1].lstrip().split(".")[0]
                command = 'show cdp neighbor ' + interface + ' detail | i IP address'
                car0_facing_ap_ip = net_connect.send_command(command).split(":")[1].lstrip().rstrip()

    except (NetMikoTimeoutException,NetMikoAuthenticationException,ValueError):
        pass
    
    # even if it is just zeroes, we still return the info to the main script
    return car0_facing_ap_name,car0_facing_ap_ip

def getAPtelemetry():
    
    # we want to send back the telemetry data for data rate, bandwidth,
    # signal strength and signal to noise
    # but if we fail for some reason, let's just return zeroed out fields
    DR = 0
    BW = 0
    SS = 0
    SN = 0
    
    try:
        # first we get the associations
        # and we filter out for the one that is a bridge
        # sometimes this output shows more than one entry
        command = 'sh dot11 assoc | i bridge'
        remote_peer = net_connect.send_command(command).split(" ")[0]
        
        # then we pull the data we need for the remote peer
        # DATA RATE
        command = ' sh dot11 assoc ' + remote_peer + ' | i Current Rate'
        DR = net_connect.send_command(command).split(":")[1].lstrip().split(" ")[0]
        
        # BANDWIDTH
        command = ' sh dot11 assoc ' + remote_peer + ' | i Bandwidth'
        BW = net_connect.send_command(command).split(":")[2].lstrip()
        
        # SIGNAL STRENGTH
        command = ' sh dot11 assoc ' + remote_peer + ' | i Strength'
        SS = net_connect.send_command(command).split(":")[1].lstrip().split(" ")[0] + " dBm"
        
        # SIGNAL TO NOISE
        command = ' sh dot11 assoc ' + remote_peer + ' | i Noise'
        SN = net_connect.send_command(command).split(":")[1].lstrip().split(" ")[0] + " dB"        
    except (NetMikoTimeoutException,NetMikoAuthenticationException,ValueError):
        pass
    
    return DR,BW,SS,SN

def get_default_gateway_linux():
    # Read the default gateway directly from /proc.
    with open("/proc/net/route") as fh:
        for line in fh:
            fields = line.strip().split()
            if fields[1] != '00000000' or not int(fields[3], 16) & 2:
                continue
            return socket.inet_ntoa(struct.pack("<L", int(fields[2], 16)))

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
    print "Usage: " + sys.argv[0] + " [asset] [local asset switch]"
    print "asset switch is optional, only needed if the detection doesn't work"
    exit()

# get the remote iperf endpoint as an argument
#remote = sys.argv[1]
remote = "10.65.0.10"

# we do 10s tests
testTime = 10

# get the total test duration as an argument
#totalDuration = int(sys.argv[2])
totalDuration = 1

#default port is 5201
testPort = 5201

# if the port is not passed as a parameter, don't completely die
# just use the default port
#try:
#    # get the test port
#    if sys.argv[4]:
#        testPort = int(sys.argv[3])
#    else:
#        testPort = 5201
#
#except IndexError:
#    pass

# we sanitize the tcp port used
# we don't allow ports less than 1024 or greater than 65335
# because that would be dumb
if (testPort <=1024) or (testPort >=65535):
    print "Port must be between 1024 and 65535"
    exit()

# we can't guarantee that we know the asset name/number
# so we might have to make it up
asset = "unknown"

# we hope that the tester can supply the asset name/number
# but we will try to learn the correct info from the switch too
try:
    # get the asset number
    if sys.argv[1]:
        asset_argv = sys.argv[1]
        asset = asset_argv
except IndexError:
    pass

# we will try to automatically detect the IP of the local asset switch
# but if this doesn't work the tester can optionally supply it
assetip = 0
try:
    # get the default gateway
    if sys.argv[2]:
        assetip = sys.argv[2]
except IndexError:
    pass

# we use this to figure out if we're at the end of our test duration
period = timedelta(minutes=totalDuration)
next_time = datetime.now() + period

# we want to know the IP of THIS endpoint
local = get_ip()
if not assetip:
    assetip = get_default_gateway_linux()
    
if check_ping(remote):
    
    # first we want to connect to the local asset switch to gather some info
    switch = {
        'device_type': 'cisco_ios',
        'ip': assetip,
        'username': 'cisco',
        'password': 'cisco',
        'secret': 'cisco',
        'port' : 22          # optional, defaults to 22
    }
        
    try:
        # this is what we connect to
        net_connect = ConnectHandler(**switch)
        
        # we want to learn the hostname of the local asset switch
        # this will tell us exactly where we are
        asset = net_connect.find_prompt()[:-1]
    except (NetMikoTimeoutException,NetMikoAuthenticationException,ValueError):
        
        # if we're not able to connect to the switch, we're not going to be able
        # to learn the connected AP info, or gather telemetry from them         
        car0_via_ap_name = 0
        car0_via_ap_ip = 0
        print "Could not reach the switch at " + assetip
    else:
        # this only gets triggered if we're able to ssh into the switch
        
        # we learn what AP is in the path for the test iperf system
        # and we record its name and IP
        (car0_via_ap_name,car0_via_ap_ip) = getNeighborWithRoute(remote)
        
        # we always sanely disconnect
        net_connect.disconnect()

    dataRate = 0
    bandwidth = 0
    signalStrength = 0
    signal2Noise = 0
    
    # if we were able to reach the switch and actually learn what AP is connected
    # in the path of the testing system, we can gather some AP telemetry
    if (car0_via_ap_ip and car0_via_ap_name):
        access_point = {
            'device_type': 'cisco_ios',
            'ip': car0_via_ap_ip,
            'username': 'cisco',
            'password': 'cisco',
            'secret': 'cisco',
            'port' : 22          # optional, defaults to 22
        }
            
        try:
            # this is what we connect to
            net_connect = ConnectHandler(**access_point)
            
            # here is where we want to learn all the important stuff
            (dataRate,bandwidth,signalStrength,signal2Noise) = getAPtelemetry()
        except (NetMikoTimeoutException,NetMikoAuthenticationException,ValueError):
            print "Could not reach the AP at " + car0_via_ap_ip
    
    # we use this as the CSV filename for output
    currentDateTime = str((datetime.date(datetime.now()))) + "." + str(datetime.time(datetime.now())).split(".")[0].replace(':','.')
    
    # we use this as row data in the output
    currentDate = str((datetime.date(datetime.now())))

    # initialize the dictionary
    database = {}
    
    # we stay in this loop unless the time exceeds 10m
    while next_time >= datetime.now():
        # we use this as row data in the output
        currentTime = str(datetime.time(datetime.now())).split(".")[0]
        
        # initialize the dictionary INSIDE the dictionary
        database[currentTime] = {}
        
        # this calls the iperfTestActual function
        # the returned variables are the speed, and rate of the test
        # those are dropped into the database[currentTime] nested dictonary
        
        (database[currentTime]["forwardSpeed"],database[currentTime]["forwardRate"]) = iPerfTestActual(remote, "forward",testPort)
        
        # print a dot so the user knows it is working
        sys.stdout.write('.')
        sys.stdout.flush()
        
        # this calls the iperfTestActual function
        # the returned variables are the speed, and rate of the test
        # those are dropped into the database[currentTime] nested dictonary
        
        (database[currentTime]["reverseSpeed"],database[currentTime]["reverseRate"]) = iPerfTestActual(remote, "reverse",testPort)
        
        # print a dot so the user knows it is working
        sys.stdout.write('.')
        sys.stdout.flush()
        
    # print a newline so it looks nice
    print ""
        
    # append to master CSV
    # this creates a single CSV for this host for all tests
    with open(asset + ".csv", "ab") as csvfile:
        csvoutput = csv.writer(csvfile, delimiter=',')
        # iterate through the dictionary and
        # drop the value, key pairs as variables that we can reference
        # timeLoop is just the current time
        # dictLoop is a dictionary containing the results of the tests
        for timeLoop, dictLoop in database.items():
            csvoutput.writerow([asset,asset_argv,local,remote,currentDate,timeLoop,car0_via_ap_name,dataRate,bandwidth,signalStrength,signal2Noise,dictLoop["forwardSpeed"],dictLoop["forwardRate"],dictLoop["reverseSpeed"],dictLoop["reverseRate"]])
    # sanely close the file handler
    csvfile.close()
    
else:
    print "Not pingable, gathering local switch and AP configs"
    
    # first we want to connect to the local asset switch to gather some info
    switch = {
        'device_type': 'cisco_ios',
        'ip': assetip,
        'username': 'cisco',
        'password': 'cisco',
        'secret': 'cisco',
        'port' : 22          # optional, defaults to 22
    }
        
    try:
        # this is what we connect to
        net_connect = ConnectHandler(**switch)
        
        # we want to learn the hostname of the local asset switch
        # this will tell us exactly where we are
        asset = net_connect.find_prompt()[:-1]
    except (NetMikoTimeoutException,NetMikoAuthenticationException,ValueError):
        
        # if we're not able to connect to the switch, we're not going to be able
        # to learn the connected AP info, or gather configs from them         
        forwardAPname = 0
        forwardAPaddress = 0
        rearwardAPname = 0
        rearwardAPaddress = 0
        
        print "Could not reach the switch at " + assetip
        quit()
    else:
        # this only gets triggered if we're able to ssh into the switch
        
        troublefile = open(asset + "-" + str(datetime.now()) + ".txt","w")
    
        # we learn what AP is in the path for the test iperf system
        # and we record its name and IP
        (forwardAPname,forwardAPaddress) = getNeighbors("Gi1/19")
        (rearwardAPname,rearwardAPaddress) = getNeighbors("Gi1/20")

        troublefile.write(getRawCDP())
        troublefile.write(getConfiguration())
    
        # we always sanely disconnect
        net_connect.disconnect()

    # if we were able to reach the switch and actually learn what AP is connected
    # in the path of the testing system, we can gather some AP info
    if (forwardAPname):
        access_point = {
            'device_type': 'cisco_ios',
            'ip': forwardAPaddress,
            'username': 'cisco',
            'password': 'cisco',
            'secret': 'cisco',
            'port' : 22          # optional, defaults to 22
        }
            
        try:
            # this is what we connect to
            net_connect = ConnectHandler(**access_point)
            
            troublefile.write(getRawCDP())
            troublefile.write(getConfiguration())
            
        except (NetMikoTimeoutException,NetMikoAuthenticationException,ValueError):
            print "Could not reach the AP at " + forwardAPaddress
        else:
            # we always sanely disconnect
            net_connect.disconnect()
    
    # if we were able to reach the switch and actually learn what AP is connected
    # in the path of the testing system, we can gather some AP info
    if (rearwardAPname):
        access_point = {
            'device_type': 'cisco_ios',
            'ip': rearwardAPaddress,
            'username': 'cisco',
            'password': 'cisco',
            'secret': 'cisco',
            'port' : 22          # optional, defaults to 22
        }
            
        try:
            # this is what we connect to
            net_connect = ConnectHandler(**access_point)
            
            troublefile.write(getRawCDP())
            troublefile.write(getConfiguration())
            
        except (NetMikoTimeoutException,NetMikoAuthenticationException,ValueError):
            print "Could not reach the AP at " + rearwardAPaddress
        else:
            # we always sanely disconnect
            net_connect.disconnect()
    
    troublefile.close()