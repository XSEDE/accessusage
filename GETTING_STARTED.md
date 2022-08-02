## Getting started
***
## CentOS 7 Linux 
### 1. Configure files
* Copy or Configure files in the "/etc" directory.

### 2. Install python version 3
```
$ sudo yum install -y python3
$ python3 -V
```
### 3. Set up the sudo environment
```
$ export SUDO_USER=cyoun
```

### 4. Create an account and change the ownership for the configuration files
```
% sudo adduser accessusage
% sudo groupadd accessusage
groupadd: group 'accessusage' already exists
$ sudo chown root.accessusage -R ./etc/
```

### 5. Add the current user to a group
```
$ sudo usermod -aG accessusage "your current user"

# check groups
$ id
uid=1000(cyoun) gid=1000(cyoun) groups=1000(cyoun),10(wheel),48(apache),996(vboxsf),1001(accessusage)
$ groups
cyoun wheel apache vboxsf accessusage

# If you can't see the "xdusage" group in the group list for your current user, 
# run the commandline below for the change to take effect.
# As the other way, you would need to log in again.
$ su - $USER
```

### 6. Set up the file permission mode
```
$ sudo chmod 750 ./etc
$ sudo chmod 640 -R ./etc/*.conf
```

### 7. Test accessusage version 2
```
$ python3 ./bin/accessusage.py -h
$ python3 ./bin/accessusage.py
$ python3 ./bin/accessusage.py -p TG-MCB190139
$ python3 ./bin/accessusage.py -up neesittg
$ python3 ./bin/accessusage.py -r expanse
$ python3 ./bin/accessusage.py -s 2021-06-28 -e 2021-10-01
$ python3 ./bin/accessusage.py -r expanse -ip
```

### 8. Test accessusage version 1
```
$ python3 ./bin/accessusage.py -av 1 -h
$ python3 ./bin/accessusage.py -av 1
$ python3 ./bin/accessusage.py -av 1 -p TG-MCB190139
$ python3 ./bin/accessusage.py -av 1 -up cyoun
$ python3 ./bin/accessusage.py -av 1 -r expanse
$ python3 ./bin/accessusage.py -av 1 -s 2021-06-28 -e 2021-10-01
$ python3 ./bin/accessusage.py -av 1 -r expanse -ip
```
