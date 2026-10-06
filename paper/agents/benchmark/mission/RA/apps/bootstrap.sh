#!/bin/bash
# One-time setup of the real-app stack shared by the real-apps study (mission/RA) and its follow-up (mission/RA2):
# fresh random credentials in .env (unless one exists), the four official images pinned in docker-compose.yml, the
# admin accounts, the Nextcloud settings the studies ran with, and the people every run shares. Idempotent.
#   ./bootstrap.sh        then: Gitea http://127.0.0.1:3330, Nextcloud http://127.0.0.1:8481, Roundcube http://127.0.0.1:8491
# Stop with `docker compose stop`. To start over: `docker compose down -v`, delete mailconf/postfix-*.cf and .env.
set -euo pipefail
A="$(cd "$(dirname "$0")" && pwd)"; cd "$A"
mkdir -p ../logs/locks ../../RA2/logs   # run logs, and the lock that keeps one Nextcloud run at a time across both studies
if [ ! -f .env ]; then
  if [ -f mailconf/postfix-accounts.cf ]; then
    echo "mailconf/postfix-accounts.cf holds the mail accounts of an earlier stack whose .env is gone; to start over, run" >&2
    echo "'docker compose down -v' and delete mailconf/postfix-*.cf, then run this again" >&2
    exit 1
  fi
  python3 gen_credentials.py
fi
set -a; . ./.env; set +a
docker compose up -d

# the mail server shuts down if it has no account 120 s after it starts: add the first of the study's accounts at once
echo "adding the first mail account"
until docker exec ra-mailserver-1 setup email list 2>/dev/null | grep "ana@acme.test" > /dev/null \
      || docker exec ra-mailserver-1 setup email add ana@acme.test "$USER_PASS" > /dev/null 2>&1; do sleep 2; done

echo "waiting for Gitea"
until curl -sf -m 5 http://127.0.0.1:3330/api/healthz > /dev/null; do sleep 3; done
if docker exec -u git ra-gitea-1 gitea admin user list --admin 2>/dev/null | awk 'NR > 1 {print $2}' | grep -x "$GITEA_ADMIN_USER" > /dev/null; then
  echo "Gitea admin $GITEA_ADMIN_USER exists"
else
  docker exec -u git ra-gitea-1 gitea admin user create --admin --username "$GITEA_ADMIN_USER" --password "$GITEA_ADMIN_PASS" \
    --email "$GITEA_ADMIN_USER@acme.test" --must-change-password=false > /dev/null
  echo "Gitea admin $GITEA_ADMIN_USER created"
fi

echo "waiting for Nextcloud to finish installing"
until curl -sf -m 5 http://127.0.0.1:8481/status.php | grep '"installed":true' > /dev/null; do sleep 5; done
occ() { docker exec -u www-data ra-nextcloud-1 php occ "$@"; }
for app in firstrunwizard recommendations support survey_client updatenotification dashboard weather_status user_status \
           nextcloud_announcements privacy circles related_resources photos activity; do
  occ app:disable "$app" > /dev/null 2>&1 || true
done
occ config:system:set defaultapp --value=files > /dev/null
for key in auth.bruteforce.protection.enabled ratelimit.protection.enabled appstoreenabled has_internet_connection; do
  occ config:system:set "$key" --type=boolean --value=false > /dev/null
done
occ config:system:set skeletondirectory --value='' > /dev/null
occ config:system:set templatedirectory --value='' > /dev/null
occ background:cron > /dev/null

echo "waiting for the mail server"
until docker exec ra-mailserver-1 doveadm auth test ana@acme.test "$USER_PASS" > /dev/null 2>&1; do sleep 3; done

python3 setup_global.py
python3 ../../RA2/tasks/setup_global_ra2.py
echo "ready: Gitea http://127.0.0.1:3330  Nextcloud http://127.0.0.1:8481  Roundcube http://127.0.0.1:8491"
