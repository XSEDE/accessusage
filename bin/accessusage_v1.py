import argparse
import csv
import logging
import sys
import json
from time import asctime
from os import environ, makedirs, removedirs, path, listdir, getuid
import pwd, grp, stat
import os
import subprocess
import re
import time
import socket
import urllib.parse
from urllib.request import urlopen, Request
from urllib.error import HTTPError
# from datetime import datetime
import datetime

XDUSAGE_CONFIG_FILE = "accessusage_v1.conf"
APIKEY = None
APIID = None
resource = None
admin_names = []
conf_file = None
rest_url = None
command_line = None

me = None
install_dir = None
is_root = None
user = None
plist = []
resources = []
users = []
sdate = None
edate = None
edate2 = None
today = None
options = None


def get_enddate():
    """
    # return a suitable end date in UnixDate form
    # uses edate2 if provided, otherwise today + 1 day
    #
    # needed since REST API requires an end date and
    # end date is an optional argument.
    :return:
    """

    if not edate2:
        new_edate = datetime.date.today() + datetime.timedelta(days=1)
        return new_edate.strftime("%Y-%m-%d")
    else:
        return edate2


def get_usage_by_dates(account_id, resource_id, person_id=None):
    """
    # return a hashref of usage info given account_id, resource_id,
    # and bounded by date
    # optionally filtered by person_id
    :return:
    """
    # my($account_id, $resource_id, $person_id) = @_;

    # construct a rest url and fetch it
    # don't forget to uri escape these things in case one has funny
    # characters
    url = "{}/xdusage/v1/usage/by_dates/{}/{}/{}/{}".format(
        rest_url, account_id, resource_id,
        urllib.parse.quote(sdate),
        urllib.parse.quote(get_enddate()))

    if person_id:
        url += "?person_id={}".format(person_id)

    result = json_get(url)

    # caller expects just a hashref
    if len(result['result']) < 1:
        return {}

    return result['result'][0]


def get_counts_by_dates(account_id, resource_id, person_id=None):
    """
    # return a string of credit/debit counts by type for a given account_id
    # and resource_id, bounded by dates
    # optionally filtered by person_id
    # format is space-delmited, type=count[ ...]
    :param account_id:
    :param resource_id:
    :param person_id:
    :return:
    """
    # my($account_id, $resource_id, $person_id) = @_;

    # construct a rest url and fetch it
    # don't forget to uri escape these things in case one has funny
    # characters
    url = "{}/xdusage/v1/counts/by_dates/{}/{}/{}/{}".format(
        rest_url, account_id, resource_id,
        urllib.parse.quote(sdate),
        urllib.parse.quote(get_enddate()))

    if person_id:
        url += "?person_id={}".format(person_id)

    result = json_get(url)

    # munge into a string according to some weird rules
    # original code will lowercase a type name if person_id is set and
    # evaluates to true... huh?  just emulating the same behavior.
    j = 0
    # my(@counts,$type,$n);
    type1 = None
    n = None
    counts = []
    lowercase = 1 if person_id else 0
    for x in result['result']:
        type1 = x['type']
        n = x['n']
        if type1 == 'job':
            j = n
        else:
            if type1 != 'storage':
                type1 += 's'
            if not lowercase:
                type1 = type1[0].upper() + type1[1:]
            counts.append("{}={}".format(type1, n))

    if lowercase:
        type1 = 'jobs'
    else:
        type1 = 'Jobs'

    # unshift @counts, "$type=$j";
    counts.insert(0, "{}={}".format(type1, j))

    return " ".join(counts)


def get_allocation(account_id, resource_id, previous):
    """
    # return curent allocation info for account_id on resource_id
    # returns previous allocation info if 3rd argument evaluates to true.
    :return:
    """

    # my($account_id, $resource_id, $previous) = @_;

    prevstr = "current"
    if previous:
        prevstr = "previous"

    # construct a rest url and fetch it
    # don't forget to escape input...
    url = "{}/xdusage/v1/allocations/{}/{}/{}".format(
        rest_url, account_id, resource_id, prevstr)
    result = json_get(url)
    # print('get allocation = {} {}'.format(url, result))
    if len(result['result']) == 0:
        return {}
    # the caller checks for undef, so we're good to go.
    # note that the result is NOT an array this time.
    return result['result']


def get_counts_on_allocation(allocation_id, person_id=None):
    """
    # return a string of credit/debit counts by type for a given allocation_id
    # optionally filtered by person_id
    # format is space-delmited, type=count[ ...]
    :return:
    """

    # my($allocation_id, $person_id) = @_;

    # construct a rest url and fetch it
    # don't forget to uri escape these things in case one has funny
    # characters
    url = "{}/xdusage/v1/counts/by_allocation/{}".format(
        rest_url, allocation_id)
    if person_id:
        url += "?person_id={}".format(person_id)

    result = json_get(url)

    # munge into a string according to some weird rules
    # original code will lowercase a type name if person_id is set and
    # evaluates to true... huh?  just emulating the same behavior.
    j = 0
    # my(@counts,$type,$n);
    counts = []
    type1 = None
    n = None

    lowercase = 1 if person_id else 0
    for x in result['result']:
        type1 = x['type']
        n = x['n']
        if type1 == 'job':
            j = n
        else:
            if type1 != 'storage':
                type1 += 's'
            if not lowercase:
                type1 = type1[0].upper() + type1[1:]
            counts.append("{}={}".format(type1, n))
    if lowercase:
        type1 = 'jobs'
    else:
        type1 = 'Jobs'

    # unshift @counts, "$type=$j";
    counts.insert(0, "{}={}".format(type1, j))

    return " ".join(counts)


def get_usage_on_allocation(allocation_id, person_id):
    """
    # returns number (float) of SUs used by a given person_id on allocation_id
    :return:
    """
    # my($allocation_id, $person_id) = @_;

    # construct a rest url and fetch it
    # don't forget to uri escape these things in case one has funny
    # characters
    url = "{}/xdusage/v1/usage/by_allocation/{}/{}".format(
        rest_url, allocation_id, person_id)
    result = json_get(url)
    num_su = 0.0
    try:
        num_su = float(result['result'][0]['su_used'])
    except KeyError:
        num_su = 0.0

    return num_su


def get_jv_by_dates(account_id, resource_id, person_id):
    """
    # return list of hashref of job info for a given account_id, resource_id,
    # and person_id bounded by dates
    :return:
    """

    # my($account_id, $resource_id, $person_id) = @_;

    # construct a rest url and fetch it
    # don't forget to uri escape these things in case one has funny
    # characters
    url = "{}/xdusage/v1/jobs/by_dates/{}/{}/{}/{}/{}".format(
        rest_url, account_id, resource_id, person_id,
        urllib.parse.quote(sdate),
        urllib.parse.quote(get_enddate()))
    # url = "{}/xdusage/v1/jobs/by_allocation/41004/55".format(rest_url)
    result = json_get(url)

    # caller expects a list
    if len(result['result']) < 1:
        return []

    return result['result']


def get_cdv_by_dates(account_id, resource_id, person_id):
    """
    # return a list of hashref of credit/debit info given account_id, resource_id,
    # person_id bounded by dates
    :param account_id: 
    :param resource_id: 
    :param person_id: 
    :return: 
    """
    # my($account_id, $resource_id, $person_id) = @_;

    # construct a rest url and fetch it
    # don't forget to uri escape these things in case one has funny
    # characters
    url = "{}/xdusage/v1/credits_debits/by_dates/{}/{}/{}/{}/{}".format(
        rest_url, account_id, resource_id, person_id,
        urllib.parse.quote(sdate),
        urllib.parse.quote(get_enddate()))
    result = json_get(url)

    # caller expects a list
    if len(result['result']) < 1:
        return []

    return result['result']


def get_jv_on_allocation(allocation_id, person_id):
    """
    # return list of hashref of job info for a given allocation_id and person_id
    :return:
    """

    # my($allocation_id, $person_id) = @_;

    # construct a rest url and fetch it
    # don't forget to uri escape these things in case one has funny
    # characters
    url = "{}/xdusage/v1/jobs/by_allocation/{}/{}".format(
        rest_url, allocation_id, person_id)
    result = json_get(url)

    # caller expects a list
    if len(result['result']) < 1:
        return []

    return result['result']


def get_cdv_on_allocation(allocation_id, person_id):
    """
    # return list of hashref of credits/debits on allocation_id by person_id
    :param allocation_id:
    :param person_id:
    :return:
    """

    # my($allocation_id, $person_id) = @_;

    # construct a rest url and fetch it
    # don't forget to uri escape these things in case one has funny
    # characters
    url = "{}/xdusage/v1/credits_debits/by_allocation/{}/{}".format(
        rest_url, allocation_id, person_id)
    result = json_get(url)

    # caller expects a list
    if len(result['result']) < 1:
        return []
    return result['result']


def get_job_attributes(job_id):
    """
    # return list of hashref of job attributes for a given
    # job id.
    :param job_id:
    :return:
    """

    # my($job_id) = shift;

    # job_id = urllib.parse.quote(job_id)

    url = "{}/xdusage/v1/jobs/attributes/{}".format(
        rest_url,
        job_id)
    result = json_get(url)

    # caller checks for undef
    return result['result']


def show_project(project):
    global sdate
    global edate
    global edate2

    # my(@a, $a, $w, $name);
    # my($x, $amt, $alloc);
    # my($s, $e);
    # my($username);
    # my(@j, @cd, $job_id, $id);
    # my($ux, $any, $is_pi);
    # my($sql, @jav, $jav);
    alloc = None
    j = []
    cd = []

    a = get_accounts(project)

    # return 0 unless (@a);
    if len(a) < 1:
        return 0

    if sdate or edate2:
        x = get_usage_by_dates(project['account_id'], project['resource_id'])
        if x['su_used']:
            amt = 1
        else:
            amt = 0
        if amt == 0 and options.zero_projects:
            return 0

        # $s = $x->{start_date} || $sdate;
        # $e = $x->{end_date} || $edate;
        s = sdate
        e = edate
        # $s = $sdate || $x->{start_date};
        # $e = $edate || $x->{end_date};

        x = get_counts_by_dates(project['account_id'], project['resource_id'])
        ux = "Usage Period: {}{}\n Usage={} {}".format(
            "{}/".format(s) if s else "thru ",
            "{}".format(e) if e else today,
            fmt_amount(amt),
            x)
    else:
        alloc = get_allocation(project['account_id'], project['resource_id'], options.previous_allocation)
        if len(alloc) == 0:
            return 0
        amt = alloc['su_used']
        if amt == 0 and options.zero_projects:
            return 0
        x = get_counts_on_allocation(alloc['allocation_id'])
        ux = "Allocation: {}/{}\n Total={} Remaining={} Usage={} {}".format(
            alloc['alloc_start'],
            alloc['alloc_end'],
            fmt_amount(float(alloc['su_allocated'])),
            fmt_amount(float(alloc['su_remaining'])),
            fmt_amount(float(amt)),
            x)
    any1 = 0
    for a1 in a:
        is_pi = a1['is_pi']
        w = "PI" if is_pi else "  "
        username = a1['portal_username']
        name = fmt_name(a1['first_name'], a1['middle_name'], a1['last_name'])

        if sdate or edate2:
            x = get_usage_by_dates(project['account_id'], project['resource_id'],
                                   person_id=a1['person_id'])
            amt = x['su_used']
            x = get_counts_by_dates(project['account_id'], project['resource_id'],
                                    person_id=a1['person_id'])
            if options.jobs:
                j = get_jv_by_dates(project['account_id'], project['resource_id'], a1['person_id'])
                cd = get_cdv_by_dates(project['account_id'], project['resource_id'], a1['person_id'])
        else:
            amt = get_usage_on_allocation(alloc['allocation_id'], a1['person_id'])
            x = get_counts_on_allocation(alloc['allocation_id'], person_id=a1['person_id'])
            if options.jobs:
                j = get_jv_on_allocation(alloc['allocation_id'], a1['person_id'])
                cd = get_cdv_on_allocation(alloc['allocation_id'], a1['person_id'])

        if amt == 0 and options.zero_accounts:
            continue
        if not any1:
            print("Project: {}".format(project['charge_number']), end='')
            print("/{}".format(project['resource_name']), end='')
            if project['proj_state'] != 'active':
                print(" status=inactive", end='')
            print("")
            print("PI: {}".format(
                fmt_name(project['pi_first_name'], project['pi_middle_name'], project['pi_last_name'])))
            print("{}".format(ux))
            any1 = 1

        print(" {} {}".format(w, name), end='')
        if username:
            print(" portal={}".format(username), end='')
        if a1['acct_state'] != 'active':
            print(" status=inactive", end='')
        print(" usage={} {}".format(fmt_amount(amt if amt else 0), x))

        for x in j:
            print("      job", end='')
            id = x['local_jobid']
            show_value("id", id)
            show_value("jobname", x['jobname'])
            show_value("resource", x['job_resource'])
            show_value("submit", fmt_datetime(x['submit_time']))
            show_value("start", fmt_datetime(x['start_time']))
            show_value("end", fmt_datetime(x['end_time']))
            show_amt("memory", x['memory'])
            show_value("nodecount", x['nodecount'])
            show_value("processors", x['processors'])
            show_value("queue", x['queue'])
            show_amt("charge", x['adjusted_charge'])
            print("")
            if options.job_attributes:
                job_id = x['job_id']
                jav = get_job_attributes(job_id)
                for jav1 in jav:
                    print("        job-attr", end='')
                    show_value("id", id)
                    show_value("name", jav1['name'])
                    show_value("value", jav1['value'])
                    print("")

        for x in cd:
            print("     {}".format(x['type']), end='')
            print(" resource={}".format(x['site_resource_name']), end='')
            print(" date={}".format(fmt_datetime(x['charge_date'])), end='')
            print(" amount={}".format(fmt_amount(abs(x['amount']))), end='')
            print("")

    if any1:
        print("")
    return any1


def show_amt(label, amt):
    # my($label, $amt) = @_;
    if amt:
        amt = fmt_amount(amt)
    else:
        amt = None
    print(" {}={}".format(label, amt), end='')


def show_value(label, value):
    # my($label, $value) = @_;
    if not value:
        value = None
    print(" {}={}".format(label, value), end='')


def fmt_name(first_name, middle_name, last_name):
    # my($first_name, $middle_name, $last_name) = @_;
    name = "{} {}".format(last_name, first_name)
    if middle_name:
        name += " {}".format(middle_name)
    return name


def fmt_datetime(dt):
    # my($dt) = shift;
    if not dt:
        return None

    # $dt = ~ s /-\d\d$//;
    dt = re.sub('-\d\d', '', dt)
    # $dt =~ s/ /@/;
    dt = re.sub(' ', '@', dt)
    return dt


def get_dates():
    # my($date);
    # my($sdate, $edate, $edate2);
    local_today = datetime.datetime.today()
    local_sdate = None
    local_edate = None
    local_edate2 = None
    local_date = options.start_date
    if local_date:
        local_sdate = datetime.datetime.strptime(local_date, '%Y-%m-%d')
        if not local_sdate:
            error("{} -- not a valid date".format(local_date))
    if local_sdate and (local_sdate > local_today):
        error("The start date (-s) can't be in the future.")

    local_date = options.end_date
    if local_date:
        if not local_sdate:
            error("The end date option (-e) requires that a start date (-s) be specified.")
        local_edate = datetime.datetime.strptime(local_date, '%Y-%m-%d')
        if not local_edate:
            error("{} -- not a valid date".format(local_date))
        local_edate2 = local_edate + datetime.timedelta(days=1)

    if local_sdate:
        local_sdate = local_sdate.strftime("%Y-%m-%d")
    if local_edate:
        local_edate = local_edate.strftime("%Y-%m-%d")
    if local_edate2:
        local_edate2 = local_edate2.strftime("%Y-%m-%d")

    if local_sdate and local_edate and (local_sdate > local_edate):
        error("The end date (-e) can't precede the start date (-s).")

    return local_sdate, local_edate, local_edate2


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


def check_sudo():
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
                  "correctly:\t\nDefault!{}/accessusage runas_default=accessusage\t\nDefault!{}/accessusage " \
                  "env_keep=\"USER\"\t\nALL  ALL=(accessusage) NOPASSWD:{}/accessusage\n".format(install_dir, install_dir,
                                                                                     install_dir)
            sys.stderr.write(msg)
            sys.exit()
        else:
            print("Please contact your system administrator.")
            sys.exit()


def setup_conf():
    # Allow a root user to create and setup the missing configuration file.
    # Check that user accessusage exists, or prompt the admin to create it.
    try:
        pwd.getpwnam("accessusage")
    except KeyError:
        sys.stderr.write(
            "Required user 'accessusage' does not exist on this system.\nCreate the user and run this script again.\n")
        sys.exit()

    # Create the empty configuration file in /etc.
    hostname = socket.gethostname()
    local_conf_file = "/etc/{}".format(XDUSAGE_CONFIG_FILE)
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


def fmt_amount(amt):
    # my($amt) = shift;

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
    x = re.sub('\.0*', '', str(x))
    # $x = commas($x) unless (option_flag('nc'));
    if not options.no_commas:
        x = commas(x)

    return x


def commas(x):
    """
    # I got this from http://forrst.com/posts/Numbers_with_Commas_Separating_the_Thousands_Pe-CLe
    :param x:
    :return:
    """
    # my($x) = shift;
    neg = 0
    # if ($x =~ / ^ - /)
    if re.match('^-', x):
        neg = 1
        # x = ~ s / ^ - //;
        x = re.sub('^-', '', x)

    # $x =~ s/\G(\d{1,3})(?=(?:\d\d\d)+(?:\.|$))/$1,/g;
    # x = re.sub('(\d{1,3})(?=(?:\d\d\d)+(?:\.|$))', '$1,', x)
    x = format(int(x), ',d')
    # $x = "-" . "$x" if $neg;
    if neg:
        x = "-{}".format(x)

    return x


def error(msg):
    print("{}: {}".format(me, msg))
    sys.exit()


def config_error(error_message, num_parameters=1):
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
                                                                                                   conf_file)
        print(message)
        sys.exit()
    else:
        error("There is a problem with the configuration file.\nPlease contact your system administrator.")


def is_authorized():
    # Check if the application is authorized.
    # Add the user's name and other information to be logged as parameters to the auth_test call.
    # The extra parameters are ignored by auth_test and are just put into the log file on the database host.
    uid = os.environ.get('LOGNAME')
    epoch_time = int(time.time())
    hostname = socket.gethostname()

    # construct a rest url and fetch it
    url = "{}/xdusage/auth_test?USER={}&TIME={}&HOST={}&COMMAND_LINE={}".format(
        rest_url, uid,
        urllib.parse.quote(str(epoch_time)),
        urllib.parse.quote(hostname),
        urllib.parse.quote(command_line)
    )

    # using LWP since it's available by default in most cases
    ua = Request(
        url,
        data=None,
        headers={
            'XA-AGENT': 'xdusage',
            'XA-RESOURCE': APIID,
            'XA-API-KEY': APIKEY
        }
    )

    resp = urlopen(ua)
    # print('is authorized = {} {}'.format(url, resp.read().decode('utf-8')))

    if resp.getcode() != 200:
        if is_root:
            message = "This script needs to be authorized with the XDCDB-API. \nAn API-KEY already exists in the " \
                      "configuration file ({}). \nIf you still have the HASH that was generated with this key \nyou " \
                      "can use it to register xdusage with the API. \nOtherwise, you will need to enter the new " \
                      "API_KEY into the configuration file. \nIn either case, send the following e-mail to " \
                      "help\@xsede.org to register with the hash and key. \nSubject: XDCDB API-KEY installation " \
                      "request \nPlease install the following HASH for agent xdusage on resource '{}'. \n<Replace " \
                      "this with the HASH you are using>".format(conf_file, APIID)
            sys.stderr.write(message)
        else:
            sys.stderr.write(
                "xdusage is not authorized to query the XDCDB-API.\nPlease contact your system administrator.\n")

        # Show full error message in case it is something other than authorization.
        print("Failure: {} returned erroneous status: {}".format(url, resp.read().decode('utf-8')))
        sys.exit()


def json_get(url):
    # perform a request to a URL that returns JSON
    # returns JSON if successful
    # dies if there's an error, printing diagnostic information to
    # stderr.
    # error is:  non-200 result code, or result is not JSON.
    # using LWP since it's available by default in most cases
    ua = Request(
        url,
        headers={
            'XA-AGENT': 'xdusage',
            'XA-RESOURCE': APIID,
            'XA-API-KEY': APIKEY
        }
    )

    try:
        resp = urlopen(ua)
    except HTTPError as h:
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


def check_resource(local_resource):
    # Check if the named resource is in the active XSEDE resource list.
    # construct a rest url and fetch it
    # don't forget to uri escape these things in case one has funny
    # characters
    url = "{}/xdusage/v1/resources/{}".format(rest_url, urllib.parse.quote(local_resource))
    result = json_get(url)

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


def get_user(username, portal=0):
    """
    # returns a list of hashref of user info for a given username at a given resource
    # resource defaults to config param resource_name; if second arg evaluates
    # to true, use the portal as the resource.
    :param username:
    :param portal:
    :return:
    """

    rs = 'portal.teragrid' if portal else resource

    # construct a rest url and fetch it
    # don't forget to uri escape these things in case one has funny
    # characters

    url = "{}/xdusage/v1/people/by_username/{}/{}".format(rest_url,
                                                          urllib.parse.quote(rs),
                                                          urllib.parse.quote(username))
    result = json_get(url)

    # there should be only one row returned here...
    if len(result['result']) > 1:
        print("Multiple user records for user {} on resource {}".format(username, rs))
        sys.exit()

    return result['result'][0] if len(result['result']) == 1 else None


def get_users_by_last_name(name):
    """
    # returns a list of hashrefs of user info for all users with the
    # given last name.
    :param name:
    :return:
    """
    # construct a rest url and fetch it
    # don't forget to uri escape these things in case one has funny
    # characters
    url = "{}/xdusage/v1/people/by_lastname/{}".format(rest_url, urllib.parse.quote(name))
    result = json_get(url)

    # conveniently, the result is already in the form the caller expects.
    return result['result']


def get_users():
    """
    # returns a list of hashrefs of user info for every user
    # described by the -u and -up arguments.
    :return:
    """
    user_list = []
    # my($name);
    # my(@u);

    for username in options.usernames:
        u = []
        g_user = get_user(username)
        g_user_lname = get_users_by_last_name(username)
        if g_user:
            u.append(g_user)
        if len(g_user_lname) > 0:
            u.extend(g_user_lname)
        if len(u) == 0:
            error("user {} not found".format(username))
        user_list.extend(u)

    for username in options.portal_usernames:
        u = get_user(username, portal=1)
        if u:
            user_list.append(u)
        else:
            error("user {} not found".format(username))

    return user_list


def get_accounts(project):
    """
    # return list of hashref of account info on a given project
    # optionally filtered by username list and active-only
    :return:
    """

    # my($project) = shift;
    # if not user:
    #     return []
    person_id = user['person_id']
    local_is_su = user['is_su']

    urlparams = []

    # filter by personid(s)
    if len(users) > 0 or (not options.all_accounts) or local_is_su:
        if len(users) > 0:
            p_ids = []
            for u in users:
                p_ids.append(u['person_id'])
            urlparams.append("person_id={}".format(urllib.parse.quote(','.join(map(str, p_ids)))))
        else:
            urlparams.append("person_id={}".format(person_id))

    # filter by active accounts
    if options.inactive_accounts:
        urlparams.append("active_only")

    # construct a rest url and fetch it
    # input has already been escaped
    url = "{}/xdusage/v1/accounts/{}/{}?{}".format(rest_url,
                                                   project['account_id'],
                                                   project['resource_id'], '&'.join(urlparams))

    result = json_get(url)

    # caller checks for undef
    return result['result']


def get_resources():
    # return a list of resource IDs (numeric) described by -r arguments.
    global options
    resource_list = []
    # my($name, $r);
    # my($pat);
    # my($any);
    # my($url);
    # print('options resources = {}'.format(options.resources))
    for name in options.resources:
        # since nobody remembers the full name, do a search based on
        # the subcomponents provided
        pat = name
        if '.' not in name:
            pat = "{}.%".format(name)

        # create a rest url and fetch
        url = "{}/xdusage/v1/resources/{}".format(rest_url, urllib.parse.quote(pat))
        result = json_get(url)
        # print('get resources = {} result = {}'.format(pat, result))
        any_r = 0
        for r in result['result']:
            resource_list.append(r['resource_id'])
            any_r = 1
        if not any_r:
            error("{} - resource not found".format(name))

    return resource_list


def get_projects():
    """
    return a list of hashrefs of project info described by
    -p (project list), -ip (filter active) args
    restricted to non-expired projects associated with
    current user by default
    :return:
    """
    if not user:
        return []

    person_id = user['person_id']
    is_su = user['is_su']

    urlparams = []

    # filter by project list?
    # (grant number, charge number)
    if len(plist) > 0:
        l_plist = []
        for p in plist:
            l_plist.append(p.lower())
        urlparams.append("projects={}".format(urllib.parse.quote(','.join(l_plist))))
    # If not filtering by project list, show all non-expired
    else:
        urlparams.append("not_expired")

    # non-su users are filtered by person_id
    # so they can't see someone else's project info
    if not is_su:
        urlparams.append("person_id={}".format(person_id))

    # filter by active
    if options.inactive_projects:
        urlparams.append("active_only")

    # filter by resources
    if len(resources) > 0:
        urlparams.append("resource_id={}".format(urllib.parse.quote(','.join(map(str, resources)))))

    # construct a rest url and fetch it
    # input has already been escaped
    url = "{}/xdusage/v1/projects?{}".format(rest_url,
                                             '&'.join(urlparams))
    result = json_get(url)

    # return an empty array if no results
    if len(result['result']) < 1:
        return []

    return result['result']


def is_admin_func(user):
    is_admin_local = 0

    for admin in admin_names:
        if user == admin:
            is_admin_local = 1
            break
    return is_admin_local


def check_config():
    global conf_file
    global APIKEY
    global APIID
    global resource
    global rest_url

    # load the various settings from a configuration file
    # (api_id, api_key, rest_url_base, resource_name, admin_name)
    # file is simple key=value, ignore lines that start with #
    # list of possible config file locations
    conf_file_list = ['/etc/{}'.format(XDUSAGE_CONFIG_FILE),
                      '/var/secrets/{}'.format(XDUSAGE_CONFIG_FILE),
                      "{}/../etc/{}".format(install_dir, XDUSAGE_CONFIG_FILE),
                      ]

    # use the first one found.
    for c in conf_file_list:
        if os.path.isfile(c) and os.access(c, os.R_OK):
            conf_file = c
            break

    # The configuration file doesn't exist.
    # Give the administrator directions to set up the script.
    if not conf_file:
        if is_root:
            sys.stderr.write("The configuration file could not be located in:\n")
            sys.stderr.write("\n  ".join(conf_file_list))
            sys.stderr.write("\n")
            setup_conf()
        else:
            print("Unable to find the configuration file.\nPlease contact your system administrator.")
            sys.exit()

    # read in config file
    try:
        con_fd = open(conf_file, 'r')
    except OSError:
        print("Could not open/read file, {}".format(conf_file))
        sys.exit()

    # Check ownership of the configuration file is root/accessusage.
    sb = os.lstat(conf_file)
    root_uid = pwd.getpwnam("root").pw_uid
    # print("sb uid = {} root uid = {}".format(sb.st_uid, root_uid))
    if sb.st_uid != root_uid:
        config_error("Configuration file '{}' must be owned by user 'root'.".format(conf_file), num_parameters=2)
    try:
        xdusage_gid = grp.getgrnam("accessusage").gr_gid
    except KeyError:
        xdusage_gid = -1
    # print("sb gid = {} xdusage gid = {}".format(sb.st_gid, xdusage_gid))
    if sb.st_gid != xdusage_gid:
        config_error("Configuration file '{}' must be owned by group 'accessusage'.".format(conf_file), num_parameters=2)

    # Check that the configuration file has the correct permissions.
    # mode = stat.S_IMODE(sb.st_mode)
    mode = oct(sb.st_mode)[-3:]
    # print('mode = {} sb mode = {}'.format(mode, sb))
    # print("\nFile permission mask (in octal):", oct(sb.st_mode)[-3:])
    if mode != '640':
        message = "Configuration file '{}' has permissions '{}', it must have permissions '0640'.".format(conf_file, mode)
        config_error(message, num_parameters=2)

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
                sys.stderr.write("Ignoring cruft in {}: '{}'\n".format(conf_file, line))
            continue

        key = matched.group(1)
        val = matched.group(2)
        # print('key = {} val = {}'.format(key, val))
        key = re.sub(r'^\s*', '', key)
        key = re.sub(r'\s*', '', key)
        val = re.sub(r'^\s*', '', val)
        val = re.sub(r'\s*', '', val)

        if key == 'api_key':
            if APIKEY:
                config_error("Multiple 'api_key' values found.")
            APIKEY = val
        elif key == 'api_id':
            if APIID:
                config_error("Multiple 'api_id' values found.")
            APIID = val
        elif key == 'resource_name':
            if resource:
                config_error("Multiple 'resource_name' values found.")
            resource = val
        elif key == 'admin_name':
            admin_names.insert(0, val)
        elif key == 'rest_url_base':
            if rest_url:
                config_error("Multiple 'rest_url_base' values found.")
            rest_url = val
        else:
            if is_root:
                sys.stderr.write("Ignoring cruft in {}: '{}'\n".format(conf_file, line))

    try:
        con_fd.close()
    except OSError:
        print("Could not close file, {}".format(conf_file))
        sys.exit()

    # stop here if missing required values
    if not APIID:
        config_error("Unable to find the 'api_id' value.")
    if not APIKEY:
        config_error("Unable to find the 'api_key' value.")
    if not resource:
        config_error("Unable to find the 'resource_name' value.")
    if not rest_url:
        config_error("Unable to find the 'rest_url_base' value.")

    # Check if the key is authorized.
    is_authorized()

    # Check if the resource specified in the configuration file is valid.
    res = check_resource(resource)


def version():
    print("accessusage version {}".format('1.0'))
    exit(1)


def main(wrapper_options):
    global options
    global command_line
    global is_root
    global me
    global install_dir
    global today
    global user
    global resources
    global users
    global plist
    global sdate, edate, edate2

    # find out where this script is running from
    # eliminates the need to configure an install dir
    install_dir = path.dirname(path.abspath(__file__))
    # print('install dir = {}'.format(install_dir))
    me = sys.argv[0].split('/')[-1]
    # print('me = {}'.format(me))

    # Perl always has "." on the end of @INC, and it causes problems if the
    # xdinfo user can't read the current working directory.
    # no lib "." will remove . from @INC--safer than pop(@INC).
    # no lib ".";

    # Determine if the script is being run by root.
    # Root will be given setup instructions, if necessary, and
    # will be given directions to correct errors, where possible.
    # print('os uid = {} {}'.format(os.getuid(), pwd.getpwuid(os.getuid())[0]))
    is_root = (pwd.getpwuid(os.getuid())[0] == "root")
    # print('is root = {}'.format(is_root))
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
        check_sudo()
        logname = "root"
    elif 'SUDO_USER' not in os.environ:
        # Check that the sudoers file is set up correctly.
        check_sudo()

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

    # Check that the configuration file is set up and contains valid information.
    check_config()

    # get argument list
    options = wrapper_options


    # print('Version = {}'.format(options.version))
    if options.version:
        version()

    DEBUG = options.debug
    today = datetime.datetime.today().strftime('%Y-%m-%d')
    is_admin = is_admin_func(logname)

    # admins can set USER to something else and view their allocation
    xuser = os.getenv('USER') if is_admin and os.getenv('USER') else logname
    # print('today = {} is admin = {} xuser = {}'.format(today, is_admin, xuser))
    user = get_user(xuser)
    # test case
    # user = get_user('tbrecken', portal=1)
    # print('user = {}'.format(user))
    resources = get_resources()
    # print('resource list = {}'.format(resources))

    users = get_users()
    # print('user list = {}'.format(users))
    plist = options.projects
    # print('project list = {}'.format(plist))
    sdate, edate, edate2 = get_dates()
    # print("start date = {} end date = {} end date2 = {}".format(sdate, edate, edate2))
    projects = get_projects()
    # print('projects = {}'.format(len(projects)))
    any1 = 0
    for project in projects:
        if show_project(project):
            any1 = 1

    if any1 == 0:
        error("No projects and/or accounts found")
    sys.exit()


if __name__ == '__main__':
    main()
