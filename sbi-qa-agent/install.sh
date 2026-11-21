#!/usr/bin/env bash
# One-time, owner-approved installation. Never grants general SSH shell access to the QA key.
set -Eeuo pipefail
if [[ "$EUID" != 0 ]]; then echo "Run with sudo" >&2; exit 1; fi
if [[ $# != 1 || ! -r "$1" ]]; then echo "Usage: sudo bash install.sh /path/to/qa_key.pub" >&2; exit 1; fi
key="$(cat "$1")"
if [[ "$key" == *$'\n'* || ! "$key" =~ ^ssh-ed25519[[:space:]]+[A-Za-z0-9+/=]+([[:space:]].*)?$ ]]; then
  echo "Provide exactly one SSH ed25519 public key" >&2
  exit 1
fi
if ! id sbiqa >/dev/null 2>&1; then
  useradd --system --create-home --home-dir /var/lib/sbiqa --shell /bin/bash --user-group sbiqa
fi
install -d -o root -g root -m 0755 /usr/local/libexec/sbi-qa
install -o root -g root -m 0755 "$(dirname "$0")/readonly_probe.sh" /usr/local/libexec/sbi-qa/readonly_probe.sh
install -d -o sbiqa -g sbiqa -m 0700 /var/lib/sbiqa/.ssh
printf 'restrict,command="/usr/local/libexec/sbi-qa/readonly_probe.sh" %s\n' "$key" > /var/lib/sbiqa/.ssh/authorized_keys
chown root:root /var/lib/sbiqa/.ssh/authorized_keys
chmod 0600 /var/lib/sbiqa/.ssh/authorized_keys
if ! sudo -u postgres psql -XqAt -d postgres -c "SELECT 1 FROM pg_roles WHERE rolname='sbiqa'" | grep -qx 1; then
  sudo -u postgres psql -X -v ON_ERROR_STOP=1 -d postgres -c 'CREATE ROLE sbiqa LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOINHERIT;'
fi
sudo -u postgres psql -X -v ON_ERROR_STOP=1 -d sbi_reconciliation_main -c 'GRANT CONNECT ON DATABASE sbi_reconciliation_main TO sbiqa;'
echo 'SBI_QA_AGENT=INSTALLED'
echo 'DATABASE_DATA_MODIFICATIONS=NONE'
echo 'SBI_QA_FORCED_COMMAND=/usr/local/libexec/sbi-qa/readonly_probe.sh'
