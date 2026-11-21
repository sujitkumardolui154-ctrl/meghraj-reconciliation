#!/usr/bin/env bash
# One-time restricted SSH QA identity bootstrap, run via: sudo bash bootstrap_readonly_agent.sh <public-key-file>
# Does not alter PostgreSQL, Docker, financial records or firewall.
set -Eeuo pipefail
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
if [[ "$EUID" -ne 0 || "$#" -ne 1 ]]; then
  echo "Usage: sudo bash $0 /home/ubuntu/sbi_lightsail_qa_ed25519.pub" >&2
  exit 1
fi
pubkey_path="$1"
if [[ ! -r "$pubkey_path" ]]; then
  echo "Public SSH key not found" >&2
  exit 1
fi
/usr/bin/ssh-keygen -lf "$pubkey_path" >/dev/null
key_type="$(/usr/bin/awk '{print $1}' "$pubkey_path")"
key_body="$(/usr/bin/awk '{print $2}' "$pubkey_path")"
if [[ "$key_type" != 'ssh-ed25519' || -z "$key_body" ]]; then
  echo "Expected ED25519 public key" >&2
  exit 1
fi
account=sbi-qa-agent
home_dir=/var/lib/sbi-qa-agent
script_dir=/usr/local/libexec/sbi-qa
gate=/usr/local/bin/sbi-qa-gate
qa_script="$script_dir/remote_readonly_qa.sh"
remote_source='https://raw.githubusercontent.com/sujitkumardolui154-ctrl/meghraj-reconciliation/aea40a6fd4529bbfa7051475fe18c53b60a10a6a/database/agent/remote_readonly_qa.sh'
if ! /usr/bin/id "$account" >/dev/null 2>&1; then
  /usr/sbin/useradd --system --create-home --home-dir "$home_dir" --shell /bin/bash "$account"
fi
/usr/bin/passwd -l "$account" >/dev/null || true
/usr/bin/install -d -o root -g root -m 0755 "$script_dir"
tmp="$(/usr/bin/mktemp)"
trap '/usr/bin/rm -f "$tmp"' EXIT
/usr/bin/curl --proto '=https' --tlsv1.2 --fail --silent --show-error --location \
  --retry 3 --output "$tmp" "$remote_source"
/usr/bin/bash -n "$tmp"
/usr/bin/install -o root -g root -m 0755 "$tmp" "$qa_script"
/usr/bin/cat > "$gate" <<'GATE'
#!/bin/sh
# SSH forced command ignores caller-provided commands, arguments and input.
exec /usr/bin/sudo -n -- /usr/local/libexec/sbi-qa/remote_readonly_qa.sh </dev/null
GATE
/usr/bin/chown root:root "$gate"
/usr/bin/chmod 0755 "$gate"
sudoers_file="/etc/sudoers.d/sbi-qa-agent"
printf '%s\n' 'sbi-qa-agent ALL=(root) NOPASSWD: /usr/local/libexec/sbi-qa/remote_readonly_qa.sh' > "$sudoers_file"
/usr/bin/chmod 0440 "$sudoers_file"
/usr/sbin/visudo -cf "$sudoers_file" >/dev/null
ssh_dir="$home_dir/.ssh"
/usr/bin/install -d -o "$account" -g "$account" -m 0700 "$ssh_dir"
keyfile="$ssh_dir/authorized_keys"
printf 'restrict,command="%s" %s %s\n' "$gate" "$key_type" "$key_body" > "$keyfile"
/usr/bin/chown "$account:$account" "$keyfile"
/usr/bin/chmod 0600 "$keyfile"
echo 'LIGHTSAIL_QA_AGENT_BOOTSTRAP=READY'
echo 'QA_ACCOUNT=sbi-qa-agent'
echo 'SSH_COMMAND_RESTRICTED=YES'
echo 'FINANCIAL_WRITES_ALLOWED=NO'
echo 'GITHUB_SECRETS_NOT_CONFIGURED=YES'
echo 'Do not share the SSH private key in ChatGPT or screenshots.'
