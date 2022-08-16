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
resource = None
admin_names = []
conf_file = None
rest_url = None
command_line = None

me = None
install_dir = None
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

    result = util.json_get(options, config, url)

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
    result = util.json_get(options, config, url)
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
    result = util.json_get(options, config, url)
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
    result = util.json_get(options, config, url)

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
    result = util.json_get(options, config, url)

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
    result = util.json_get(options, config, url)

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

    url = "{}/xdusage/v1/jobs/attributes/{}".format(
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
            amt = x['su_used']
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
            util.fmt_amount(float(amt), options.no_commas),
            x)
    else:
        alloc = get_allocation(project['account_id'], project['resource_id'], options.previous_allocation)
        if len(alloc) == 0:
            return 0
        amt = float(alloc['su_used'])
        if amt == 0 and options.zero_projects:
            return 0
        x = get_counts_on_allocation(alloc['allocation_id'])
        ux = "Allocation: {}/{}\n Total={} Remaining={} Usage={} {}".format(
            alloc['alloc_start'],
            alloc['alloc_end'],
            util.fmt_amount(float(alloc['su_allocated']), options.no_commas),
            util.fmt_amount(float(alloc['su_remaining']), options.no_commas),
            util.fmt_amount(amt, options.no_commas),
            x)
    any1 = 0
    for a1 in a:
        is_pi = a1['is_pi']
        w = "PI" if is_pi else "  "
        username = a1['portal_username']
        name = util.fmt_name(a1['first_name'], a1['middle_name'], a1['last_name'])

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
                util.fmt_name(project['pi_first_name'], project['pi_middle_name'], project['pi_last_name'])))
            print("{}".format(ux))
            any1 = 1

        print(" {} {}".format(w, name), end='')
        if username:
            print(" portal={}".format(username), end='')
        if a1['acct_state'] != 'active':
            print(" status=inactive", end='')
        print(" usage={} {}".format(util.fmt_amount(float(amt) if amt else 0, options.no_commas), x))

        for x in j:
            print("      job", end='')
            id = x['local_jobid']
            util.show_value("id", id)
            util.show_value("jobname", x['jobname'])
            util.show_value("resource", x['job_resource'])
            util.show_value("submit", util.fmt_datetime(x['submit_time']))
            util.show_value("start", util.fmt_datetime(x['start_time']))
            util.show_value("end", util.fmt_datetime(x['end_time']))
            util.show_amt("memory", x['memory'], options.no_commas)
            util.show_value("nodecount", x['nodecount'])
            util.show_value("processors", x['processors'])
            util.show_value("queue", x['queue'])
            util.show_amt("charge", float(x['adjusted_charge']), options.no_commas)
            print("")
            if options.job_attributes:
                job_id = x['job_id']
                jav = get_job_attributes(job_id)
                for jav1 in jav:
                    print("        job-attr", end='')
                    util.show_value("id", id)
                    util.show_value("name", jav1['name'])
                    util.show_value("value", jav1['value'])
                    print("")

        for x in cd:
            print("     {}".format(x['type']), end='')
            print(" resource={}".format(x['site_resource_name']), end='')
            print(" date={}".format(util.fmt_datetime(x['charge_date'])), end='')
            print(" amount={}".format(util.fmt_amount(abs(x['amount']), options.no_commas)), end='')
            print("")

    if any1:
        print("")
    return any1




def get_dates():
    # my($date);
    # my($sdate, $edate, $edate2);
    local_today = datetime.datetime.today()
    local_sdate = None
    local_edate = None
    local_edate2 = None
    local_date = options.start_date
    if local_date:
        try:
            local_sdate = datetime.datetime.strptime(local_date, '%Y-%m-%d')
        except:
            pass 
        if not local_sdate:
            util.error(me, "{} -- not a valid date (please specify Y-m-d format)".format(local_date))
    if local_sdate and (local_sdate > local_today):
        util.error(me, "The start date (-s) can't be in the future.")

    local_date = options.end_date
    if local_date:
        if not local_sdate:
            util.error(me, "The end date option (-e) requires that a start date (-s) be specified.")
        try:
            local_edate = datetime.datetime.strptime(local_date, '%Y-%m-%d')
        except:
            pass
        if not local_edate:
            util.error(me, "{} -- not a valid date (please specify Y-m-d format)".format(local_date))
        local_edate2 = local_edate + datetime.timedelta(days=1)

    if local_sdate:
        local_sdate = local_sdate.strftime("%Y-%m-%d")
    if local_edate:
        local_edate = local_edate.strftime("%Y-%m-%d")
    if local_edate2:
        local_edate2 = local_edate2.strftime("%Y-%m-%d")

    if local_sdate and local_edate and (local_sdate > local_edate):
        util.error(me, "The end date (-e) can't precede the start date (-s).")

    return local_sdate, local_edate, local_edate2




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
    result = util.json_get(options, config, url)

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
            util.error(me, "user {} not found".format(username))
        user_list.extend(u)

    for username in options.portal_usernames:
        u = get_user(username, portal=1)
        if u:
            user_list.append(u)
        else:
            util.error(me, "user {} not found".format(username))

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
        url = "{}/xdusage/v1/resources/{}".format(rest_url, urllib.parse.quote(pat))
        result = util.json_get(options, config, url)
        # print('get resources = {} result = {}'.format(pat, result))
        any_r = 0
        for r in result['result']:
            resource_list.append(r['resource_id'])
            any_r = 1
        if not any_r:
            util.error(me, "{} - resource not found".format(name))

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
    result = util.json_get(options, config, url)

    # return an empty array if no results
    if len(result['result']) < 1:
        return []

    return result['result']




def main(wrapper_options, wrapper_config):
    global options
    global config
    global command_line
    global me
    global install_dir
    global today
    global user
    global resource
    global resources
    global users
    global plist
    global sdate, edate, edate2
    global rest_url

    # me
    me = __file__

    # re-run this as sudo to access credentials
    logname = util.check_and_run_sudo(me)

    # get argument list
    options = wrapper_options

    # check authorization and resource
    resources_func = "{}/xdusage/v1/resources/{}".format(wrapper_config["rest_url"], urllib.parse.quote(wrapper_config["resource"]))
    util.check_config(options, wrapper_config, __file__, resources_func)
    config = wrapper_config

    # set rest_url
    rest_url = config["rest_url"]

    # set resource
    resource = config["resource"]

    DEBUG = options.debug
    today = datetime.datetime.today().strftime('%Y-%m-%d')
    is_admin = util.is_admin_func(config, logname)

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
        util.error(me, "No projects and/or accounts found")
    sys.exit()


if __name__ == '__main__':
    main()
