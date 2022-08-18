import grp
import json
import os 
import pwd
import re
import socket
import time
import sys
import urllib

is_root = None



def check_resource(options, config, resources_func):
    local_resource = config["resource"]
    # Check if the named resource is in the active XSEDE resource list.
    # construct a rest url and fetch it
    # don't forget to uri escape these things in case one has funny
    # characters
    result = json_get(options, config, resources_func)

    if not result['result'] and len(result['result']) == 0:
        if is_root:
            sys.stderr.write(
                "The resource_name '{}' specified in the configuration file '{}'\n".format(local_resource, conf_file))
            sys.stderr.write("is not listed as a current XSEDE system.\n")
            sys.stderr.write(
                "Information may not exist in the XSEDE central accounting database for this resource.\n\n")
            sys.stderr.write("Current XSEDE resources are listed at:\n")
            sys.stderr.write("https://info.xsede.org/wh1/warehouse-views/v1/resources-xdcdb-active/?format=html;sort"
                             "=ResourceID\n")
        else:
            sys.stderr.write("The resource_name '{}' specified in the configuration file is not listed as a current "
                             "XSEDE system.\n".format(local_resource))
            sys.stderr.write("Information may not exist in the XSEDE central accounting database for this resource.\n")
            sys.stderr.write("Please contact your system administrator.\n\n")
            sys.stderr.write("You can specify a different resource with the \"-r\" option.\n\n")
            sys.stderr.write("Current XSEDE resources are listed at:\n")
            sys.stderr.write("https://info.xsede.org/wh1/warehouse-views/v1/resources-xdcdb-active/?format=html;sort"
                             "=ResourceID\n")




def check_sudo(install_dir):
    """
    # Check that the /etc/sudoers file is set up correctly and
    # warn the administrator if it is not.
    :return:
    """

    found = 0
    result = run_command_line('sudo -l -n | grep accessusage')

    if len(result) > 0:
        found = 1

    if not found:
        sys.stderr.write("The /etc/sudoers file is not set up correctly.\n")
        if is_root:
            msg = "The /etc/sudoers file needs to contain the following lines in order for non-root users to run " \
                  "correctly:\t\nDefaults!{}/accessusage env_keep=\"USER\"\t\n" \
                  "Defaults!{}/accessusage runas_default=accessusage\t\n" \
                  "ALL  ALL=(accessusage) NOPASSWD:{}/accessusage\n".format(install_dir, install_dir,
                                                                                     install_dir)
            sys.stderr.write(msg)
            sys.exit()
        else:
            print("Please contact your system administrator.")
            sys.exit()




def config_error(config_file, error_message, num_parameters=1):
    """
    # Show the root user the error message for the configuration file.
    # Show other users a generic message. Exit in either case.
    :param error_message:
    :param num_parameters:
    :return:
    """

    message = ""
    if is_root:
        # If 2 parameters are passed don't show the extra message.
        if num_parameters == 2:
            message = error_message
        else:
            message = "{} \nThe configuration file ({}) should have one entry for each of the " \
                      "following:\n\tapi_key\n\tapi_id\n\tresource_name\n\trest_url_base".format(error_message,
                                                                                                   config_file)
        print(message)
        sys.exit()
    else:
        error(config_file, "There is a problem with the configuration file.\nPlease contact your system administrator.")




def error(me, msg):
    print("{}: {}".format(me, msg))
    sys.exit()




def get_config(options, accessusage_config_file, install_dir):
    config = { 
        "conf_file": None,
        "api_key": None,
        "api_id": None,
        "admin_names": [],
        "resource": None,
        "rest_url": None
    }

    # load the various settings from a configuration file
    # (api_id, api_key, rest_url_base, resource_name, admin_name)
    # file is simple key=value, ignore lines that start with #
    # list of possible config file locations
    conf_file_list = ['/etc/{}'.format(accessusage_config_file),
                      '/var/secrets/{}'.format(accessusage_config_file),
                      "{}/../etc/{}".format(install_dir, accessusage_config_file),
                      ]

    # use the first one found.
    for c in conf_file_list:
        if os.path.isfile(c) and os.access(c, os.R_OK):
            config["conf_file"] = c
            break

    # The configuration file doesn't exist.
    # Give the administrator directions to set up the script.
    if not config["conf_file"]:
        if is_root:
            sys.stderr.write("The configuration file could not be located in:\n  ")
            sys.stderr.write("\n  ".join(conf_file_list))
            sys.stderr.write("\n")
            setup_conf(accessusage_config_file)
        else:
            print("Unable to find the configuration file.\nPlease contact your system administrator.")
            sys.exit()

    # read in config file
    try:
        con_fd = open(config["conf_file"], 'r')
    except OSError:
        print("Could not open/read file, {}".format(config["conf_file"]))
        sys.exit()

    # Check ownership of the configuration file is root/accessusage.
    sb = os.lstat(config["conf_file"])
    root_uid = pwd.getpwnam("root").pw_uid
    # print("sb uid = {} root uid = {}".format(sb.st_uid, root_uid))
    if sb.st_uid != root_uid:
        config_error(accessusage_config_file, "Configuration file '{}' must be owned by user 'root'.".format(config["conf_file"]), num_parameters=2)
        # pass
    try:
        xdusage_gid = grp.getgrnam("accessusage").gr_gid
    except KeyError:
        xdusage_gid = -1
    # print("sb gid = {} accessusage gid = {}".format(sb.st_gid, xdusage_gid))
    if sb.st_gid != xdusage_gid:
        config_error(accessusage_config_file, "Configuration file '{}' must be owned by group 'accessusage'.".format(config["conf_file"]), num_parameters=2)
        # pass
    # Check that the configuration file has the correct permissions.
    # mode = stat.S_IMODE(sb.st_mode)
    mode = oct(sb.st_mode)[-3:]
    # print('mode = {} sb mode = {}'.format(mode, sb))
    # print("\nFile permission mask (in octal):", oct(sb.st_mode)[-3:])
    if mode != '640':
        message = "Configuration file '{}' has permissions '{}', it must have permissions '0640'.".format(config["conf_file"], mode)
        # uncomment it
        config_error(accessusage_config_file, message, num_parameters=2)

    # line_list = list(con_fd.readlines())
    # i = 0
    # while i < len(line_list):
    for line in con_fd:
        line = line.rstrip()
        if '#' in line:
            continue
        if len(line) == 0:
            continue
        matched = re.search('^([^=]+)=([^=]+)', line)
        if not bool(matched):
            if is_root:
                sys.stderr.write("Ignoring cruft in {}: '{}'\n".format(config["conf_file"], line))
            continue

        key = matched.group(1)
        val = matched.group(2)
        # print('key = {} val = {}'.format(key, val))
        key = re.sub(r'^\s*', '', key)
        key = re.sub(r'\s*', '', key)
        val = re.sub(r'^\s*', '', val)
        val = re.sub(r'\s*', '', val)

        if key == 'api_key':
            if config["api_key"]:
                config_error(accessusage_config_file, "Multiple 'api_key' values found.")
            config["api_key"] = val
        elif key == 'api_id':
            if config["api_id"]:
                config_error(accessusage_config_file, "Multiple 'api_id' values found.")
            config["api_id"] = val
        elif key == 'resource_name':
            if config["resource"]:
                config_error(accessusage_config_file, "Multiple 'resource_name' values found.")
            config["resource"] = val
        elif key == 'admin_name':
            config["admin_names"].insert(0, val)
        elif key == 'rest_url_base':
            if config["rest_url"]:
                config_error(accessusage_config_file, "Multiple 'rest_url_base' values found.")
            config["rest_url"] = val
        else:
            if is_root:
                sys.stderr.write("Ignoring cruft in {}: '{}'\n".format(config["conf_file"], line))

    try:
        con_fd.close()
    except OSError:
        print("Could not close file, {}".format(config["conf_file"]))
        sys.exit()

    # stop here if missing required values
    if not config["api_id"]:
        config_error(accessusage_config_file, "Unable to find the 'api_id' value.")
    if not config["api_key"]:
        config_error(accessusage_config_file, "Unable to find the 'api_key' value.")
    if not config["resource"]:
        config_error(accessusage_config_file, "Unable to find the 'resource_name' value.")
    if not config["rest_url"]:
        config_error(accessusage_config_file, "Unable to find the 'rest_url_base' value.")

    return config




def check_config(options, config, command_line, resources_func):
   # Check if the key is authorized.
    is_authorized(options, config, command_line)

    # Check if the resource specified in the configuration file is valid.
    res = check_resource(options, config, resources_func)




def check_and_run_sudo(exec_script):
    global is_root

    # Determine if the script is being run by root.
    # Root will be given setup instructions, if necessary, and
    # will be given directions to correct errors, where possible.
    # print('os uid = {} {}'.format(os.getuid(), pwd.getpwuid(os.getuid())[0]))
    is_root = (pwd.getpwuid(os.getuid())[0] == "root")
    # print('is root = {}'.format(is_root))

    # find out where this script is running from
    # eliminates the need to configure an install dir
    install_dir = os.path.dirname(os.path.abspath(exec_script))
    # print('install dir = {}'.format(install_dir))
    me = sys.argv[0].split('/')[-1]
    # print('me = {}'.format(me))

    command_line = " ".join(sys.argv[1:])
    # print('command line = {}'.format(command_line))
    if is_root:
        sys.stderr.write("You are running this script as root.\nAs an administrator, you will be given directions to "
                         "set up accessusage to run on this machine, if needed.\nWhere possible, you will also be given "
                         "instructions to correct any errors that are detected.\n\n")

    # Root needs to check that the sodoers file is set up correctly,
    # but doesn't need to run with sudo.
    logname = ''
    if is_root:
        check_sudo(install_dir)
        logname = "root"
    elif 'SUDO_USER' not in os.environ:
        # Check that the sudoers file is set up correctly.
        check_sudo(install_dir)

        # This script needs to be run by sudo to provide a reasonably-
        # assured user ID with access to the configuration file.
        # Re-run the script using sudo.
        sys.argv.insert(1, '{}/accessusage'.format(install_dir))
        #sys.argv.insert(1, "sudo")
        try:
            #print('command args = {}'.format(sys.argv[1:]))
            if os.geteuid() != 0:
                #The extra "sudo" in thesecond parameter is required because
                #Python doesn't automatically set $0 in the new process.
                os.execvp("sudo", ["sudo"] + sys.argv[1:])
        except Exception as e:
            print("command does not work: {}".format(e))
            sys.exit()

    else:
        logname = os.environ.get('SUDO_USER')

    return logname




def check_user():
    # Check that user accessusage exists, or prompt the admin to create it.
    try:
        pwd.getpwnam("accessusage")
    except KeyError:
        sys.stderr.write("Required user 'accessusage' does not exist on this system.\n")
        if is_root:
            sys.stderr.write("Create the user and run this script again.\n")
        else:
            sys.stderr.write( "Please contact your system administrator.\n")
        sys.exit()




def fmt_amount(amt, no_commas=False):
    if amt == 0:
        return '0'
    n = 2
    if abs(amt) >= 10000:
        n = 0
    elif abs(amt) >= 1000:
        n = 1

    x = float("%.{}f".format(n) % amt)
    while x == 0:
        n += 1
        x = float("%.{}f".format(n) % amt)
    # $x =~ s/\.0*$//;
    # $x = commas($x) unless (option_flag('nc'));
    if not no_commas:
        x = "{:,}".format(x)
    x = re.sub('\.0*$', '', str(x))

    return x




def fmt_datetime(dt):
    # my($dt) = shift;
    if not dt:
        return None

    # $dt = ~ s /-\d\d$//;
    dt = re.sub('-\d\d$', '', dt)
    # $dt =~ s/ /@/;
    dt = re.sub(' ', '@', dt)
    return dt




def fmt_name(first_name, middle_name, last_name):
    # my($first_name, $middle_name, $last_name) = @_;
    name = "{}, {}".format(last_name, first_name)
    if middle_name:
        name += " {}".format(middle_name)
    return name




def is_admin_func(config, user):
    is_admin_local = 0

    for admin in config["admin_names"]:
        if user == admin:
            is_admin_local = 1
            break
    return is_admin_local




def is_authorized(options, config, command_line):
    # Check if the application is authorized.
    # Add the user's name and other information to be logged as parameters to the auth_test call.
    # The extra parameters are ignored by auth_test and are just put into the log file on the database host.
    uid = os.environ.get('LOGNAME')
    epoch_time = int(time.time())
    hostname = socket.gethostname()

    # construct a rest url and fetch it
    url = "{}/xdusage/auth_test?USER={}&TIME={}&HOST={}&COMMAND_LINE={}".format(
        config["rest_url"], uid,
        urllib.parse.quote(str(epoch_time)),
        urllib.parse.quote(hostname),
        urllib.parse.quote(command_line)
    )

    if options.debug:
      print(url)

    # using LWP since it's available by default in most cases
    ua = urllib.request.Request(
        url,
        data=None,
        headers={
            'XA-AGENT': 'xdusage',
            'XA-RESOURCE': config["api_id"],
            'XA-API-KEY': config["api_key"]
        }
    )

    resp = None
    try:
      resp = urllib.request.urlopen(ua)
    except urllib.error.HTTPError as h:
      response = None
    # print('is authorized = {} {}'.format(url, resp.read().decode('utf-8')))

    if resp is None or resp.getcode() != 200:
        if is_root:
            message = "This script needs to be authorized with the XDCDB-API. \nAn API-KEY already exists in the " \
                      "configuration file ({}). \nIf you still have the HASH that was generated with this key \nyou " \
                      "can use it to register accessusage with the API. \nOtherwise, you will need to enter the new " \
                      "API_KEY into the configuration file. \nIn either case, send the following e-mail to " \
                      "help@xsede.org to register with the hash and key. \nSubject: ACDB API-KEY installation " \
                      "request \nPlease install the following HASH for agent xdusage on resource '{}'. \n<Replace " \
                      "this with the HASH you are using>\n".format(config["conf_file"], config["api_id"])
            sys.stderr.write(message)
        else:
            sys.stderr.write(
                "accessusage is not authorized to query the XDCDB-API.\nPlease contact your system administrator.\n")

        # Show full error message in case it is something other than authorization.
        if resp is not None:
            print("Failure: {} returned erroneous status: {}".format(url, resp.read().decode('utf-8')))
        sys.exit()




def json_get(options, config, url):
    # perform a request to a URL that returns JSON
    # returns JSON if successful
    # dies if there's an error, printing diagnostic information to
    # stderr.
    # error is:  non-200 result code, or result is not JSON.
    # using LWP since it's available by default in most cases

    if options.debug:
        print(url)

    ua = urllib.request.Request(
        url,
        headers={
            'XA-AGENT': 'xdusage',
            'XA-RESOURCE': config["api_id"],
            'XA-API-KEY': config["api_key"]
        }
    )

    try:
        resp = urllib.request.urlopen(ua)
    except urllib.error.HTTPError as h:
        print('Error = {}, Response body = {}'.format(h, h.read().decode()))
        sys.exit()

    # check for bad response code here
    if resp.getcode() != 200:
        print("Failure: {} returned erroneous status: {}".format(url, resp.read().decode('utf-8')))
        sys.exit()
    # do stuff with the body
    try:
        data = resp.read()
        encoding = resp.info().get_content_charset('utf-8')
        json_data = json.loads(data.decode(encoding))
    except ValueError:
        # not json? this is fatal too.
        print("Failure: {} returned non-JSON output: {}".format(url, resp.read().decode('utf-8')))
        sys.exit()
    # every response must contain a 'result' field.
    try:
        json_data['result']
    except KeyError:
        print("Failure: {} returned invalid JSON (missing result):  {}".format(url, resp.read().decode('utf-8')))
        sys.exit()
    return json_data




def run_command_line(cmd):
    try:
        # output = subprocess.check_output(cmd, shell=True)
        output = os.popen(cmd).read()
        # print('raw output = {}'.format(output))
        # cmd = cmd.split()
        # output = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        # output = subprocess.Popen(cmd, shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        #                           stderr=subprocess.PIPE).communicate(input=b'password\n')
        if len(output) == 0:
            result = []
        else:
            result = str(output).strip().split('\n')
        # print('result = {}'.format(result))
    except Exception as e:
        print("[-] run cmd = {} error = {}".format(cmd, e))
        sys.exit()

    return result




def setup_conf(config_filename):
    # Allow a root user to create and setup the missing configuration file.
    # Check that user accessusage exists, or prompt the admin to create it.
    check_user()

    # Create the empty configuration file in /etc.
    hostname = socket.gethostname()
    local_conf_file = "/etc/{}".format(config_filename)
    try:
        open_mode = 0o640
        con_fd = os.open(local_conf_file, os.O_WRONLY | os.O_CREAT, open_mode)
    except OSError:
        print("Could not open/write file, {}".format(local_conf_file))
        sys.exit()

    os.write(con_fd, str.encode("# Select an XDCDB ResourceName from "
                                "https://info.xsede.org/wh1/warehouse-views/v1/resources-xdcdb-active/?format=html"
                                ";sort=ResourceID\n"))
    os.write(con_fd, str.encode("# They are stored as \"ResourceID\" on the output from that page.\n"))
    os.write(con_fd, str.encode("# This is the resource that usage will be reported on by default.\n"))
    os.write(con_fd, str.encode("resource_name     = <YOUR_XDCDB_RESOURCE_NAME>\n\n"))
    os.write(con_fd, str.encode("api_id            = {}\n\n".format(hostname)))
    os.write(con_fd, str.encode("# Instructions for generating the API key and hash and for getting the has "
                                "configured in the API are at:\n"))
    os.write(con_fd, str.encode("#     https://xsede-xdcdb-api.xsede.org/\n"))
    os.write(con_fd, str.encode("# Click on the \"Generate API-KEY\" link and follow the instructions.\n"))
    os.write(con_fd, str.encode("api_key           = <YOUR_API_KEY>\n\n"))
    os.write(con_fd, str.encode("rest_url_base     = https://xsede-xdcdb-api.xsede.org/\n\n"))
    os.write(con_fd, str.encode("# List the login name of admins who can impersonate other users; one per line.\n"))
    os.write(con_fd, str.encode("# admin_name = fabio\n"))
    try:
        os.close(con_fd)
    except OSError:
        print("Could not close file, {}".format(local_conf_file))
        sys.exit()

    # Change its ownership to root/accessusage
    uid = pwd.getpwnam("root").pw_uid
    gid = grp.getgrnam("accessusage").gr_gid

    try:
        os.chown(local_conf_file, uid, gid)
    except OSError:
        print("Could not change the ownership, {}".format(local_conf_file))
        sys.exit()

    print(
        "\nA configuration file has been created at '{}'.\nFollow the instructions in the file to finish the "
        "configuration process.".format(local_conf_file)
    )
    sys.exit()




def show_amt(label, amt, no_commas):
    # my($label, $amt) = @_;
    if amt:
        amt = fmt_amount(amt, no_commas)
        print(" {}={}".format(label, amt), end='')




def show_value(label, value):
    # my($label, $value) = @_;
    if value:
        print(" {}={}".format(label, value), end='')

