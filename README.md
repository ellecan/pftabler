# pftabler.py
###### a pf table expiration handler

### pftabler.py is intended for two primary tasks for handling pf tables:
(primarily on OpenBSD, but this might work for other pf based OSes)
####1) it makes regular backups to disk

   `--backup` makes a backup of each table as its table name.txt in /var/pf,
   (a directory that must be made before use).

   Example:
   The pf table `bad_ssh` will be stored as `/var/pf/bad_ssh.txt`

####2) it handles expiring entries

   `--expire` will expire entries in the respective tables that are older
   than their expiration value.  Particular tables have a custom value as
   defined in EXPIRE_DELTAS, other tables receive the default as defined
   via args.expiration

   Example:
   The table `bad_ssh` will expire as 864000 seconds for ten days, while
    any new `persist` table will receive a timeout of 86400 seconds for
   one day.

### email reporting
This script has been designed to consolidate multiple cronjobs into one for a
single email report.  The email report is based on how the cron daemon is
configured, where this script simply outputs to screen.

## To install:
```
# as root
cp pftabler.py /usr/local/bin/pftabler.py
chmod +x /usr/local/bin/pftabler.py
```

## To run pftabler.py

Run this from cron instead of using multiple expiration handlers/shell calls
for each of the systems "persist" driven pf tables.

You can use two crontab entries as such:

```
# Dump the tables to files
5       *       *       *       *       /usr/local/bin/pftabler.py --backup
# Remove expired entries from pf tables:
5       7       *       *       *       /usr/local/bin/pftabler.py --expire
```


#### The future?
- convert from python2.7 to python3
- config files instead of hard coding the expire deltas
- rrd-ify the data and setup munin to poll it
- post somethign to a url after a run
- report on day to day deltas and weekly/monthly/yearly trend data?
- ignore tables, where some persistent tables might not need to be backed up.
   (cant think of any now, so putting the idea here instead of into code)

