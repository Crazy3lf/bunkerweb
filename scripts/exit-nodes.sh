#!/bin/sh

# load some functions
. /opt/entrypoint/utils.sh

# copy old conf to cache
cp /etc/nginx/tor-exit-nodes.list /cache

# generate the new conf
curl -s "https://iplists.firehol.org/files/tor_exits.ipset" | \
	grep -E "^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}/?[0-9]*$" > /tmp/tor-exit-nodes.list

# if we are running nginx
if [ -f /tmp/nginx.pid ] ; then
	RELOAD="/usr/sbin/nginx -s reload"
# if we are in autoconf
elif [ -S /tmp/autoconf.sock ] ; then
	RELOAD="/opt/entrypoint/reload.py"
fi

# check if we have at least 1 line
lines="$(wc -l /tmp/tor-exit-nodes.list | cut -d ' ' -f 1)"
if [ "$lines" -gt 1 ] ; then
	job_log "[BLACKLIST] TOR exit node list updated ($lines entries)"
	# reload nginx with the new config
	mv /tmp/tor-exit-nodes.list /etc/nginx/tor-exit-nodes.list
	if [ "$RELOAD" != "" ] ; then
		$RELOAD > /dev/null 2>&1
		# new config is ok : save it in the cache
		if [ "$?" -eq 0 ] ; then
			cp /etc/nginx/tor-exit-nodes.list /cache
			job_log "[NGINX] successfull nginx reload after TOR exit node list update"
		else
			job_log "[NGINX] failed nginx reload after TOR exit node list update fallback to old list"
			cp /cache/tor-exit-nodes.list /etc/nginx
			$RELOAD > /dev/null 2>&1
		fi
	else
		cp /etc/nginx/tor-exit-nodes.list /cache
	fi
else
	job_log "[BLACKLIST] can't update TOR exit node list"
fi

rm -f /tmp/tor-exit-nodes.list 2> /dev/null
