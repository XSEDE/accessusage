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

file_path = os.path.abspath(__file__)
bin_path = os.path.split(file_path)[0]    # drop file name
accessusage_path = os.path.split(bin_path)[0]    # drop file name
sys.path.append(accessusage_path)
import util

config = None
DEBUG = False
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


def get_usage_by_dates(project_id, resource_id, person_id=None):
    """
    # return a hashref of usage info given project_id, resource_id,
    # and bounded by date
    # optionally filtered by person_id
    :return:
    """
    # my($project_id, $resource_id, $person_id) = @_;

    # construct a rest url and fetch it
    # don't forget to uri escape these things in case one has funny
    # characters
    url = "{}/xdusage/v2/usage/by_dates/{}/{}/{}/{}".format(
        rest_url, project_id, resource_id,
        urllib.parse.quote(sdate),
        urllib.parse.quote(get_enddate()))

    if person_id:
        url += "?person_id={}".format(person_id)

    result = util.json_get(options, config, url)

    # caller expects just a hashref
    if len(result['result']) < 1:
        return {}

    return result['result'][0]


def get_counts_by_dates(project_id, resource_id, person_id=None):
    """
    # return a string of credit/debit counts by type for a given project_id
    # and resource_id, bounded by dates
    # optionally filtered by person_id
    # format is space-delmited, type=count[ ...]
    :param account_id:
    :param resource_id:
    :param person_id:
    :return:
    """
    # my($project_id, $resource_id, $person_id) = @_;

    # construct a rest url and fetch it
    # don't forget to uri escape these things in case one has funny
    # characters
    url = "{}/xdusage/v2/counts/by_dates/{}/{}/{}/{}".format(
        rest_url, project_id, resource_id,
        urllib.parse.quote(sdate),
        urllib.parse.quote(get_enddate()))

    if person_id:
        url += "?person_id={}".format(person_id)

    result = util.json_get(options, config, url)

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


def get_request_resource(project_id, resource_id, previous):
    """
    # return current request_resource info for project_id on resource_id
    # returns previous request_resource info if 3rd argument evaluates to true.
    :return:
    """

    # my($account_id, $resource_id, $previous) = @_;

    prevstr = "current"
    if previous:
        prevstr = "previous"

    # construct a rest url and fetch it
    # don't forget to escape input...
    url = "{}/xdusage/v2/request_resource/{}/{}/{}".format(
        rest_url, prevstr, project_id, resource_id, )
    result = util.json_get(options, config, url)
    # print('get allocation = {} {}'.format(url, result))
    if len(result['result']) == 0:
        return {}
    # the caller checks for undef, so we're good to go.
    # note that the result is NOT an array this time.
    return result['result']


def get_counts_on_request_resource(request_resource_id, person_id=None):
    """
    # return a string of credit/debit counts by type for a given request_resource_id
    # optionally filtered by person_id
    # format is space-delmited, type=count[ ...]
    :return:
    """

    # my($request_resource_id, $person_id) = @_;

    # construct a rest url and fetch it
    # don't forget to uri escape these things in case one has funny
    # characters
    url = "{}/xdusage/v2/counts/by_request_resource/{}".format(
        rest_url, request_resource_id)
    if person_id:
        url += "?person_id={}".format(person_id)

    result = util.json_get(options, config, url)

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


def get_usage_on_request_resource(request_resource_id, person_id):
    """
    # returns number (float) of SUs used by a given person_id on request_resource_id
    :return:
    """
    # my($request_resource_id, $person_id) = @_;

    # construct a rest url and fetch it
    # don't forget to uri escape these things in case one has funny
    # characters
    url = "{}/xdusage/v2/usage/by_request_resource/{}".format(
        rest_url, request_resource_id)
    if person_id:
        url += "?person_id={}".format(person_id)

    result = util.json_get(options, config, url)
    num_su = 0.0
    try:
        num_su = float(result['result'][0]['su_used'])
    except (KeyError, TypeError) as e:
        num_su = 0.0

    return num_su


def get_jv_by_dates(project_id, resource_id, person_id):
    """
    # return list of hashref of job info for a given project_id, resource_id,
    # and person_id bounded by dates
    :return:
    """

    # my($project_id, $resource_id, $person_id) = @_;

    # construct a rest url and fetch it
    # don't forget to uri escape these things in case one has funny
    # characters
    url = "{}/xdusage/v2/jobs/by_dates/{}/{}/{}/{}".format(
        rest_url, project_id, resource_id,
        urllib.parse.quote(sdate),
        urllib.parse.quote(get_enddate()))
    if person_id:
        url += "?person_id={}".format(person_id)

    result = util.json_get(options, config, url)

    # caller expects a list
    if len(result['result']) < 1:
        return []

    return result['result']


def get_cdv_by_dates(project_id, resource_id, person_id):
    """
    # return a list of hashref of credit/debit info given project_id, resource_id,
    # person_id bounded by dates
    :param account_id: 
    :param resource_id: 
    :param person_id: 
    :return: 
    """
    # my($project_id, $resource_id, $person_id) = @_;

    # construct a rest url and fetch it
    # don't forget to uri escape these things in case one has funny
    # characters
    url = "{}/xdusage/v2/credits_debits/by_dates/{}/{}/{}/{}".format(
        rest_url, project_id, resource_id,
        urllib.parse.quote(sdate),
        urllib.parse.quote(get_enddate()))
    if person_id:
        url += "?person_id={}".format(person_id)

    result = util.json_get(options, config, url)

    # caller expects a list
    if len(result['result']) < 1:
        return []

    return result['result']


def get_jv_on_request_resource(request_resource_id, person_id):
    """
    # return list of hashref of job info for a given request_resource_id and person_id
    :return:
    """

    # my($request_resource_id, $person_id) = @_;

    # construct a rest url and fetch it
    # don't forget to uri escape these things in case one has funny
    # characters
    url = "{}/xdusage/v2/jobs/by_request_resource/{}".format(
        rest_url, request_resource_id)
    if person_id:
        url += "?person_id={}".format(person_id)
    result = util.json_get(options, config, url)

    # caller expects a list
    if len(result['result']) < 1:
        return []

    return result['result']


def get_cdv_on_request_resource(request_resource_id, person_id):
    """
    # return list of hashref of credits/debits on request_resource_id by person_id
    :param allocation_id:
    :param person_id:
    :return:
    """

    # my($request_resource_id, $person_id) = @_;

    # construct a rest url and fetch it
    # don't forget to uri escape these things in case one has funny
    # characters
    url = "{}/xdusage/v2/credits_debits/by_request_resource/{}".format(
        rest_url, request_resource_id)
    if person_id:
        url += "?person_id={}".format(person_id)
    result = util.json_get(options, config, url)

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

    url = "{}/xdusage/v2/jobs/attributes/{}".format(
        rest_url,
        job_id)
    result = util.json_get(options, config, url)

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
    rr = None
    j = []
    cd = []

    a = get_accounts(project)

    # return 0 unless (@a);
    if len(a) < 1:
        return 0

    if sdate or edate2:
        x = get_usage_by_dates(project['project_id'], project['resource_id'])
        if x['su_used']:
            amt = float(x['su_used'])
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

        x = get_counts_by_dates(project['project_id'], project['resource_id'])
        ux = "Usage Period: {}{}\n Usage={} {}".format(
            "{}/".format(s) if s else "thru ",
            "{}".format(e) if e else today,
            fmt_amount(amt),
            x)
    else:
        rr = get_request_resource(project['project_id'], project['resource_id'], options.previous_allocation)
        if len(rr) == 0:
            return 0
        try:
            if not rr['request_resource_id']:
                return 0
        except KeyError:
            return 0
        amt = float(rr['charges'])

        if amt == 0 and options.zero_projects:
            return 0
        x = get_counts_on_request_resource(rr['request_resource_id'])
        ux = "Allocation: {}/{}\n Total={} Remaining={} Usage={} {}".format(
            rr['start_date'],
            rr['end_date'],
            fmt_amount(float(rr['allocation'])),
            fmt_amount(float(rr['balance'])),
            fmt_amount(amt),
            x)
    any1 = 0
    for a1 in a:
        is_pi = a1['is_pi']
        w = "PI" if is_pi else "  "
        username = a1['portal_username']
        name = fmt_name(a1['first_name'], a1['middle_name'], a1['last_name'])

        if sdate or edate2:
            x = get_usage_by_dates(project['project_id'], project['resource_id'],
                                   person_id=a1['person_id'])
            amt = x['su_used']
            x = get_counts_by_dates(project['project_id'], project['resource_id'],
                                    person_id=a1['person_id'])
            if options.jobs:
                j = get_jv_by_dates(project['project_id'], project['resource_id'], a1['person_id'])
                cd = get_cdv_by_dates(project['project_id'], project['resource_id'], a1['person_id'])
        else:
            amt = get_usage_on_request_resource(rr['request_resource_id'], a1['person_id'])
            x = get_counts_on_request_resource(rr['request_resource_id'], a1['person_id'])
            if options.jobs:
                j= get_jv_on_request_resource(rr['request_resource_id'], a1['person_id'])
                cd = get_cdv_on_request_resource(rr['request_resource_id'], a1['person_id'])

        if amt == 0 and options.zero_accounts:
            continue
        if not any1:
            print("Project: {}".format(project['grant_number']), end='')
            print("/{}".format(project['resource_name']), end='')
            if project['project_state'] != 'active':
                print(" status=inactive", end='')
            print("")
            print("PI: {}".format(
                fmt_name(project['pi_first_name'], project['pi_middle_name'], project['pi_last_name'])))
            print("{}".format(ux))
            any1 = 1

        print(" {} {}".format(w, name), end='')
        if username:
            print(" portal={}".format(username), end='')
        if a1['account_state'] != 'active':
            print(" status=inactive", end='')
        print(" usage={} {}".format(fmt_amount(float(amt) if amt else 0), x))

        for x in j:
            print("      job", end='')
            id = x['local_job_id']
            show_value("id", id)
            show_value("jobname", x['jobname'])
            show_value("resource", x['resource_name'])
            show_value("submit", fmt_datetime(x['submit_time']))
            show_value("start", fmt_datetime(x['start_time']))
            show_value("end", fmt_datetime(x['end_time']))
            show_value("cputime", x['cpu_time'])
            show_amt("memory", x['memory'])
            show_value("nodecount", x['nodecount'])
            show_value("processors", x['processors'])
            show_value("queue", x['queue'])
            show_value("walltime", x['wall_time'])
            show_amt("charge", x['charge'])
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
        amt = fmt_amount(float(amt))
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
    dt = re.sub('-\d\d$', '', dt)
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




def fmt_amount(amt):
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
    if not options.no_commas:
        x = "{:,}".format(x)
    x = re.sub('\.0*$', '', str(x))

    return x


def error(msg):
    print("{}: {}".format(me, msg))
    sys.exit()




def get_user(username, portal=0):
    """
    # returns a list of hashref of user info for a given username at a given resource
    # resource defaults to config param resource_name
    #
    # if second arg evaluates to true, search by portal_username

    :param username:
    :param portal:
    :return:
    """

    # construct a rest url and fetch it
    # don't forget to uri escape these things in case one has funny
    # characters
    if not portal:
        url = "{}/xdusage/v2/people/by_username/{}/{}".format(rest_url,
                                                              urllib.parse.quote(resource),
                                                              urllib.parse.quote(username))
    else:
        url = "{}/xdusage/v2/people/by_portal_username/{}".format(rest_url,
                                                                  urllib.parse.quote(username))
    result = util.json_get(options, config, url)

    # there should be only one row returned here...
    if len(result['result']) > 1:
        # there should be only one row returned here...
        if portal:
            print("Multiple user records for portal username {}".format(username))
            sys.exit()
        else:
            print("Multiple user records for user {} on resource {}".format(username, resource))
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
    url = "{}/xdusage/v2/people/by_lastname/{}".format(rest_url, urllib.parse.quote(name))
    result = util.json_get(options, config, url)

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
    url = "{}/xdusage/v2/accounts/{}/{}?{}".format(rest_url,
                                                   project['project_id'],
                                                   project['resource_id'], '&'.join(urlparams))

    result = util.json_get(options, config, url)

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
        url = "{}/xdusage/v2/resources/{}".format(rest_url, urllib.parse.quote(pat))
        result = util.json_get(options, config, url)
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
    global user

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
    url = "{}/xdusage/v2/projects?{}".format(rest_url,
                                             '&'.join(urlparams))
    result = util.json_get(options, config, url)

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



def main(wrapper_options, wrapper_config):
    global options
    global config 
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
    global resource
    global DEBUG
    global rest_url


    # re-run this as sudo to access credentials
    logname = util.check_and_run_sudo(__file__)

    # get argument list
    options = wrapper_options

    # check authorization and resource
    resources_func = "{}/xdusage/v2/resources/{}".format(wrapper_config["rest_url"], urllib.parse.quote(wrapper_config["resource"]))
    util.check_config(options, wrapper_config, __file__, resources_func)
    config = wrapper_config

    # set rest_url
    rest_url = config["rest_url"]

    # set resource
    resource = config["resource"]


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
