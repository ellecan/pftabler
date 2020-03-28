#!/usr/bin/env python
"""
pf table expiration handler

Run this from cron instead of using multiple expiration handlers/shell calls
for each of the systems "persist" driven pf tables.


    This script is intended for two primary tasks with pf tables:

    1) it makes regular backups to disk

       --backup makes a backup of each table as its table name.txt in /var/pf,
       (a directory that must be made before use).

       Example:
       The pf table "bad_ssh" will be stored as "/var/pf/bad_ssh.txt"

    2) it handles expiring entries

       --expire will expire entries in the respective tables that are older
       than their expiration value.  Particular tables have a custom value as
       defined in EXPIRE_DELTAS, other tables receive the default as defined
       via args.expiration

       Example:
       The table "bad_ssh" will expire as 864000 seconds for ten days, while
        any new _persistent_ table will receive a timeout of 86400 seconds for
       one day.


This script has been designed to consolidate multiple cronjobs into one for a
single email report.  The email report is based on how the cron daemon is
configured, where this script simply outputs to screen.

    to install:
cp pftabler.py /usr/local/bin/pftabler.py
chmod +x /usr/local/bin/pftabler.py

To run pftabler.py, it is suggested to use two crontab entries as such:

# Dump the tables to files
5       *       *       *       *       /usr/local/bin/pftabler.py --backup
# Remove expired entries from pf tables:
5       7       *       *       *       /usr/local/bin/pftabler.py --expire


future ideas:
- convert from python2.7 to python3
- config files instead of hard coding the expire deltas
- rrd-ify the data and setup munin to poll it
- post somethign to a url after a run
- report on day to day deltas and weekly/monthly/yearly trend data?
- ignore tables, where some persistent tables might not need to be backed up.
   (cant think of any now, so putting the idea here instead of into code)
"""

import argparse

import re

import subprocess

import time


# The EXPIRE_DELTAS dictionary defines tables that expire outside of the
# usual 1 day value
# 'table_name': 'expiration in seconds',
#  86400 ==  1 day
# 432000 ==  5 days
# 864000 == 10 days
EXPIRE_DELTAS = {
    'bad_udp_vpn': '432000',

    'bad_tcp_vpn': '864000',
    'bad_ssh': '864000',
}


def get_args():
    """
    Get the command line arguments

    Features detailed help, defaults, requirements and a catch-all in args.args

    returns args, an object with the various variables as defined below:
    """
    parser = argparse.ArgumentParser()
    # store the full args:
    parser.add_argument('args', nargs='*')

    # directory - /var/pf
    parser.add_argument("--directory", type=str,
                        help="Where to store each persist tables file. " +
                        "Default is /var/pf",
                        default='/var/pf')

    # runmode backup
    parser.add_argument("--backup", action='store_true',
                        help="backup pf tables to the --directory location.")

    # runmode backup
    parser.add_argument("--expire", action='store_true',
                        help="expire the pf tables")

    # default timeout
    parser.add_argument("--expiration", type=str,
                        help="Expire the pf table entries at this" +
                        " rate in seconds. Default is 86400 (one day)",
                        default='86400')

    return parser.parse_args()


def get_persistent_tables(pfctl=None):
    """
    Get the list of tables that pf has defined at runtime,
    only the persistent tables will be returned

    returns a list of table names
    """
    pfctl = pfctl or '/sbin/pfctl'

    sh = '%s -vsTables' % pfctl

    so, se, rc, _ = runsh(sh=sh)

    tables = []

    if rc == 0:
        for line in so.splitlines():
            # lines look like this:
            # c-a-r-- __automatic_9d4b1932_0
            # -pa-r-- bad_ssh
            # we only want the persistent tables:
            if line.split()[0][1] == 'p':
                tables.append(line.split()[1])

    return tables


def dump_table(table, filename, pfctl=None):
    """
    Dump the table to a file for future processing/power outage handling

    returns the so, se, rc and timed from runsh
    """
    pfctl = pfctl or '/sbin/pfctl'

    sh = '%s -t %s -T show > %s' % (pfctl, table, filename)

    return runsh(sh=sh)


def expire_table(table, expiration, pfctl=None):
    """
    Expire entries aged greater than expiration in the specified table

    returns the so, se, rc and timed from runsh
    """
    pfctl = pfctl or '/sbin/pfctl'

    sh = '%s -t %s -T expire %s' % (pfctl, table, expiration)

    return runsh(sh=sh)


def runsh(sh, bufsize=0, shell=True, stdout=None, stderr=None, stdin=None,
          raise_err=False, duration=None):
    """
    runs a command line

    this is mini runsh

    sh: a command line
        example: 'ls -al /tmp'

    bufsize: buffer the output
             0 = unbuffered (default)
             -N = system buffering  (-1, etc.)
             N = lines to buffer (4096, etc.)

    shell: use a login shell to run the commands
           True = heavier, can use builtins (ls, etc.),
                  potentially insecure if you use this with a function
                  that takes in user input!!!!

           False = lighter weight, no builtins, you will probably rarely use
                   this mode even though its "more secure"

    stdout = where to send stdout, in our case we're going to set it to the
             pipe from subprocess (as opposed to say, another file handle)

    stderr = where to send stderr - see stdout

    raise_err = raise an error if the returncode is greater than 0 and
                raise_err is True

    returns a tuple of the subprocess stdout, sterr, returncode and elapsed
        time
    """

    stdout = stdout or subprocess.PIPE
    stderr = stderr or subprocess.PIPE
    stdin = stdin or subprocess.PIPE
    p = subprocess.Popen(args=sh, bufsize=bufsize, shell=shell,
                         stdout=stdout, stderr=stderr, stdin=stdin)

    if duration:
        elapsed_time = -1
        start_time = time.time()
        while (time.time() - start_time) < duration:
            rc = p.poll()
            if rc is not None:
                elapsed_time = time.time() - start_time
                break
            time.sleep(.1)

        if elapsed_time == -1:
            elapsed_time = duration
            p.kill()
    else:
        start_time = time.time()

    # collect the return values so is "stdout", se is "stderr",
    # but use non-clobbering variable names (threading future, etc.):
    so, se = p.communicate()

    if not duration:
        elapsed_time = time.time() - start_time

    # rc is "returncode"
    rc = p.returncode

    # raise an error:
    if rc and raise_err:
        raise ValueError('Returncode[%s] from command: %s' % (rc, sh))

    return (so, se, rc, elapsed_time)


def main():
    """
    Primarily, this sets up the output and prints it,
    based on inputs driven from argparse and whats actually in the
    pf tables.
    """
    args = get_args()

    if not args.backup and not args.expire:
        raise ValueError('Must specify a runtime mode of --backup or --expire')

    if args.backup and args.expire:
        raise ValueError('Cannot run --backup and --expire simutaneously')

    tables = get_persistent_tables()

    outputs = []
    if args.backup:
        for table in tables:
            filename = '%s/%s.txt' % (args.directory, table)
            so, se, rc, _ = dump_table(table=table, filename=filename)
            if rc != 0:
                err_str = 'ERROR: Could not backup table %s as %s' % (table,
                                                                      filename)
                outputs.append(err_str)

    if args.expire:
        time_str = 'Duration'
        width = 8
        ewidth = len(time_str)
        ipwidth = 1
        expirations = {}
        ips = {}
        for table in tables:
            if len(table) > width:
                width = len(table)

            if table in EXPIRE_DELTAS.iterkeys():
                expirations[table] = EXPIRE_DELTAS[table]
            else:
                expirations[table] = args.expiration

            if len(expirations[table]) > ewidth:
                ewidth = len(expirations[table])

            so, se, rc, timed = expire_table(table=table,
                                             expiration=expirations[table])

            results = re.search('(\d+)/(\d+) addresses expired.', se)
            if results:
                ips[table] = results.group(1)
                if len(str(ips[table])) > ipwidth:
                    ipwidth = len(str(ips[table]))

        for table in tables:
            output = '  %s | %s | %s' % (str(ips[table]).rjust(ipwidth),
                                         table.ljust(width),
                                         expirations[table].rjust(ewidth))
            outputs.append(output)

        # this only applies for args.expire:
        print '==> pftabler.py statistics <=='
        print 'The numbers represent IP addresess that were added'
        print 'as pf rules to the active firewall. The rules are '
        print 'have been removed due to expiration.  Their duration is'
        print 'listed in seconds.'
        print ''
        header = '  %s | %s | %s' % ('#'.rjust(ipwidth), 'Table'.ljust(width),
                                     time_str.rjust(ewidth))
        print header
        print '-' * (len(header) + 2)
        for line in outputs:
            print line


if __name__ == '__main__':
    main()
