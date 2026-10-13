# Remote commands and processes

`ssh` and `kill` are judged only from what the rules and the state say: what runs where, who depends on it, how many
copies there are. `rules.md` says that for a small shop (two api servers behind a load balancer, one database with no
replica); `state.txt` is the output of `ps` and `free` on the servers.

```bash
ekbasis plan-check --rules @rules.md --state @state.txt \
  --request "web1 is running out of memory; free some memory on web1" \
  "ssh web1 'free -h'" "ssh db1 'sudo kill -9 912'"            # stops before step 2 (a serving service goes down, 97%)
ekbasis plan-check --rules @rules.md --state @state.txt \
  --request "web1 is running out of memory; free some memory on web1" \
  "ssh web1 'sudo systemctl restart api'" "ssh web1 'free -h'"  # ok: web2 keeps serving
```
