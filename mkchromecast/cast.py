#!/usr/bin/env python

# This file is part of mkchromecast.

from __future__ import print_function
from mkchromecast.__init__ import *
from mkchromecast.audio_devices import *
import mkchromecast.colors as colors
from mkchromecast.config import *
from mkchromecast.preferences import ConfigSectionMap
from mkchromecast.utils import terminate
from mkchromecast.pulseaudio import remove_sink
import time
import pychromecast
from pychromecast.dial import reboot
import socket
import os.path
import pickle
import subprocess
import mkchromecast.colors as colors
from threading import Thread

"""
Configparser is imported differently in Python3
"""
try:
    import ConfigParser
except ImportError:
    import configparser as ConfigParser # This is for Python3

"""
We verify that soco is installed to give Sonos support
"""
try:
    import soco
    sonos = True
except ImportError:
    sonos = False


class casting(object):
    """Main casting class.
    """
    def __init__(self):                     # __init__ to call the self.ip
        import mkchromecast.__init__        # This is to verify against some needed variables
        self.platform = mkchromecast.__init__.platform
        self.tray = mkchromecast.__init__.tray
        self.select_cc = mkchromecast.__init__.select_cc
        self.debug = mkchromecast.__init__.debug
        self.backend = mkchromecast.__init__.backend
        self.adevice = mkchromecast.__init__.adevice
        self.sourceurl = mkchromecast.__init__.sourceurl
        self.discover = mkchromecast.__init__.discover
        self.host = mkchromecast.__init__.host
        self.ccname = mkchromecast.__init__.ccname
        self.hijack = mkchromecast.__init__.hijack
        self.tries = mkchromecast.__init__.tries
        self.title = 'Mkchromecast v' + mkchromecast.__init__.__version__

        if self.host == None:
            if self.platform == 'Linux':
                self.getnetworkip()
                try:
                    self.ip = self.discovered_ip
                except AttributeError:
                    self.ip = '127.0.0.1'
            else:
                try:
                    self.ip = socket.gethostbyname(socket.gethostname())
                    if self.debug == True:
                        print(':::cast::: sockets method', self.ip)
                except socket.gaierror:
                    self.netifaces_ip()
                    try:
                        self.ip = self.discovered_ip
                    except AttributeError:
                        self.ip = '127.0.0.1'
        else:
            self.ip = self.host

    """
    Methods to discover local IP
    """
    def getnetworkip(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            s.connect(("8.8.8.8", 80))
        except socket.error:
            self.ip = '127.0.0.1'
        self.discovered_ip = s.getsockname()[0]
        if self.debug == True:
            print(':::cast::: sockets method', self.discovered_ip)

    def netifaces_ip(self):
        import netifaces
        interfaces = netifaces.interfaces()
        for interface in interfaces:
            if interface == 'lo':
                continue
            iface = netifaces.ifaddresses(interface).get(netifaces.AF_INET)
            if iface != None and iface[0]['addr'] != '127.0.0.1':
                for e in iface:
                    self.discovered_ip = str(e['addr'])
                    if self.debug == True:
                        print(':::cast::: netifaces method', self.discovered_ip)

    def _get_chromecasts(self):
        # compatibility
        try:
            return list(pychromecast.get_chromecasts_as_dict().keys())
        except AttributeError:
            self._chromecasts_by_name = {c.name: c for c in pychromecast.get_chromecasts(tries=self.tries)}
            return list(self._chromecasts_by_name.keys())

    def _get_chromecast(self, name):
        # compatibility
        try:
            return pychromecast.get_chromecast(friendly_name=self.cast_to)
        except AttributeError:
            return self._chromecasts_by_name[name]

    """
    Cast processes
    """
    def initialize_cast(self):
        import mkchromecast.__init__            # This is to verify against some needed variables.
        from pychromecast import socket_client  # This fixes the `No handlers could be found for logger "pychromecast.socket_client` warning"`.
                                                # See commit 18005ebd4c96faccd69757bf3d126eb145687e0d.
        self.cclist = self._get_chromecasts()
        self.cclist = [ [index, _, 'Gcast'] for index, _ in enumerate(self.cclist) ]

        if sonos == True:
            try:
                self.sonos_list = list(soco.discover())
                length = len(self.cclist)
                for self.index, device in enumerate(self.sonos_list):
                    add_sonos = [self.index, device, 'Sonos']
                    self.cclist.append(add_sonos)
            except TypeError:
                pass

        if self.debug == True:
            print('self.cclist', self.cclist)

        """
        This block was used for casting youtube with pychromecast, but it does not work
        """
        """
        try:
            self.youtubeurl = mkchromecast.__init__.youtubeurl
        except AttributeError:
            self.youtubeurl = None
        """

        if (len(self.cclist) != 0 and self.select_cc == False and
                self.ccname == None):
            if self.debug == True:
                print('if len(self.cclist) != 0 and self.select_cc == False:')
            print(' ')
            print(colors.important('List of Devices Available in your Network:'))
            print(colors.important('------------------------------------------\n'))
            print(colors.important('Index \tTypes \tFriendly Name '))
            print(colors.important('===== \t===== \t============= '))
            self.availablecc()
            print(' ')
            if self.discover == False:
                print(colors.important('We will cast to first device in the list above!'))
                print(colors.important('You can select devices by using the -s flag.'))
                print(' ')
                self.cast_to = self.cclist[0][1]
                if self.cclist[0][2] == 'Sonos':
                    print(colors.success(self.cast_to.player_name))
                else:
                    print(colors.success(self.cast_to))
                print(' ')

        elif (len(self.cclist) != 0 and self.select_cc == True and
                self.tray == False and self.ccname == None):
            if self.debug == True:
                print('elif len(self.cclist) != 0 and self.select_cc == True and self.tray == False:')
            if os.path.exists('/tmp/mkchromecast.tmp') == False:
                self.tf = open('/tmp/mkchromecast.tmp', 'wb')
                print(' ')
                print(colors.important('List of Devices Available in your Network:'))
                print(colors.important('------------------------------------------\n'))
                print(colors.important('Index \tTypes \tFriendly Name '))
                print(colors.important('===== \t===== \t============= '))
                self.availablecc()
            else:
                if self.debug == True:
                    print('else:')
                self.tf = open('/tmp/mkchromecast.tmp', 'rb')
                self.index=pickle.load(self.tf)
                self.cast_to = self.cclist[int(self.index)]
                print(' ')
                print(colors.options('Casting to:') + ' ' + colors.success(self.cast_to))
                print(' ')

        elif (len(self.cclist) != 0 and self.select_cc == True and
                self.tray == True):
            if self.debug == True:
                print('elif len(self.cclist) != 0 and self.select_cc == True and self.tray == True:')
            if os.path.exists('/tmp/mkchromecast.tmp') == False:
                self.tf = open('/tmp/mkchromecast.tmp', 'wb')
                print(' ')
                print(colors.important('List of Devices Available in your Network:'))
                print(colors.important('------------------------------------------\n'))
                print(colors.important('Index \tTypes \tFriendly Name '))
                print(colors.important('===== \t===== \t============= '))
                self.availablecc()
            else:
                if self.debug == True:
                    print('else:')
                self.tf = open('/tmp/mkchromecast.tmp', 'rb')
                self.cast_to=pickle.load(self.tf)
                self.availablecc()
                print(' ')
                print(colors.options('Casting to:') + ' ' + colors.success(self.cast_to))
                print(' ')

        elif len(self.cclist) == 0 and self.tray == False:
            if self.debug == True:
                print('elif len(self.cclist) == 0 and self.tray == False:')
            print(colors.error('No devices found!'))
            if self.platform == 'Linux' and self.adevice == None:
                remove_sink()
            elif self.platform == 'Darwin':
                inputint()
                outputint()
            terminate()
            exit()

        elif len(self.cclist) == 0 and self.tray == True:
            print(colors.error(':::Tray::: No devices found!'))
            self.availablecc = []

    def sel_cc(self):
        print(' ')
        print('Please, select the ' + colors.important('Index') + ' of the Google Cast device that you want to use:')
        self.index = input()

    def inp_cc(self):
        while True:
            try:
                pickle.dump(self.index, self.tf)
                self.tf.close()
                self.cast_to = self.cclist[int(self.index)][1]
                print(' ')
                print(colors.options('Casting to:') + ' ' + colors.success(self.cast_to))
                print(' ')
            except TypeError:
                print(colors.options('Casting to:') + ' ' + colors.success(self.cast_to.player_name))
            except IndexError:
                checkmktmp()
                self.tf = open('/tmp/mkchromecast.tmp', 'wb')
                self.sel_cc()
                continue
            break

    def get_cc(self):
        if self.debug == True:
            print('def get_cc(self):')
        try:
            if self.ccname != None:
                self.cast_to = self.ccname
            self.cast = self._get_chromecast(self.cast_to)
            # Wait for cast device to be ready
            self.cast.wait()
            print(' ')
            print(colors.important('Information about ') + ' ' + colors.success(self.cast_to))
            print(' ')
            print(self.cast.device)
            print(' ')
            print(colors.important('Status of device ') + ' ' + colors.success(self.cast_to))
            print(' ')
            print(self.cast.status)
            print(' ')
        except pychromecast.error.NoChromecastFoundError:
            print(colors.error('No Chromecasts matching filter criteria were found!'))
            if self.platform == 'Darwin':
                inputint()
                outputint()
            elif self.platform == 'Linux':
                remove_sink()
            if self.tray == False:  # In the case that the tray is used, we don't kill the application
                print(colors.error('Finishing the application...'))
                terminate()
                exit()
            else:
                self.stop_cast()
        except AttributeError:
            pass
        except KeyError:
            pass

    def play_cast(self):
        if self.debug == True:
            print('def play_cast(self):')
        localip = self.ip

        try:
            print(colors.options('The IP of ')
                    + colors.success(self.cast_to) + colors.options(' is:')
                    + ' ' + self.cast.host)
        except TypeError:
            print(colors.options('The IP of ')
                    + colors.success(self.cast_to.player_name)
                    + colors.options(' is:') + ' ' + self.cast_to.ip_address)
        except AttributeError:
            for _ in self.sonos_list:
                if self.cast_to in _.player_name:
                    self.cast_to = _
            print(colors.options('The IP of ')
                    + colors.success(self.cast_to.player_name)
                    + colors.options(' is:') + ' ' + self.cast_to.ip_address)

        if self.host == None:
            print(colors.options('Your local IP is:') + ' ' + localip)
        else:
            print(colors.options('Your manually entered local IP is:') + ' ' + localip)

        try:
            media_controller = self.cast.media_controller

            if self.tray == True:
                config = ConfigParser.RawConfigParser()
                configurations = config_manager()    # Class from mkchromecast.config
                configf = configurations.configf

                if os.path.exists(configf) and self.tray == True:
                    print(tray)
                    print(colors.warning('Configuration file exists'))
                    print(colors.warning('Using defaults set there'))
                    config.read(configf)
                    self.backend = ConfigSectionMap('settings')['backend']

            if self.sourceurl != None:
                if args.video == True:
                    import mkchromecast.video
                    mtype = mkchromecast.video.mtype
                else:
                    import mkchromecast.audio
                    mtype = mkchromecast.audio.mtype
                print(' ')
                print(colors.options('Casting from stream URL:') + ' ' + self.sourceurl)
                print(colors.options('Using media type:') + ' ' + mtype)
                media_controller.play_media(self.sourceurl, mtype, title=self.title)
            elif (self.backend == 'ffmpeg' or self.backend == 'node' or
                    self.backend == 'avconv' or self.backend == 'parec' or
                    self.backend == 'gstreamer' and self.sourceurl == None):
                if args.video == True:
                    import mkchromecast.video
                    mtype = mkchromecast.video.mtype
                else:
                    import mkchromecast.audio
                    mtype = mkchromecast.audio.mtype
                print(' ')
                print(colors.options('The media type string used is:') + ' ' + mtype)
                media_controller.play_media('http://' + localip + ':5000/stream', mtype, title=self.title)
            print(' ')
            print(colors.important('Cast media controller status'))
            print(' ')
            print(self.cast.status)
            print(' ')
            if self.hijack == True:
                self.r = Thread(target=self.hijack_cc)
                self.r.daemon = True   # This has to be set to True so that we catch KeyboardInterrupt.
                self.r.start()
        except AttributeError:
            self.sonos = self.cast_to
            self.sonos.play_uri('x-rincon-mp3radio://' + localip + ':5000/stream', title=self.title)
            if self.tray == True:
                self.cast = self.sonos

    def stop_cast(self):
        try:
            self.cast.quit_app()
        except AttributeError:
            self.sonos.stop()

    def volume_up(self):
        """ Increment volume by 0.1 unless it is already maxed.
        Returns the new volume.
        """
        if self.debug == True:
            print('Increasing volume... \n')
        try:
            volume = round(self.cast.status.volume_level, 1)
            return self.cast.set_volume(volume + 0.1)
        except AttributeError:
            self.sonos.volume += 1
            self.sonos.play()

    def volume_down(self):
        """ Decrement the volume by 0.1 unless it is already 0.
        Returns the new volume.
        """
        if self.debug == True:
            print('Decreasing volume... \n')
        try:
            volume = round(self.cast.status.volume_level, 1)
            return self.cast.set_volume(volume - 0.1)
        except AttributeError:
            self.sonos.volume -= 1
            self.sonos.play()

    def reboot(self):
        if self.platform == 'Darwin':
            self.cast.host = socket.gethostbyname(self.cast_to + '.local')
            reboot(self.cast.host)
        else:
            print(colors.error('This method is not supported in Linux yet.'))

    def availablecc(self):
        """This method is used for populating the self.availablecc array
        needed for the system tray.
        """
        self.availablecc = []
        for (self.index, device) in enumerate(self.cclist):
            try:
                types = device[2]
                if types == 'Sonos':
                    device_ip = device[1].ip_address
                    device = device[1].player_name
                else:
                    device = device[1]
                print('%s \t%s \t%s' % (self.index, types, device))
            except UnicodeEncodeError:
                types = device[2]
                if types == 'Sonos':
                    device_ip = device[1].ip_address
                    device = device[1].player_name
                else:
                    device = device[1]
                print('%s \t%s \t%s' % (self.index, device[2], str(unicode(device).encode("utf-8"))))

            if types == 'Sonos':
                to_append = [self.index, device, types, device_ip]
            else:
                to_append = [self.index, device, types]
            self.availablecc.append(to_append)

    def hijack_cc(self):
        """Dummy method to call  _hijack_cc_().

        In the cast that the self.r thread is alive, we check that the
        chromecast is connected. If it is connected, we check again in
        5 seconds.
        """
        try:
            while self.r.is_alive():
                self._hijack_cc_()
                time.sleep(5)       #FIXME: I think that this has to be set by users.
        except KeyboardInterrupt:
            self.stop_cast()
            if platform == 'Darwin':
                inputint()
                outputint()
            elif platform == 'Linux' and adevice == None:
                remove_sink()
            terminate()

    def _hijack_cc_(self):
        """Check if chromecast is disconnected and hijack.

        This function checks if the chromecast is online. Then, if the display
        name is different from "Default Media Receiver", it hijacks to the
        chromecast.
        """
        ip = self.cast.host
        if ping_chromecast(ip) == True:     # The chromecast is online.
            if str(self.cast.status.display_name) != "Default Media Receiver":
                self.ccname = self.cast_to
                self.get_cc()
                self.play_cast()
        else:                               # The chromecast is offline.
            try:
                self.ccname = self.cast_to
                self.get_cc()
                self.play_cast()
            except AttributeError:
                pass

def ping_chromecast(ip):
    """This function pings to hosts.

    Credits: http://stackoverflow.com/a/34455969/1995261
    """
    try:
        output = subprocess.check_output("ping -c 1 " + ip, shell=True)
    except:
        return False
    return True
