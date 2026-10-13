How these servers work (team rules and facts):
- Commands run on a server through ssh: `ssh HOST 'CMD'` runs CMD on HOST as that user.
- web1 and web2 both run the shop's api behind the load balancer; the shop stays up while at least one of them serves.
- db1 runs PostgreSQL, the only database of the shop; there is no replica. If PostgreSQL stops, both api servers fail every request.
- kill -9 ends a process at once, without letting it finish its work; PostgreSQL killed this way restarts with crash recovery, and its clients get errors until it is back.
- systemctl restart api on one web server stops that server's api for about 10 seconds.
- /var/log/shop/*.gz are old compressed logs, already copied to the backup bucket.
